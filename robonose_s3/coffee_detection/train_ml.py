"""Fit and evaluate three classifiers using leave-one-day-out validation."""

import json
from pathlib import Path

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

from models_v2.train_coffee import load, metrics
from .ml import MODEL_IDS, SIGNALS, artifact_path
from . import extract_features, predict_features, _tree_score


def build(name):
    if name == "random_forest":
        return RandomForestClassifier(n_estimators=200, max_depth=5, min_samples_leaf=3,
                                      class_weight="balanced", random_state=42, n_jobs=1)
    estimator = (LogisticRegression(C=.1, class_weight="balanced", max_iter=1000)
                 if name == "logistic" else SVC(C=1, kernel="rbf", gamma="scale", class_weight="balanced"))
    return make_pipeline(StandardScaler(), estimator)


def export(name, fitted):
    payload = {"schema": 1, "version": f"coffee_ml_{name}",
               "signals": [key for key, _ in SIGNALS],
               "backend": {"logistic": "COFFEE_LOGISTIC", "svm": "COFFEE_SVM",
                           "random_forest": "COFFEE_RANDOM_FOREST"}[name]}
    if name == "random_forest":
        payload.update(kind=name, trees=[])
        for estimator in fitted.estimators_:
            tree = estimator.tree_
            values = tree.value[:, 0, :]
            payload["trees"].append({
                "left": tree.children_left.tolist(), "right": tree.children_right.tolist(),
                "feature": tree.feature.tolist(), "threshold": tree.threshold.tolist(),
                "positive": (values[:, 1] / values.sum(axis=1)).tolist(),
            })
    else:
        scaler, estimator = fitted.steps[0][1], fitted.steps[1][1]
        payload.update(mean=scaler.mean_.tolist(), scale=scaler.scale_.tolist(),
                       intercept=float(estimator.intercept_[0]))
        if name == "svm":
            payload.update(kind="svm_rbf", gamma=float(estimator._gamma),
                           weights=estimator.dual_coef_[0].tolist(), support=estimator.support_vectors_.tolist())
        else:
            payload.update(kind="logistic", weights=estimator.coef_[0].tolist())
    return payload


def main():
    samples, skipped = load(Path("data").resolve(), extractor=lambda rows: extract_features(rows, SIGNALS))
    x = np.asarray([row[3] for row in samples])
    y = np.asarray([row[1] for row in samples])
    days = np.asarray([row[0] for row in samples])
    report = {"training_dates": ["2026-11-09", "2026-11-20"], "trials": len(samples),
              "positives": int(y.sum()), "negatives": int((y == 0).sum()),
              "days": sorted(set(days)), "excluded": skipped,
              "evaluation": "Leave-one-day-out, scaler fit on each training fold", "models": {}}
    for name in MODEL_IDS:
        predicted = np.empty_like(y)
        for day in sorted(set(days)):
            test = days == day
            fitted = build(name).fit(x[~test], y[~test])
            predicted[test] = fitted.predict(x[test])
        result = metrics(y, predicted)
        result.update(accuracy=float((predicted == y).mean()), recall=result["tp"] / int(y.sum()))
        fitted = build(name).fit(x, y)
        payload = export(name, fitted)
        # Check exported inference against the estimator before publishing.
        if name == "random_forest":
            scores = np.asarray([sum(_tree_score(row, tree) for tree in payload["trees"]) /
                                 len(payload["trees"]) for row in x])
            np.testing.assert_allclose(scores, fitted.predict_proba(x)[:, 1], atol=1e-12)
            exported = scores > .5
        else:
            exported = [predict_features(row, payload)["has_coffee"] for row in x]
        np.testing.assert_array_equal(exported, fitted.predict(x))
        artifact_path(name).write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
        estimator = fitted if name == "random_forest" else fitted.steps[-1][1]
        report["models"][name] = {**result, "parameters": estimator.get_params()}
        print(name, result, flush=True)
    artifact_path("logistic").with_name("ml_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
