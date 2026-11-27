"""Learn six bounded sensor gains for identity retrieval with the frozen encoder."""

import json
from pathlib import Path

import torch
from torch.nn import functional as F

from models_v2.improve import (
    ARCHIVE_NAMES, END, START, TEST_NAMES, fit, load, ranks, stacked, summarize, vectors,
)
from models_v2.learned import (
    BaselineCorrector, GROUPED_CHECKPOINT, SENSOR_CHECKPOINT, checkpoint_hash, load_corrector,
)
from robonose_s3.rescnn64 import MODEL_CHANNELS, ResCNN64Predictor


LIMIT = .25
DEPLOY_LIMITS = (.0625, .125, .1875, LIMIT)


def calibrate(encoder, corrector, training):
    model = BaselineCorrector(corrector.gain, corrector.relative_context, sensor_limit=LIMIT)
    missing, unexpected = model.load_state_dict(corrector.state_dict(), strict=False)
    if missing != ["sensor_logits"] or unexpected:
        raise ValueError("Unexpected baseline corrector state.")
    model.requires_grad_(False)
    model.sensor_logits.requires_grad_(True)
    optimizer = torch.optim.AdamW([model.sensor_logits], lr=.05)
    b, x = stacked(training)
    days = torch.tensor([int(t.day.replace("-", "")) for t in training])
    labels = torch.tensor([encoder.labels.index(t.label) for t in training])
    across_days = days[:, None] != days
    positive = (labels[:, None] == labels) & across_days
    anchors = positive.any(dim=1) & (((labels[:, None] != labels) & across_days).any(dim=1))
    if not anchors.any():
        raise ValueError("No cross-day training pairs for sensor calibration.")
    # Weight each identity equally in the cross-day objective.
    counts = torch.bincount(labels[anchors], minlength=len(encoder.labels)).clamp_min(1)
    weight = 1 / counts[labels[anchors]]
    for _ in range(24):
        embedding = encoder.model.encode(model(b, x))
        scores = (embedding @ embedding.T)[anchors] / .15
        partition = scores.masked_fill(~across_days[anchors], -torch.inf).logsumexp(dim=1)
        positive_score = (scores * positive[anchors]).sum(dim=1) / positive[anchors].sum(dim=1)
        loss = ((partition - positive_score) * weight).sum() / weight.sum()
        loss = loss + .5 * (model.sensor_gains() - 1).square().mean()
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
    return model.eval()


def main():
    torch.set_num_threads(1)
    root = Path("data").resolve()
    hardware = root / "hardware"
    encoder = ResCNN64Predictor("models/rescnn64/20261119_053351_6b8717", [hardware])
    encoder.model.requires_grad_(False).eval()
    original = load_corrector(encoder, GROUPED_CHECKPOINT)
    report_source = json.loads(GROUPED_CHECKPOINT.with_name("grouped_training_report.json").read_text(encoding="utf-8"))
    option = report_source["selected_settings"]
    archive, excluded = load(root, ARCHIVE_NAMES, encoder, exclude_root=hardware, date_range=(START, END))
    base_ranks = []
    weighted_ranks = {limit: [] for limit in DEPLOY_LIMITS}
    for day in sorted({t.day for t in archive}):
        train = [t for t in archive if t.day != day]
        query = [t for t in archive if t.day == day]
        labels = {t.label for t in train}
        if len(labels) < 2 or not any(t.label in labels for t in query):
            continue
        baseline = fit(encoder, train, option, report_source["epochs"])
        weighted = calibrate(encoder, baseline, train)
        scores = vectors(encoder, query, baseline) @ vectors(encoder, train, baseline).T
        base_ranks.extend(ranks(query, train, scores, cross_session=True))
        for limit, output in weighted_ranks.items():
            weighted.sensor_limit = limit
            scores = vectors(encoder, query, weighted) @ vectors(encoder, train, weighted).T
            output.extend(ranks(query, train, scores, cross_session=True))
        print(day, flush=True)
    base = summarize(base_ranks)
    variants = {limit: summarize(result) for limit, result in weighted_ranks.items()}
    selected_limit = max(variants, key=lambda limit: (
        variants[limit]["macro_top1"], variants[limit]["mrr"], -limit))
    weighted = variants[selected_limit]
    candidate = calibrate(encoder, original, archive)
    candidate.sensor_limit = selected_limit
    gains = {key: value for (key, _), value in zip(MODEL_CHANNELS, candidate.sensor_gains().tolist(), strict=True)}

    test, _ = load(hardware, TEST_NAMES, encoder)
    refs = encoder.references[0] if encoder.references else []
    excluded_ids = {t.id for t in archive} | {r["trial_id"] for r in refs}
    excluded_hashes = {t.raw_hash for t in archive} | {r["raw_sha256"] for r in refs}
    sessions = {t.session for t in archive}
    test = [t for t in test if t.id not in excluded_ids and t.raw_hash not in excluded_hashes and t.session not in sessions]
    hardware_results = {}
    for name, corrector in (("original", original), ("weighted", candidate)):
        embedding = vectors(encoder, test, corrector)
        hardware_results[name] = summarize(ranks(test, test, embedding @ embedding.T, cross_session=True))
    # Archive chooses whether the change is promising. Hardware serves as a release check.
    enabled = (weighted["macro_top1"] > base["macro_top1"]
               and hardware_results["weighted"]["top1"] >= hardware_results["original"]["top1"])
    original_hash = checkpoint_hash(encoder.model_dir / "model.pt")
    assert original_hash == report_source["encoder_sha256"]
    assert all(parameter.grad is None for parameter in encoder.model.parameters())
    if enabled:
        torch.save({
            "schema": 1, "version": "v2-sensor-weighted", "encoder_sha256": original_hash,
            "settings_sha256": checkpoint_hash(encoder.model_dir / "model.json"), "weights": candidate.state_dict(),
            "corrector_options": {"gain": candidate.gain, "relative_context": candidate.relative_context,
                                  "sensor_limit": selected_limit},
        }, SENSOR_CHECKPOINT)
    report = {
        "train_window": [START, END], "training_trials": len(archive), "excluded_archive": len(excluded),
        "gains": gains, "activated": enabled, "archive_grouped": {"original": base, "weighted": weighted},
        "selected_limit": selected_limit, "archive_variants": variants, "hardware_holdout": hardware_results,
    }
    SENSOR_CHECKPOINT.with_name("identity_sensor_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
