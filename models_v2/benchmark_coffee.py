"""Qualify a replacement coffee model on held-out dates before deployment."""

import argparse
import json
from pathlib import Path

import numpy as np
from sklearn.ensemble import ExtraTreesClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from models_v2.train_coffee import SIGNALS, OUTPUT, load, metrics
from robonose_s3.coffee_detection import predict_features


ALL = tuple(range(len(SIGNALS)))
MOS = (1, 2, 3, 4)
CURRENT = (1, 3, 4)
CONFIGS = {
    "reference_v2": ("logistic", CURRENT, False, .1, 1.),
    "logistic_mos_kinetics": ("logistic", MOS, True, .1, .65),
    "logistic_all_kinetics": ("logistic", ALL, True, .1, .65),
    "logistic_current_kinetics": ("logistic", CURRENT, True, .3, .65),
    "trees_mos_kinetics": ("extra_trees", MOS, True, 5, .65),
    "trees_all_kinetics": ("extra_trees", ALL, True, 5, .65),
    "trees_current": ("extra_trees", CURRENT, False, 4, .65),
}


def indices(channels, kinetics):
    return [j for i in channels for j in range(9 * i, 9 * i + (9 if kinetics else 5))]


def matrix(samples):
    return (np.array([row[3] for row in samples]), np.array([row[1] for row in samples]),
            np.array([row[2] for row in samples]))


def fit(config, x, y, category):
    kind, channels, kinetics, strength, proxy_weight = config
    cols = indices(channels, kinetics)
    weights = np.where(category == "identity_name_proxy", proxy_weight, 1.)
    if kind == "logistic":
        scaler = StandardScaler().fit(x[:, cols])
        classifier = LogisticRegression(C=strength, class_weight="balanced", max_iter=1000)
        classifier.fit(scaler.transform(x[:, cols]), y, sample_weight=weights)
    else:
        scaler = None
        classifier = ExtraTreesClassifier(n_estimators=80, max_depth=6, min_samples_leaf=strength,
                                           class_weight="balanced", max_features=.7, random_state=42)
        classifier.fit(x[:, cols], y, sample_weight=weights)
    return scaler, classifier


def scores(config, fitted, x):
    scaler, classifier = fitted
    cols = indices(config[1], config[2])
    features = x[:, cols]
    if scaler is not None:
        features = scaler.transform(features)
    return classifier.predict_proba(features)[:, 1]


def summarize(y, predictions, categories):
    strict = categories != "identity_name_proxy"
    predictions = np.asarray(predictions)
    return {"all": metrics(y, predictions), "coffee_and_air": metrics(y[strict], predictions[strict])}


def precision_sweep(y, predictions):
    sweep = []
    for threshold in (.5, .6, .7, .8, .9):
        result = metrics(y, predictions >= threshold)
        tp, fp = result["tp"], result["fp"]
        sweep.append({"score_threshold": threshold, "true_positive": tp, "false_positive": fp,
                      "positive_precision": tp / (tp + fp) if tp + fp else None,
                      "recall": tp / (tp + result["fn"])})
    return sweep


def export(config, fitted, version):
    kind, channels, kinetics, _, _ = config
    scaler, clf = fitted
    model = {"version": version, "kind": kind, "signals": [SIGNALS[i] for i in channels],
             "feature_set": "kinetics" if kinetics else "legacy"}
    if scaler is not None:
        model.update(mean=scaler.mean_.tolist(), scale=scaler.scale_.tolist(),
                     weights=clf.coef_[0].tolist(), intercept=float(clf.intercept_[0]))
    else:
        model["trees"] = [
            {"left": tree.children_left.tolist(), "right": tree.children_right.tolist(),
             "threshold": tree.threshold.tolist(), "feature": tree.feature.tolist(),
             "positive": (tree.value[:, 0, 1] / tree.value.sum(axis=(1, 2))).tolist()}
            for tree in (item.tree_ for item in clf.estimators_)
        ]
    return model


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nov07-root", type=Path, required=True)
    args = parser.parse_args()
    root = Path("data").resolve()
    samples, skipped = load(root, kinetics=True)
    x, y, categories = matrix(samples)
    days = np.array([row[0] for row in samples])
    archive, sweeps = {}, {}
    for name, config in CONFIGS.items():
        predictions = np.empty(len(y))
        for day in sorted(set(days)):
            test = days == day
            predictions[test] = scores(config, fit(config, x[~test], y[~test], categories[~test]), x[test])
        archive[name] = summarize(y, predictions >= .5, categories)
        sweeps[name] = precision_sweep(y, predictions)
    # Use archive only for model selection. Two later checks determine deployment.
    candidate = max((name for name in CONFIGS if name != "reference_v2"), key=lambda name: (
        archive[name]["all"]["balanced_accuracy"], archive[name]["coffee_and_air"]["balanced_accuracy"]))
    config = CONFIGS[candidate]
    trained = fit(config, x, y, categories)
    v3 = export(config, trained, f"coffee_v3_{candidate}")
    v2 = json.loads(OUTPUT.read_text(encoding="utf-8"))
    hashes = {row[4] for row in samples}
    holdout = {}
    for key, loaded in (("nov07", load(args.nov07_root.resolve(strict=True), kinetics=True, crosscheck_day="2026-11-07")),
                        ("hardware", load(root, hardware=True, kinetics=True))):
        rows, invalid = loaded
        rows = [row for row in rows if row[4] not in hashes]
        hx, hy, hc = matrix(rows)
        v2cols = indices(CURRENT, False)
        base_pred = [predict_features(row[v2cols], v2)["has_coffee"] for row in hx]
        pred = scores(config, trained, hx) >= .5
        runtime_pred = [predict_features(row[indices(config[1], config[2])], v3)["has_coffee"] for row in hx]
        assert np.array_equal(runtime_pred, pred)
        holdout[key] = {"v2": summarize(hy, base_pred, hc), "candidate": summarize(hy, pred, hc), "invalid": invalid}
    original = archive["reference_v2"]["all"]
    new = archive[candidate]["all"]
    nov07 = holdout["nov07"]
    hardware = holdout["hardware"]
    deploy = (new["balanced_accuracy"] > original["balanced_accuracy"]
              and nov07["candidate"]["all"]["tp"] >= nov07["v2"]["all"]["tp"]
              and hardware["candidate"]["all"]["fp"] <= hardware["v2"]["all"]["fp"])
    report = {"archive_trials": len(samples), "invalid_archive": skipped,
              "archive_grouped": archive, "positive_threshold_sweep": sweeps,
              "selected": candidate, "holdout": holdout, "activated": deploy}
    if deploy:
        OUTPUT.with_name("model_sensor_v3.json").write_text(
            json.dumps(v3, separators=(",", ":")) + "\n", encoding="utf-8")
    Path(__file__).with_name("coffee_v3_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "positive_threshold_sweep"},
                     indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
