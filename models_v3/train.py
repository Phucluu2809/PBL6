"""Fit and benchmark light smoothing using the same data splits as RoboNose V2."""

import argparse
from dataclasses import replace
import json
from pathlib import Path

import numpy as np
import torch

from models_v2.benchmark_coffee import matrix, summarize
from models_v2.improve import ARCHIVE_NAMES, END, START, TEST_NAMES, fit, load, ranks, summarize as identity_metrics, vectors
from models_v2.learned import GROUPED_CHECKPOINT, checkpoint_hash, load_corrector
from models_v2.train_coffee import OUTPUT, fit as fit_logistic, load as load_coffee
from models_v3 import coffee, identity
from models_v3.smoothing import KERNELS
from robonose_s3 import coffee_detection
from robonose_s3.rescnn64 import ResCNN64Predictor


DIRECTORY = Path(__file__).parent
METHODS = ("none", *KERNELS)


def save_report(name, report):
    (DIRECTORY / name).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


def train_identity(root):
    hardware = root / "hardware"
    encoder = ResCNN64Predictor("models/rescnn64/20261119_053351_6b8717", [hardware])
    encoder.model.requires_grad_(False).eval()
    model_path = encoder.model_dir / "model.pt"
    original_hash = checkpoint_hash(model_path)
    v2 = json.loads(GROUPED_CHECKPOINT.with_name("grouped_training_report.json").read_text(encoding="utf-8"))
    settings, epochs = v2["selected_settings"], v2["epochs"]
    trials, excluded = load(root, ARCHIVE_NAMES, encoder, exclude_root=hardware, date_range=(START, END))
    validation = {}
    for method in METHODS:
        data = [replace(trial, exposure=identity.filter_exposure(trial.exposure, method)) for trial in trials]
        results = []
        for day in sorted({trial.day for trial in data}):
            train = [trial for trial in data if trial.day != day]
            query = [trial for trial in data if trial.day == day]
            if not {trial.label for trial in train}.intersection(trial.label for trial in query):
                continue
            corrector = fit(encoder, train, settings, epochs)
            similarities = vectors(encoder, query, corrector) @ vectors(encoder, train, corrector).T
            results.extend(ranks(query, train, similarities, cross_session=True))
        validation[method] = identity_metrics(results)
        print(f"Identity archive {method}: {validation[method]}", flush=True)

    selected = max(KERNELS, key=lambda method: (validation[method]["macro_top1"], validation[method]["mrr"]))
    training = [replace(trial, exposure=identity.filter_exposure(trial.exposure, selected)) for trial in trials]
    corrector = fit(encoder, training, settings, epochs)
    assert all(parameter.grad is None for parameter in encoder.model.parameters())
    assert checkpoint_hash(model_path) == original_hash

    tests, test_excluded = load(hardware, TEST_NAMES, encoder)
    references = encoder.references[0] if encoder.references else []
    train_ids = {trial.id for trial in trials} | {sample["trial_id"] for sample in references}
    train_hashes = {trial.raw_hash for trial in trials} | {sample["raw_sha256"] for sample in references}
    train_sessions = {trial.session for trial in trials}
    holdout = [trial for trial in tests if trial.id not in train_ids and trial.raw_hash not in train_hashes
               and trial.session not in train_sessions]
    smoothed = [replace(trial, exposure=identity.filter_exposure(trial.exposure, selected)) for trial in holdout]
    metrics = {}
    for name, items, model in (("v2_grouped", holdout, load_corrector(encoder, GROUPED_CHECKPOINT)),
                               ("v3_smoothed", smoothed, corrector)):
        encoded = vectors(encoder, items, model)
        metrics[name] = identity_metrics(ranks(items, items, encoded @ encoded.T, cross_session=True))
    torch.save({
        "schema": 1, "version": f"v3-smoothed-{selected}", "encoder_sha256": original_hash,
        "settings_sha256": checkpoint_hash(encoder.model_dir / "model.json"),
        "weights": corrector.state_dict(),
        "corrector_options": {key: settings[key] for key in ("gain", "relative_context")},
    }, identity.ARTIFACT)
    save_report("identity_report.json", {
        "train_days": [START, END], "train_trials": len(trials), "excluded_train": len(excluded),
        "validation": validation, "selected": selected, "holdout": metrics,
        "holdout_sessions": len({trial.session for trial in holdout}), "excluded_holdout": test_excluded,
        "encoder_sha256": original_hash, "deployment": "optional_experimental",
    })


def train_coffee(root, nov07_root):
    previous = json.loads(OUTPUT.read_text(encoding="utf-8"))
    signals = tuple((key, coffee_detection.AVAILABLE_SIGNALS[key]) for key in previous["signals"])
    width = 5 * len(signals)

    def extract(rows):
        return [value for method in METHODS for value in coffee.features(rows, signals, method)]

    def block(x, method):
        start = METHODS.index(method) * width
        return x[:, start:start + width]

    trials, skipped = load_coffee(root, extractor=extract)
    x, y, category = matrix(trials)
    days = np.array([row[0] for row in trials])
    results = {}
    for method in METHODS:
        values = block(x, method)
        predictions = np.empty(len(y), dtype=bool)
        for day in sorted(set(days)):
            train = days != day
            scaler, model = fit_logistic(values[train], y[train], .1)
            predictions[~train] = model.decision_function(scaler.transform(values[~train])) > 0
        results[method] = summarize(y, predictions, category)
    selected = max(KERNELS, key=lambda method: (
        results[method]["all"]["balanced_accuracy"], results[method]["coffee_and_air"]["balanced_accuracy"]))
    scaler, model = fit_logistic(block(x, selected), y, .1)
    artifact = {
        "version": f"coffee_logistic_v3_{selected}", "smoothing": selected, "signals": previous["signals"],
        "mean": scaler.mean_.tolist(), "scale": scaler.scale_.tolist(), "weights": model.coef_[0].tolist(),
        "intercept": float(model.intercept_[0]),
    }
    hashes = {row[4] for row in trials}
    holdout = {}
    for name, (rows, invalid) in (
        ("nov07", load_coffee(nov07_root, extractor=extract, crosscheck_day="2026-11-07")),
        ("hardware", load_coffee(root, hardware=True, extractor=extract)),
    ):
        hx, hy, kinds = matrix([row for row in rows if row[4] not in hashes])
        if not len(hy):
            holdout[name] = {"trials": 0, "invalid": invalid}
            continue
        prior = [coffee_detection.predict_features(row, previous)["has_coffee"] for row in block(hx, "none")]
        values = block(hx, selected)
        prediction = [coffee_detection.predict_features(row, artifact)["has_coffee"] for row in values]
        assert np.array_equal(prediction, model.decision_function(scaler.transform(values)) > 0)
        holdout[name] = {"v2": summarize(hy, prior, kinds), "v3": summarize(hy, prediction, kinds), "invalid": invalid}
    coffee.ARTIFACT.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    save_report("coffee_report.json", {
        "train_days": [START, END], "train_trials": len(trials), "excluded_train": skipped,
        "validation": results, "selected": selected, "holdout": holdout, "deployment": "optional_experimental",
    })


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", choices=("identity", "coffee"))
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--nov07-root", type=Path, default=Path("D:/PBL6/curated_raw"))
    args = parser.parse_args()
    torch.set_num_threads(1)
    root = args.data.resolve(strict=True)
    if args.task == "identity":
        train_identity(root)
    else:
        train_coffee(root, args.nov07_root.resolve(strict=True))


if __name__ == "__main__":
    main()
