"""Select coffee sensors and fit a logistic model with day-grouped validation."""

import csv
import hashlib
from itertools import combinations
import json
from pathlib import Path
import re

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from models_v2.improve import ARCHIVE_NAMES, END, START, TEST_NAMES
from robonose_s3 import coffee_detection as coffee


COFFEE = re.compile(r"(?:^|[\W_])(?:cf|itcf|coffe+|coffee|cà\s+phê|caf[eé])(?=$|[\W_])")
AIR = re.compile(r"^(?:khongkhi|blank)(?:$|[ _])")
SIGNALS = tuple(coffee.AVAILABLE_SIGNALS)
OUTPUT = Path(coffee.__file__).with_name("model_sensor_v2.json")


def load(root, *, hardware=False, kinetics=False, crosscheck_day=None, extractor=None):
    samples, skipped = [], []
    seen = set()
    search = root / "hardware" if hardware else root
    pattern = "metadata.json" if crosscheck_day else "trials/*/metadata.json"
    for path in sorted(search.rglob(pattern)):
        if not hardware and path.is_relative_to(root / "hardware"):
            continue
        meta = json.loads(path.read_text(encoding="utf-8-sig"))
        day = (meta.get("started_at") or "")[:10]
        if ((crosscheck_day and day != crosscheck_day)
                or (not hardware and not crosscheck_day and not START <= day <= END)
                or meta.get("mode") != "HARDWARE"
                or meta.get("status") != "COMPLETE" or not meta.get("export_finalized")):
            continue
        name = (meta.get("name") or "").strip().casefold()
        if COFFEE.search(name) or name in {"taivscf", "tai&cf"}:
            label, kind = 1, "coffee_named"
        elif AIR.match(name):
            label, kind = 0, "air_control"
        elif not crosscheck_day and name in (TEST_NAMES if hardware else ARCHIVE_NAMES):
            label, kind = 0, "identity_name_proxy"
        else:
            continue
        raw = path.with_name("raw.csv")
        try:
            digest = hashlib.sha256(raw.read_bytes()).hexdigest()
            if digest in seen:
                continue
            with raw.open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle, strict=True))
            features = (extractor(rows) if extractor else
                        coffee.extract_features(rows, tuple(coffee.AVAILABLE_SIGNALS.items()), kinetics=kinetics))
        except (OSError, ValueError, KeyError, TypeError, csv.Error) as error:
            skipped.append({"trial_id": meta.get("trial_id"), "reason": str(error)})
            continue
        seen.add(digest)
        samples.append((day, label, kind, features, digest))
    return samples, skipped


def metrics(y, predictions):
    y, predictions = np.asarray(y), np.asarray(predictions)
    tp = int(np.sum((y == 1) & (predictions == 1)))
    tn = int(np.sum((y == 0) & (predictions == 0)))
    positives, negatives = int(np.sum(y == 1)), int(np.sum(y == 0))
    recall = tp / positives if positives else None
    specificity = tn / negatives if negatives else None
    return {"tp": tp, "fn": positives - tp, "tn": tn, "fp": negatives - tn,
            "balanced_accuracy": (recall + specificity) / 2 if positives and negatives else None}


def fit(x, y, strength):
    scaler = StandardScaler().fit(x)
    classifier = LogisticRegression(C=strength, class_weight="balanced", max_iter=1000)
    return scaler, classifier.fit(scaler.transform(x), y)


def columns(channels):
    return [j for i in channels for j in range(5 * i, 5 * (i + 1))]


def main():
    root = Path("data").resolve()
    samples, skipped = load(root)
    days = np.array([s[0] for s in samples])
    y = np.array([s[1] for s in samples])
    x = np.array([s[3] for s in samples])
    leaderboard = []
    for size in range(1, len(SIGNALS) + 1):
        for channels in combinations(range(len(SIGNALS)), size):
            chosen = columns(channels)
            for strength in (.1, 1., 10.):
                predicted = np.empty_like(y)
                for day in sorted(set(days)):
                    test = days == day
                    if len(set(y[~test])) < 2:
                        raise ValueError("Day split has only one training class.")
                    scaler, clf = fit(x[~test][:, chosen], y[~test], strength)
                    predicted[test] = clf.predict(scaler.transform(x[test][:, chosen]))
                leaderboard.append((channels, strength, metrics(y, predicted), predicted))
    leaderboard.sort(key=lambda item: (
        -item[2]["balanced_accuracy"], item[2]["fn"], len(item[0]), item[1], item[0]))
    channels, strength, grouped, selected = leaderboard[0]
    chosen = columns(channels)
    scaler, clf = fit(x[:, chosen], y, strength)
    weights = clf.coef_[0].tolist()
    previous = json.loads(OUTPUT.with_name("model.json").read_text(encoding="utf-8"))
    legacy = [coffee.predict_features(row[:10], previous)["has_coffee"] for row in x]
    hardware, hardware_skipped = load(root, hardware=True)
    training_hashes = {sample[4] for sample in samples}
    hardware = [sample for sample in hardware if sample[4] not in training_hashes]
    report = {
        "train_window": [START, END], "signals": [SIGNALS[i] for i in channels], "C": strength,
        "archive_trials": len(samples), "days": sorted(set(days)),
        "excluded_archive_signals": skipped,
        "archive_grouped_v2": grouped, "archive_old_reference_only": metrics(y, legacy),
        "archive_named_coffee_vs_air_only": {
            mode: metrics(y[mask], np.asarray(pred)[mask])
            for mask in [np.array([s[2] != "identity_name_proxy" for s in samples])]
            for mode, pred in (("grouped_v2", selected), ("old_reference_only", legacy))
        },
        "validation_top5": [{"signals": [SIGNALS[i] for i in ids], "C": c, **scores}
                            for ids, c, scores, _ in leaderboard[:5]],
        "sensor_weight_l2": {SIGNALS[channel]: float(np.linalg.norm(weights[i*5:i*5+5]))
                             for i, channel in enumerate(channels)},
        "hardware_excluded_signals": hardware_skipped,
    }
    if hardware:
        hx, hy = np.array([s[3] for s in hardware]), [s[1] for s in hardware]
        report["hardware_v2"] = metrics(hy, clf.predict(scaler.transform(hx[:, chosen])))
        report["hardware_old"] = metrics(hy, [coffee.predict_features(row[:10], previous)["has_coffee"]
                                              for row in hx])
    artifact = {"version": "logistic_sensor_selection_v2", "signals": report["signals"],
                "mean": scaler.mean_.tolist(), "scale": scaler.scale_.tolist(),
                "weights": weights, "intercept": float(clf.intercept_[0])}
    report["activated"] = grouped["balanced_accuracy"] > report["archive_old_reference_only"]["balanced_accuracy"]
    if report["activated"]:
        OUTPUT.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    Path(__file__).with_name("coffee_sensor_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
