"""Select the baseline corrector using leave-one-day-out retrieval."""

import argparse
from collections import Counter
import csv
from dataclasses import dataclass
import json
from pathlib import Path
from statistics import mean

import torch
from torch.nn import functional as F

from models_v2.learned import (
    BaselineCorrector, CHECKPOINT, GROUPED_CHECKPOINT, checkpoint_hash, inputs, load_corrector,
)
from robonose_s3.rescnn64 import ResCNN64Predictor


START, END = "2026-11-09", "2026-11-20"
ARCHIVE_NAMES = {
    "duong": "Dương", "duong_ktx": "Dương", "duong_phongtai": "Dương", "duong_e205": "Dương",
    "anhduong_warn_phongtai": "Dương", "phucluu": "Phúc", "phuc_phongtai": "Phúc",
    "tai_phongtai": "Tài", "tai_e205": "Tài",
    **{name: name for name in ("chau", "lam", "son", "tan", "toan", "tuan")},
    **{f"{name}_phongtai": name for name in ("chau", "lam", "son", "tan", "toan", "tuan")},
}
TEST_NAMES = {"phucluu": "Phúc", "phucluu_e304": "Phúc", "tai_e304": "Tài", "tai_f209": "Tài"}


@dataclass
class Trial:
    id: str
    raw_hash: str
    day: str
    session: str
    label: str
    baseline: torch.Tensor
    exposure: torch.Tensor


def load(root, names, encoder, *, exclude_root=None, date_range=None):
    trials, excluded = [], []
    seen_ids, seen_hashes = set(), set()
    for path in sorted(root.rglob("trials/*/metadata.json")):
        if exclude_root and path.resolve().is_relative_to(exclude_root):
            continue
        try:
            meta = json.loads(path.read_text(encoding="utf-8-sig"))
            day = (meta.get("started_at") or "")[:10]
            if date_range and not date_range[0] <= day <= date_range[1]:
                continue
            if meta.get("mode") != "HARDWARE":
                continue
            trial_id = meta.get("trial_id")
            label = names.get((meta.get("name") or "").strip().casefold())
            if meta.get("status") != "COMPLETE" or not meta.get("export_finalized"):
                excluded.append({"trial_id": trial_id, "reason": "Lượt chưa hoàn chỉnh"})
                continue
            if label is None:
                excluded.append({"trial_id": trial_id, "reason": "Tên không xác nhận nhãn danh tính"})
                continue
            baseline, exposure, info = inputs(path.parent, encoder)
            if trial_id in seen_ids or info["raw_sha256"] in seen_hashes:
                excluded.append({"trial_id": trial_id, "reason": "Trùng UUID hoặc SHA-256"})
                continue
            seen_ids.add(trial_id)
            seen_hashes.add(info["raw_sha256"])
            trials.append(Trial(trial_id, info["raw_sha256"], day, info["session_id"], label, baseline, exposure))
        except (OSError, ValueError, KeyError, csv.Error) as error:
            excluded.append({"folder": path.parent.name, "reason": str(error)})
    return trials, excluded


def stacked(trials):
    return torch.stack([t.baseline for t in trials]), torch.stack([t.exposure for t in trials])


def fit(encoder, trials, option, epochs):
    torch.manual_seed(42)
    b, x = stacked(trials)
    y = torch.tensor([encoder.labels.index(t.label) for t in trials])
    groups = torch.tensor([int(t.day.replace("-", "")) for t in trials])
    model = BaselineCorrector(gain=option["gain"], relative_context=option["relative_context"])
    context = model.context(b)
    model.center.copy_(context.mean(0))
    model.scale.copy_(context.std(0, unbiased=False).clamp_min(1e-6))
    optimizer = torch.optim.AdamW(model.parameters(), lr=.003)
    frequencies = torch.bincount(y, minlength=len(encoder.labels)).clamp_min(1).float()
    weights = frequencies.rsqrt()
    classifier = F.normalize(encoder.model.classifier.weight, dim=1)
    with torch.no_grad():
        original = encoder.model.encode(x)
    for _ in range(epochs):
        for idx in torch.randperm(len(y)).split(24):
            adjusted = model(b[idx], x[idx])
            embedding = encoder.model.encode(adjusted)
            ce = F.cross_entropy(12 * embedding @ classifier.T, y[idx], weight=weights)
            penalty = (adjusted - x[idx]).square().mean()
            loss = ce + option["regularization"] * penalty
            if option["contrastive"]:
                other_day = groups[idx, None] != groups
                same = y[idx, None] == y
                pos = same & other_day
                eligible = pos.any(1) & ((~same) & other_day).any(1)
                scores = (embedding @ original.T)[eligible] / .15
                positives, available = pos[eligible], other_day[eligible]
                if scores.numel():
                    partition = scores.masked_fill(~available, -torch.inf).logsumexp(1)
                    positive = (scores * positives).sum(1) / positives.sum(1)
                    loss = loss + option["contrastive"] * (partition - positive).mean()
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
    return model.eval()


def vectors(encoder, trials, corrector=None):
    b, x = stacked(trials)
    with torch.inference_mode():
        if corrector is not None:
            x = corrector(b, x)
        return encoder.model.encode(x)


def ranks(query, gallery, similarities, *, cross_session):
    result = []
    for trial, scores in zip(query, similarities, strict=True):
        candidates = [(sample, score) for sample, score in zip(gallery, scores.tolist(), strict=True)
                      if not cross_session or sample.session != trial.session]
        labels = {sample.label for sample, _ in candidates}
        if trial.label not in labels or len(labels) < 2:
            continue
        candidates.sort(key=lambda entry: (-entry[1], entry[0].id))
        rank = next(i for i, (sample, _) in enumerate(candidates, 1) if sample.label == trial.label)
        result.append((trial.label, rank))
    return result


