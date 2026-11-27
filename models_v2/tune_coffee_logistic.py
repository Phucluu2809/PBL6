"""Tune coffee features and threshold with nested date-grouped validation."""

import argparse
import json
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from models_v2.benchmark_coffee import ALL, CURRENT, MOS, indices, matrix, summarize
from models_v2.train_coffee import OUTPUT, SIGNALS, load
from robonose_s3.coffee_detection import predict_features


THRESHOLDS = (-.8, -.6, -.4, -.2, 0., .2, .4, .6, .8)
TRIALS = [
    (channels, kinetics, strength, proxy)
    for channels in (CURRENT, MOS, ALL)
    for kinetics in (False, True)
    for strength in (.03, .15, 1.)
    for proxy in (.55, 1.)
]


def fit(config, x, y, category):
    channels, kinetics, strength, proxy = config
    scaler = StandardScaler().fit(x[:, indices(channels, kinetics)])
    model = LogisticRegression(C=strength, class_weight="balanced", max_iter=1000)
    model.fit(scaler.transform(x[:, indices(channels, kinetics)]), y,
              sample_weight=np.where(category == "identity_name_proxy", proxy, 1.))
    return scaler, model


def margins(config, model, x):
    scaler, classifier = model
    return classifier.decision_function(scaler.transform(x[:, indices(*config[:2])]))


def choose(config_scores, mask, y, categories):
    best = None
    best_key = None
    for index, scores in enumerate(config_scores):
        for threshold in THRESHOLDS:
            result = summarize(y[mask], scores[mask] > threshold, categories[mask])
            combined, strict = result["all"], result["coffee_and_air"]
            # Keep the broad benchmark primary and favor fewer misses on an exact tie.
            rank = (combined["balanced_accuracy"], strict["balanced_accuracy"],
                    combined["tp"], -abs(threshold))
            if best_key is None or rank > best_key:
                best_key, best = rank, (index, threshold, result)
    return best


def describe(config, threshold):
    channels, kinetics, strength, proxy = config
    return {"signals": [SIGNALS[i] for i in channels],
            "feature_set": "kinetics" if kinetics else "legacy",
            "C": strength, "person_proxy_weight": proxy, "logit_threshold": threshold}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nov07-root", type=Path, required=True)
    args = parser.parse_args()
    root = Path("data").resolve()
    samples, skipped = load(root, kinetics=True)
    x, y, categories = matrix(samples)
    days = np.array([row[0] for row in samples])
    dates = sorted(set(days))
    cache = {}

    def model_without(index, excluded):
        key = (index, tuple(sorted(excluded)))
        if key not in cache:
            train = ~np.isin(days, excluded)
            cache[key] = fit(TRIALS[index], x[train], y[train], categories[train])
        return cache[key]

    result = np.zeros(len(y), dtype=bool)
    folds = {}
    for outer in dates:
        test = days == outer
        inner_scores = np.zeros((len(TRIALS), len(y)))
        for day in dates:
            if day == outer:
                continue
            mask = days == day
            for i, config in enumerate(TRIALS):
                inner_scores[i, mask] = margins(config, model_without(i, (day, outer)), x[mask])
        index, threshold, _ = choose(inner_scores, ~test, y, categories)
        result[test] = margins(TRIALS[index], model_without(index, (outer,)), x[test]) > threshold
        folds[outer] = describe(TRIALS[index], threshold)
        print(f"Finished date {outer}", flush=True)
    nested = summarize(y, result, categories)

    oof = np.empty((len(TRIALS), len(y)))
    for date in dates:
        mask = days == date
        for i, config in enumerate(TRIALS):
            oof[i, mask] = margins(config, model_without(i, (date,)), x[mask])
    index, threshold, selection = choose(oof, np.ones(len(y), dtype=bool), y, categories)
    config = TRIALS[index]
    scaler, classifier = fit(config, x, y, categories)
    v2 = json.loads(OUTPUT.read_text(encoding="utf-8"))
    report_path = Path(__file__).with_name("coffee_v3_report.json")
    reference = json.loads(report_path.read_text(encoding="utf-8"))["archive_grouped"]["reference_v2"]
    artifact = {"version": "coffee_logistic_tuned", "kind": "logistic", **describe(config, threshold),
                "mean": scaler.mean_.tolist(), "scale": scaler.scale_.tolist(),
                "weights": classifier.coef_[0].tolist(), "intercept": float(classifier.intercept_[0] - threshold)}
    hashes = {row[4] for row in samples}
    holdout = {}
    for key, (rows, invalid) in (
        ("nov07", load(args.nov07_root.resolve(strict=True), kinetics=True, crosscheck_day="2026-11-07")),
        ("hardware", load(root, hardware=True, kinetics=True)),
    ):
        hx, hy, hc = matrix([row for row in rows if row[4] not in hashes])
        old = [predict_features(row[indices(CURRENT, False)], v2)["has_coffee"] for row in hx]
        new = margins(config, (scaler, classifier), hx) > threshold
        runtime = [predict_features(row[indices(*config[:2])], artifact)["has_coffee"] for row in hx]
        assert np.array_equal(new, runtime)
        holdout[key] = {"v2": summarize(hy, old, hc), "candidate": summarize(hy, new, hc), "invalid": invalid}
    deploy = (nested["all"]["balanced_accuracy"] >= .75
              and nested["all"]["balanced_accuracy"] > reference["all"]["balanced_accuracy"]
              and holdout["nov07"]["candidate"]["all"]["tp"] >= holdout["nov07"]["v2"]["all"]["tp"]
              and holdout["hardware"]["candidate"]["all"]["fp"] <= holdout["hardware"]["v2"]["all"]["fp"])
    report = {"archive_trials": len(samples), "configurations": len(TRIALS), "thresholds": THRESHOLDS,
              "invalid_archive": skipped, "nested_validation": nested, "reference_v2": reference,
              "selected_for_fit": describe(config, threshold), "selection_only": selection,
              "outer_folds": folds, "holdout": holdout, "activated": deploy}
    if deploy:
        OUTPUT.with_name("model_sensor_tuned.json").write_text(
            json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    Path(__file__).with_name("coffee_logistic_tuned_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "outer_folds"},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
