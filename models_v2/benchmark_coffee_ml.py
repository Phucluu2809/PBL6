"""Compare regularized small-data classifiers for the coffee task."""

import argparse
import json
from pathlib import Path

import numpy as np
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.preprocessing import RobustScaler, StandardScaler
from sklearn.svm import SVC

from models_v2.benchmark_coffee import (
    ALL, CURRENT, MOS, CONFIGS, fit, indices, matrix, scores, summarize,
)
from models_v2.train_coffee import OUTPUT, SIGNALS, load
from robonose_s3.coffee_detection import predict_features


def candidates():
    for channels in (CURRENT, MOS, ALL):
        for kinetics in (False, True):
            for strength in (.3, 1., 3.):
                yield "svm_rbf", channels, kinetics, strength
            yield "shrinkage_lda", channels, kinetics, "auto"


def make(config, x, y, categories):
    method, channels, kinetics, strength = config
    cols = indices(channels, kinetics)
    if method == "svm_rbf":
        scaler = RobustScaler(quantile_range=(10, 90)).fit(x[:, cols])
        model = SVC(C=strength, gamma="scale", class_weight="balanced")
        model.fit(scaler.transform(x[:, cols]), y,
                  sample_weight=np.where(categories == "identity_name_proxy", .65, 1.))
    else:
        scaler = StandardScaler().fit(x[:, cols])
        model = LinearDiscriminantAnalysis(solver="lsqr", shrinkage=strength, priors=[.5, .5])
        model.fit(scaler.transform(x[:, cols]), y)
    return scaler, model


def predict(config, fitted, x):
    scaler, classifier = fitted
    features = scaler.transform(x[:, indices(config[1], config[2])])
    return classifier.decision_function(features) > 0


def details(config):
    method, channels, kinetics, strength = config
    return {"method": method, "signals": [SIGNALS[i] for i in channels],
            "feature_set": "kinetics" if kinetics else "legacy", "regularization": strength}


def model_json(config, fitted):
    scaler, classifier = fitted
    result = {
        "version": f"coffee_ml_{config[0]}", "kind": config[0],
        "signals": [SIGNALS[i] for i in config[1]],
        "feature_set": "kinetics" if config[2] else "legacy",
        "mean": getattr(scaler, "center_", getattr(scaler, "mean_", None)).tolist(),
        "scale": scaler.scale_.tolist(), "intercept": float(classifier.intercept_[0]),
    }
    if config[0] == "svm_rbf":
        result.update(support=classifier.support_vectors_.tolist(),
                      weights=classifier.dual_coef_[0].tolist(), gamma=float(classifier._gamma))
    else:
        result["weights"] = classifier.coef_[0].tolist()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nov07-root", type=Path, required=True)
    args = parser.parse_args()
    root = Path("data").resolve()
    rows, skipped = load(root, kinetics=True)
    x, y, categories = matrix(rows)
    days = np.array([row[0] for row in rows])
    v2config = CONFIGS["reference_v2"]
    originals = np.empty(len(y), dtype=bool)
    for day in sorted(set(days)):
        train = days != day
        originals[~train] = scores(v2config, fit(v2config, x[train], y[train], categories[train]), x[~train]) >= .5
    reference = summarize(y, originals, categories)
    leaderboard = []
    for config in candidates():
        predicted = np.empty(len(y), dtype=bool)
        for day in sorted(set(days)):
            train = days != day
            predicted[~train] = predict(config, make(config, x[train], y[train], categories[train]), x[~train])
        leaderboard.append((config, summarize(y, predicted, categories)))
    leaderboard.sort(key=lambda row: (row[1]["all"]["balanced_accuracy"],
                                      row[1]["coffee_and_air"]["balanced_accuracy"]), reverse=True)
    selected, validation = leaderboard[0]
    trained = make(selected, x, y, categories)
    previous = json.loads(OUTPUT.read_text(encoding="utf-8"))
    hashes = {row[4] for row in rows}
    holdout = {}
    selected_json = model_json(selected, trained)
    for name, (items, invalid) in (
        ("nov07", load(args.nov07_root.resolve(strict=True), kinetics=True, crosscheck_day="2026-11-07")),
        ("hardware", load(root, hardware=True, kinetics=True)),
    ):
        hx, hy, hc = matrix([row for row in items if row[4] not in hashes])
        legacy = [predict_features(row[indices(CURRENT, False)], previous)["has_coffee"] for row in hx]
        new = predict(selected, trained, hx)
        exported = [predict_features(row[indices(selected[1], selected[2])], selected_json)["has_coffee"]
                    for row in hx]
        assert np.array_equal(new, exported)
        holdout[name] = {"v2": summarize(hy, legacy, hc), "candidate": summarize(hy, new, hc), "invalid": invalid}
    deploy = (
        validation["all"]["balanced_accuracy"] > reference["all"]["balanced_accuracy"]
        and validation["coffee_and_air"]["balanced_accuracy"] >= reference["coffee_and_air"]["balanced_accuracy"]
        and holdout["nov07"]["candidate"]["all"]["tp"] >= holdout["nov07"]["v2"]["all"]["tp"]
        and holdout["hardware"]["candidate"]["all"]["fp"] <= holdout["hardware"]["v2"]["all"]["fp"]
    )
    report = {"archive_trials": len(rows), "invalid_archive": skipped, "reference_v2": reference,
              "selected": details(selected), "holdout": holdout, "activated": deploy,
              "candidates": [{"settings": details(config), **result} for config, result in leaderboard]}
    if deploy:
        OUTPUT.with_name("model_sensor_ml.json").write_text(
            json.dumps(selected_json, separators=(",", ":")) + "\n", encoding="utf-8")
    Path(__file__).with_name("coffee_ml_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({**report, "candidates": report["candidates"][:3]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