def summarize(results):
    counts = Counter(label for label, _ in results)
    correct = Counter(label for label, rank in results if rank == 1)
    return {"queries": len(results), "top1": sum(correct.values()),
            "macro_top1": round(mean(correct[label] / n for label, n in counts.items()), 6) if counts else None,
            "mrr": round(mean(1 / rank for _, rank in results), 6) if counts else None,
            "by_label": {label: [correct[label], n] for label, n in sorted(counts.items())}}


def select(encoder, archive, epochs):
    options = [
        {"gain": .5, "relative_context": False, "regularization": .25, "contrastive": 0.},
        {"gain": .5, "relative_context": True, "regularization": .25, "contrastive": 0.},
        {"gain": .5, "relative_context": False, "regularization": .25, "contrastive": .5},
        {"gain": .5, "relative_context": True, "regularization": .25, "contrastive": .5},
    ]
    folds = sorted({t.day for t in archive})
    totals = [[] for _ in options]
    baseline = []
    for day in folds:
        fit_set = [t for t in archive if t.day != day]
        holdout = [t for t in archive if t.day == day]
        base_ranks = ranks(holdout, fit_set, vectors(encoder, holdout) @ vectors(encoder, fit_set).T,
                           cross_session=True)
        if not base_ranks:
            continue
        baseline.extend(base_ranks)
        print(f"Validation {day}: {len(base_ranks)} eligible queries", flush=True)
        for index, option in enumerate(options):
            model = fit(encoder, fit_set, option, epochs)
            scores = vectors(encoder, holdout, model) @ vectors(encoder, fit_set, model).T
            totals[index].extend(ranks(holdout, fit_set, scores, cross_session=True))
    report = [summarize(row) for row in totals]
    if not baseline:
        raise ValueError("No labeled cross-day validation queries.")
    best = max(range(len(options)), key=lambda index: (report[index]["macro_top1"], report[index]["mrr"]))
    return options[best], {"original": summarize(baseline), "variants": [
        {"settings": option, **metric} for option, metric in zip(options, report, strict=True)
    ]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--model-dir", type=Path, default=Path("models/rescnn64/20261119_053351_6b8717"))
    parser.add_argument("--epochs", type=int, default=20)
    args = parser.parse_args()
    root = args.data.resolve(strict=True)
    hardware = root / "hardware"
    torch.set_num_threads(1)
    encoder = ResCNN64Predictor(args.model_dir, [hardware])
    encoder.model.requires_grad_(False).eval()
    original_hash = checkpoint_hash(encoder.model_dir / "model.pt")
    archive, excluded = load(root, ARCHIVE_NAMES, encoder, exclude_root=hardware, date_range=(START, END))
    print(f"Archive usable: {len(archive)}; filtered: {len(excluded)}", flush=True)
    option, validation = select(encoder, archive, args.epochs)
    print(f"Selected from archive validation: {option}", flush=True)
    model = fit(encoder, archive, option, args.epochs)
    assert all(p.grad is None for p in encoder.model.parameters())
    assert checkpoint_hash(encoder.model_dir / "model.pt") == original_hash
    checkpoint = {
        "schema": 1, "version": "v2-grouped", "encoder_sha256": original_hash,
        "settings_sha256": checkpoint_hash(encoder.model_dir / "model.json"),
        "weights": model.state_dict(),
        "corrector_options": {key: option[key] for key in ("gain", "relative_context")},
    }

    # Hardware is evaluated only after the model and settings are fixed.
    test, test_excluded = load(hardware, TEST_NAMES, encoder)
    refs = encoder.references[0] if encoder.references else []
    excluded_ids = {t.id for t in archive} | {row["trial_id"] for row in refs}
    excluded_hashes = {t.raw_hash for t in archive} | {row["raw_sha256"] for row in refs}
    sessions = {t.session for t in archive}
    retained = []
    for trial in test:
        if trial.id in excluded_ids or trial.raw_hash in excluded_hashes or trial.session in sessions:
            test_excluded.append({"trial_id": trial.id, "reason": "Trùng dữ liệu train hoặc gallery gốc"})
        else:
            retained.append(trial)
    test = retained
    if not test:
        raise ValueError("No eligible hardware holdout.")
    methods = {"original": None, "grouped_v2": model}
    if CHECKPOINT.is_file():
        methods["initial_v2"] = load_corrector(encoder, CHECKPOINT)
    evaluation = {}
    for name, corrector in methods.items():
        encoded = vectors(encoder, test, corrector)
        evaluation[name] = summarize(ranks(test, test, encoded @ encoded.T, cross_session=True))
    report = {
        "training_dates": [START, END], "training_trials": len(archive),
        "by_day": dict(sorted(Counter(t.day for t in archive).items())),
        "training_by_label": dict(sorted(Counter(t.label for t in archive).items())),
        "excluded_training": excluded, "epochs": args.epochs,
        "validation": validation, "selected_settings": option, "holdout": evaluation,
        "holdout_sessions": len({t.session for t in test}), "excluded_holdout": test_excluded,
        "encoder_sha256": original_hash,
    }
    torch.save(checkpoint, GROUPED_CHECKPOINT)
    GROUPED_CHECKPOINT.with_name("grouped_training_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"archive_validation": validation, "hardware_holdout": evaluation},
                     ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
