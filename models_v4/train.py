"""Train and benchmark V4 without changing the previous models."""

import argparse
from dataclasses import replace
import json
from pathlib import Path

import numpy as np
import torch

from models_v2.benchmark_coffee import matrix, summarize
from models_v2.improve import (
    ARCHIVE_NAMES, END, START, TEST_NAMES, fit, load, ranks, stacked, summarize as identity_metrics,
)
from models_v2.learned import GROUPED_CHECKPOINT, checkpoint_hash
from models_v2.train_coffee import fit as fit_logistic, load as load_coffee
from models_v3.identity import filter_exposure
from models_v4 import COFFEE_ARTIFACT, DIRECTORY, IDENTITY_ARTIFACT, coffee, identity
from robonose_s3.rescnn64 import ResCNN64Predictor


IDENTITY_MODELS = {
    "v1": (1., 0., 0.),
    "v2": (0., 1., 0.),
    "v3": (0., 0., 1.),
    "v4_equal": (1 / 3, 1 / 3, 1 / 3),
    "v4_v2_focus": (.15, .65, .20),
    "v4_v3_focus": (.15, .20, .65),
    "v4_rescnn_focus": (.60, .20, .20),
}
COFFEE_MODELS = {
    "v1_channels_refit": (1., 0., 0., 0.),
    "v2_refit": (0., 1., 0., 0.),
    "v3_refit": (0., 0., 1., 0.),
    "v4_equal": (1 / 3, 1 / 3, 1 / 3, 0.),
    "v4_later_models": (.1, .45, .45, 0.),
    "v4_kinetics": (.1, .3, .3, .3),
    "v4_kinetics_light": (.1, .4, .4, .1),
}
COFFEE_WIDTHS = tuple(len(keys) * (9 if kinetics else 5) for _, keys, kinetics in coffee.BRANCHES.values())


