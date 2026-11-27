"""Test logistic regression trained with within-day coffee contrasts."""

import argparse
import json
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from models_v2.benchmark_coffee import ALL, CURRENT, MOS, indices, matrix, summarize
from models_v2.train_coffee import OUTPUT, SIGNALS, load
from robonose_s3.coffee_detection import predict_features


def fit(x, y, categories, days, config):
    channels, kinetics, strength, pair_weight = config
    cols = indices(channels, kinetics)
    scaler = StandardScaler().fit(x[:, cols])
    x = scaler.transform(x[:, cols])
    pairs = []
    for day in sorted(set(days)):
        coffee = x[(days == day) & (y == 1)]
        person = x[(days == day) & (categories == "identity_name_proxy")]
        if len(coffee) and len(person):
            pairs.append((coffee[:, None] - person[None, :]).reshape(-1, x.shape[1]))
    if not pairs:
        raise ValueError("Need a day with both coffee and named-person control samples.")
    weights = np.where(categories == "identity_name_proxy", .8, 1.)
    weights = weights / np.where(y == 1, weights[y == 1].sum(), weights[y == 0].sum()) * (len(y) / 2)
    pair_weights = np.concatenate([
        np.full(len(group), pair_weight * len(y) / (2 * len(pairs) * len(group))) for group in pairs
    ])
    contrasts = np.concatenate(pairs)
    # Fit the decision direction on absolute features and contrasts. Calibrate the
    # intercept using training trials only, since pair differences have another origin.
    model = LogisticRegression(C=strength, max_iter=1000, fit_intercept=False)
    model.fit(np.vstack((x, contrasts, -contrasts)),
              np.concatenate((y, np.ones(len(contrasts)), np.zeros(len(contrasts)))),
              sample_weight=np.concatenate((weights, pair_weights, pair_weights)))
    direction = x @ model.coef_[0]
    intercept = LogisticRegression(C=10., max_iter=1000).fit(direction[:, None], y, sample_weight=weights)
    coef = intercept.coef_[0, 0] * model.coef_[0]
    return {
        "version": "coffee_logistic_date_pairs", "kind": "logistic",
        "signals": [SIGNALS[i] for i in channels], "feature_set": "kinetics" if kinetics else "legacy",
        "mean": scaler.mean_.tolist(), "scale": scaler.scale_.tolist(),
        "weights": coef.tolist(), "intercept": float(intercept.intercept_[0]),
    }


def predictions(model, x, channels, kinetics):
    return [predict_features(row[indices(channels, kinetics)], model)["has_coffee"] for row in x]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nov07-root", type=Path, required=True)
    args = parser.parse_args()
    root = Path("data").resolve()
    rows, invalid = load(root, kinetics=True)
    x, y, groups = matrix(rows)
    days = np.array([row[0] for row in rows])
    variants = []
    for channels in (CURRENT, MOS, ALL):
        for kinetics in (False, True):
            for strength in (.1, .6):
                for pair_weight in (.5, 2.):
                    config = (channels, kinetics, strength, pair_weight)
                    oof = np.empty(len(y), dtype=bool)
                    for day in sorted(set(days)):
                        train = days != day
                        model = fit(x[train], y[train], groups[train], days[train], config)
                        oof[~train] = predictions(model, x[~train], channels, kinetics)
                    variants.append((config, summarize(y, oof, groups)))
    variants.sort(key=lambda item: (item[1]["all"]["balanced_accuracy"],
                                    item[1]["coffee_and_air"]["balanced_accuracy"]), reverse=True)
    config, best = variants[0]
    model = fit(x, y, groups, days, config)
    v2 = json.loads(OUTPUT.read_text(encoding="utf-8"))
    holdout = {}
    hashes = {row[4] for row in rows}
    for name, (items, skipped) in (
        ("nov07", load(args.nov07_root.resolve(strict=True), kinetics=True, crosscheck_day="2026-11-07")),
        ("hardware", load(root, hardware=True, kinetics=True)),
    ):
        hx, hy, hg = matrix([row for row in items if row[4] not in hashes])
        holdout[name] = {"v2": summarize(hy, predictions(v2, hx, CURRENT, False), hg),
                         "candidate": summarize(hy, predictions(model, hx, *config[:2]), hg),
                         "invalid": skipped}
    report = {
        "archive_trials": len(rows), "invalid_archive": invalid, "selected": best,
        "holdout": holdout, "activated": False,
        "variants": [{"signals": [SIGNALS[i] for i in c[0]], "kinetics": c[1], "C": c[2],
                      "pair_weight": c[3], **result} for c, result in variants],
    }
    Path(__file__).with_name("coffee_pairs_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "variants"}, indent=2))


if __name__ == "__main__":
    main()
