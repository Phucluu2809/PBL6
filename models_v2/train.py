"""Fit only the baseline corrector using the original labeled gallery."""

import argparse
import csv
import json
from pathlib import Path
from statistics import mean

import torch
from torch.nn import functional as F

from models_v2.learned import BaselineCorrector, CHECKPOINT, checkpoint_hash, inputs
from robonose_s3.rescnn64 import ResCNN64Predictor
from robonose_s3.web_server import TrialCatalog


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labeled-root", required=True, type=Path)
    parser.add_argument("--model-dir", type=Path, default=Path("models/rescnn64/20261119_053351_6b8717"))
    parser.add_argument("--evaluation-root", type=Path, default=Path("data/hardware"))
    args = parser.parse_args()

    torch.manual_seed(42)
    torch.set_num_threads(1)
    encoder = ResCNN64Predictor(args.model_dir, [args.evaluation_root])
    encoder.model.requires_grad_(False).eval()
    original_hash = checkpoint_hash(encoder.model_dir / "model.pt")
    if encoder.references is None:
        raise ValueError("Training needs the original labeled references.json.")

    baseline, exposure, targets, skipped = [], [], [], []
    train_ids, train_hashes, train_sessions = set(), set(), set()
    root = args.labeled_root.resolve(strict=True)
    for sample in encoder.references[0]:
        folder = (root / sample["path"]).resolve()
        if not folder.is_relative_to(root):
            raise ValueError("Training sample escapes labeled root.")
        try:
            b, x, info = inputs(folder, encoder)
            if info["trial_id"] != sample["trial_id"] or info["raw_sha256"] != sample["raw_sha256"]:
                raise ValueError("Labeled reference UUID/hash differs from the manifest.")
        except (OSError, ValueError, KeyError, csv.Error) as error:
            skipped.append({"trial_id": sample["trial_id"], "reason": str(error)})
            continue
        if info["raw_sha256"] in train_hashes:
            continue
        baseline.append(b)
        exposure.append(x)
        targets.append(encoder.labels.index(sample["label"]))
        train_ids.add(info["trial_id"])
        train_hashes.add(info["raw_sha256"])
        train_sessions.add(info["session_id"])
    if set(targets) != set(range(len(encoder.labels))):
        raise ValueError("Training samples are missing one or more original labels.")

    b, x, y = torch.stack(baseline), torch.stack(exposure), torch.tensor(targets)
    corrector = BaselineCorrector()
    corrector.center.copy_(b.mean(dim=0))
    corrector.scale.copy_(b.std(dim=0, unbiased=False).clamp_min(1e-6))
    optimizer = torch.optim.AdamW(corrector.parameters(), lr=.003)
    epochs = 50
    with torch.no_grad():
        initial_loss = F.cross_entropy(encoder.model(x), y).item()
    for _ in range(epochs):
        for indices in torch.randperm(len(y)).split(16):
            adjusted = corrector(b[indices], x[indices])
            classification = F.cross_entropy(encoder.model(adjusted), y[indices])
            loss = classification + .05 * (adjusted - x[indices]).square().mean()
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
    corrector.eval()
    with torch.no_grad():
        final_loss = F.cross_entropy(encoder.model(corrector(b, x)), y).item()
    assert all(parameter.grad is None for parameter in encoder.model.parameters())
    assert checkpoint_hash(encoder.model_dir / "model.pt") == original_hash

    report = {
        "training_trials": len(y), "classes": len(encoder.labels), "epochs": epochs,
        "excluded_training_trials": skipped, "training_cross_entropy_before": initial_loss,
        "training_cross_entropy_after": final_loss, "frozen_encoder_sha256": original_hash,
        "evaluation": evaluate(encoder, corrector, args.evaluation_root, train_ids, train_hashes, train_sessions),
    }
    state = {
        "schema": 1, "encoder_sha256": original_hash,
        "settings_sha256": checkpoint_hash(encoder.model_dir / "model.json"),
        "weights": corrector.state_dict(),
    }
    torch.save(state, CHECKPOINT)
    CHECKPOINT.with_name("training_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


def evaluate(encoder, corrector, root, train_ids, train_hashes, train_sessions):
    labels = {"phucluu": "Phúc Lưu", "phucluu_e304": "Phúc Lưu", "tai_e304": "Tài", "tai_f209": "Tài"}
    known_references = encoder.references[0]
    excluded_ids = train_ids | {row["trial_id"] for row in known_references}
    excluded_hashes = train_hashes | {row["raw_sha256"] for row in known_references}
    records = []
    for row in TrialCatalog(root).list():
        label = labels.get((row["name"] or "").casefold())
        if not label or row["status"] != "COMPLETE" or not row["export_finalized"]:
            continue
        b, x, info = inputs(row["folder"], encoder)
        if (info["trial_id"] in excluded_ids or info["raw_sha256"] in excluded_hashes
                or info["session_id"] in train_sessions):
            continue
        with torch.inference_mode():
            vectors = (encoder.model.encode(x[None])[0],
                       encoder.model.encode(corrector(b[None], x[None]))[0])
        records.append((label, info["session_id"], info["trial_id"], vectors))

    ranks = {"original": [], "learned": []}
    for label, session, _, vectors in records:
        candidates = [row for row in records if row[1] != session]
        if {row[0] for row in candidates} != set(labels.values()):
            continue
        for index, name in enumerate(ranks):
            ranked = sorted(candidates, key=lambda row: (-(vectors[index] @ row[3][index]).item(), row[2]))
            ranks[name].append(next(rank for rank, row in enumerate(ranked, 1) if row[0] == label))
    return {"sessions": len({row[1] for row in records}), "retained_trials": len(records), **{
        name: {"queries": len(values), "top1": values.count(1),
               "mrr": round(mean(1 / rank for rank in values), 4) if values else None}
        for name, values in ranks.items()
    }}


if __name__ == "__main__":
    main()