def report(task, payload):
    (DIRECTORY / f"{task}_report.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)


def train_identity(root):
    hardware = root / "hardware"
    encoder = ResCNN64Predictor("models/rescnn64/20261119_053351_6b8717", [hardware])
    encoder.model.requires_grad_(False).eval()
    model_path = encoder.model_dir / "model.pt"
    original_hash = checkpoint_hash(model_path)
    settings = json.loads(GROUPED_CHECKPOINT.with_name("grouped_training_report.json").read_text(encoding="utf-8"))
    option, epochs = settings["selected_settings"], settings["epochs"]
    method = "light3"
    archive, excluded = load(root, ARCHIVE_NAMES, encoder, exclude_root=hardware, date_range=(START, END))
    per_model = {name: [] for name in IDENTITY_MODELS}

    def fit_branches(train):
        smoothed = [replace(row, exposure=filter_exposure(row.exposure, method)) for row in train]
        return fit(encoder, train, option, epochs), fit(encoder, smoothed, option, epochs)

    def encode(data, models):
        baseline, exposure = stacked(data)
        return identity.encode(encoder, baseline, exposure, *models, method)

    for day in sorted({row.day for row in archive}):
        train = [row for row in archive if row.day != day]
        query = [row for row in archive if row.day == day]
        if not {row.label for row in train}.intersection(row.label for row in query):
            continue
        models = fit_branches(train)
        a, b = encode(query, models), encode(train, models)
        for name, weights in IDENTITY_MODELS.items():
            score = identity.fuse(a, weights) @ identity.fuse(b, weights).T
            per_model[name].extend(ranks(query, train, score, cross_session=True))
        print(f"Identity training fold: {day}", flush=True)

    validation = {name: identity_metrics(items) for name, items in per_model.items()}
    selected = max((name for name in IDENTITY_MODELS if name.startswith("v4_")),
                   key=lambda name: (validation[name]["macro_top1"], validation[name]["mrr"]))
    corrected, filtered = fit_branches(archive)
    assert all(parameter.grad is None for parameter in encoder.model.parameters())
    assert checkpoint_hash(model_path) == original_hash

    candidates, excluded_test = load(hardware, TEST_NAMES, encoder)
    gallery = encoder.references[0] if encoder.references else []
    train_ids = {row.id for row in archive} | {row["trial_id"] for row in gallery}
    train_hashes = {row.raw_hash for row in archive} | {row["raw_sha256"] for row in gallery}
    train_sessions = {row.session for row in archive}
    test = [row for row in candidates if row.id not in train_ids and row.raw_hash not in train_hashes
            and row.session not in train_sessions]
    views = encode(test, (corrected, filtered))
    results = {}
    for name in ("v1", "v2", "v3", selected):
        vector = identity.fuse(views, IDENTITY_MODELS[name])
        results[name] = identity_metrics(ranks(test, test, vector @ vector.T, cross_session=True))
    corrector_options = {key: option[key] for key in ("gain", "relative_context")}
    torch.save({
        "schema": 1, "encoder_sha256": original_hash,
        "settings_sha256": checkpoint_hash(encoder.model_dir / "model.json"),
        "smoothing": method, "fusion_weights": list(IDENTITY_MODELS[selected]),
        "corrected": {"options": corrector_options, "weights": corrected.state_dict()},
        "filtered": {"options": corrector_options, "weights": filtered.state_dict()},
    }, IDENTITY_ARTIFACT)
    report("identity", {
        "training_dates": [START, END], "training_trials": len(archive), "excluded_train": len(excluded),
        "validation": validation, "selected": selected, "fusion_weights": IDENTITY_MODELS[selected],
        "holdout": results, "holdout_sessions": len({row.session for row in test}),
        "excluded_holdout_by_loader": len(excluded_test),
        "excluded_holdout_overlap": len(candidates) - len(test), "encoder_sha256": original_hash,
    })


def coffee_extract(rows):
    return [value for branch in coffee.BRANCHES for value in coffee.extract(rows, branch)]


def train_logistics(x, y):
    result = {}
    start = 0
    for branch, width in zip(coffee.BRANCHES, COFFEE_WIDTHS, strict=True):
        values = x[:, start:start + width]
        scaler, model = fit_logistic(values, y, .1)
        result[branch] = {"mean": scaler.mean_.tolist(), "scale": scaler.scale_.tolist(),
                          "weights": model.coef_[0].tolist(), "intercept": float(model.intercept_[0])}
        start += width
    return result


def branch_logits(x, models):
    columns = []
    start = 0
    for branch, width in zip(coffee.BRANCHES, COFFEE_WIDTHS, strict=True):
        columns.append([coffee.logit(row, models[branch]) for row in x[:, start:start + width]])
        start += width
    return np.asarray(columns).T


def train_coffee(root, nov07):
    archive, excluded = load_coffee(root, extractor=coffee_extract)
    x, y, kinds = matrix(archive)
    days = np.array([row[0] for row in archive])
    out_of_fold = np.empty((len(y), len(coffee.BRANCHES)))
    for day in sorted(set(days)):
        train = days != day
        out_of_fold[~train] = branch_logits(x[~train], train_logistics(x[train], y[train]))
    validation = {name: summarize(y, out_of_fold @ weights > 0, kinds)
                  for name, weights in COFFEE_MODELS.items()}
    selected = max((name for name in COFFEE_MODELS if name.startswith("v4_")), key=lambda name: (
        validation[name]["all"]["balanced_accuracy"], validation[name]["coffee_and_air"]["balanced_accuracy"]))
    models = train_logistics(x, y)
    hashes = {row[4] for row in archive}
    holdouts = {}
    for name, (items, invalid) in (
        ("nov07", load_coffee(nov07, extractor=coffee_extract, crosscheck_day="2026-11-07")),
        ("hardware", load_coffee(root, hardware=True, extractor=coffee_extract)),
    ):
        retained = [row for row in items if row[4] not in hashes]
        if not retained:
            holdouts[name] = {"trials": 0, "invalid": invalid}
            continue
        tx, ty, tk = matrix(retained)
        logits = branch_logits(tx, models)
        holdouts[name] = {model: summarize(ty, logits @ COFFEE_MODELS[model] > 0, tk)
                          for model in ("v1_channels_refit", "v2_refit", "v3_refit", selected)}
        holdouts[name]["invalid"] = invalid
    weights = dict(zip(coffee.BRANCHES, COFFEE_MODELS[selected], strict=True))
    COFFEE_ARTIFACT.write_text(json.dumps({
        "schema": 1, "version": f"coffee_{selected}", "branches": models, "fusion_weights": weights,
    }, indent=2) + "\n", encoding="utf-8")
    report("coffee", {"training_dates": [START, END], "training_trials": len(archive), "invalid_archive": excluded,
                      "validation": validation, "selected": selected, "fusion_weights": weights, "holdout": holdouts})


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
