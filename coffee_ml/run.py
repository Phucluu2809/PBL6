"""Compare classifiers for coffee on a person using raw sensor trials."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime
from pathlib import Path
from statistics import median
import sys

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, balanced_accuracy_score, confusion_matrix, f1_score
from sklearn.model_selection import LeaveOneGroupOut, cross_val_predict
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from analysis import check_coffee_odor as detector
from processing.core.signals import digest, number, validity

INPUT_LABELS = {"no_coffee": 0, "coffee": 1}
CURATED_LABELS = {
    "tài": 0, "dương": 0, "aduong": 0, "phúc": 0,
    "tai_cf": 1, "duong_cf": 1, "phuc_cf": 1,
    "cf": "out_of_scope", "kk_baseline": "out_of_scope",
}
MODEL_NAMES = ("Logistic Regression", "Random Forest", "SVM (RBF)")


def discover(extra_root: Path) -> dict[Path, tuple[int | str | None, str]]:
    sources = {}
    for base, labels in (
        (ROOT / "curated_raw", CURATED_LABELS),
        (extra_root, INPUT_LABELS),
        (ROOT / "data", {}),
    ):
        for path in sorted(base.rglob("raw.csv")):
            relative = path.relative_to(base)
            if any(part.casefold() in {"preprocessed", "_robonose"} for part in relative.parts):
                continue
            label = labels.get(relative.parts[0].casefold())
            sources.setdefault(path.resolve(), (label, base.name if label is not None else ""))

    for manifest in sorted((ROOT / "data").rglob("label_manifest.csv")):
        with manifest.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            required = {"folder", "binary_use", "coffee_on_person_label"}
            if not required.issubset(reader.fieldnames or []):
                raise ValueError(f"Manifest thiếu cột nhãn: {manifest}")
            for row in reader:
                path = (manifest.parent / row["folder"] / "raw.csv").resolve()
                label = "out_of_scope"
                if row["binary_use"].strip() == "ELIGIBLE":
                    value = row["coffee_on_person_label"].strip()
                    if value not in {"0", "1"}:
                        raise ValueError(f"Nhãn ELIGIBLE không hợp lệ: {path}")
                    label = int(value)
                sources[path] = (label, display_path(manifest))

    # Preserve the label convention from the existing detector for this batch.
    for path, (label, _) in sources.items():
        if label is not None or path.parent.parent != ROOT / "data" / "2026-10-30":
            continue
        name = path.parent.name.casefold()
        if detector.metadata_status(path.parent) == "COMPLETE":
            if name.startswith(("duongcaphe2_", "duong_", "dat_")):
                sources[path] = (int(name.startswith("duongcaphe2_")), "legacy_2026-10-30")
            elif name.startswith(("caphe1_", "caphe2_", "khongkhi_")):
                sources[path] = ("out_of_scope", "legacy_2026-10-30")
    return sources


def extract(path: Path) -> tuple[str, list[float]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, strict=True)
        headers = set(reader.fieldnames or [])
        if not {"phase", "phase_elapsed_s", "timestamp"}.issubset(headers):
            raise ValueError("Thiếu cột phase, phase_elapsed_s hoặc timestamp")
        modern = "bme688_status" in headers
        rows = list(reader)
    if any(None in row or None in row.values() for row in rows):
        raise ValueError("CSV có dòng lệch số cột")
    trial_ids = {row.get("trial_id") or row.get("run_id") for row in rows} - {None, ""}
    if len(trial_ids) > 1:
        raise ValueError("raw.csv chứa nhiều lượt đo")
    errors, _ = detector.measurement_structure_quality(rows)
    if errors:
        raise ValueError("; ".join(errors))

    phases = {phase: [row for row in rows if row["phase"] == phase] for phase in detector.PHASES}
    day = datetime.fromisoformat(phases["BASELINE"][0]["timestamp"]).date().isoformat()
    features = []
    # The v1 MQ3 alias refers to the same channel as MQ3-1 on later loggers.
    mq3 = "mq3_1" if any(number(row.get("mq3_1_voltage_v")) is not None
                         for row in phases["BASELINE"]) else "mq3"
    for column, sensor in (("gas_resistance_ohm", "gas"), (f"{mq3}_voltage_v", mq3)):
        if column not in headers:
            raise ValueError(f"Thiếu cột tín hiệu {column}")
        valid = {
            phase: [(number(row["phase_elapsed_s"]), number(row[column])) for row in group
                    if validity(row, column, sensor, modern) is True]
            for phase, group in phases.items()
        }
        for phase, points in valid.items():
            if len(points) / len(phases[phase]) < detector.MIN_VALID_FRACTION:
                raise ValueError(f"{column} {phase} có {len(points)}/{len(phases[phase])} điểm hợp lệ")
            if points[-1][0] - points[0][0] < detector.MIN_PHASE_SPAN_S[phase]:
                raise ValueError(f"{column} {phase} có thời lượng hợp lệ quá ngắn")
            if any(right[0] - left[0] > detector.MAX_PHASE_GAP_S for left, right in zip(points, points[1:])):
                raise ValueError(f"{column} {phase} có khoảng trống giữa các điểm hợp lệ")
        baseline = median(value for _, value in valid["BASELINE"])
        if not baseline:
            raise ValueError(f"{column} có baseline bằng 0")
        exposure = [(time, 100 * (value - baseline) / abs(baseline)) for time, value in valid["EXPOSURE"]]
        values = [value for _, value in exposure]
        middle = [value for time, value in exposure if 40 <= time < 80]
        features.extend((detector.mean(values), detector.mean(middle),
                         detector.percentile(values, 0.10), detector.percentile(values, 0.90),
                         60 * detector.slope(exposure)))
    if not np.isfinite(features).all():
        raise ValueError("Đặc trưng không hữu hạn")
    return day, features


def display_path(path: Path) -> str:
    return path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)


def load(sources):
    records = {}
    by_hash = defaultdict(list)
    for path, (label, source) in sources.items():
        row = {"raw_csv": display_path(path), "label": label if isinstance(label, int) else "",
               "label_source": source, "day": "", "status": "", "detail": ""}
        records[path] = row
        try:
            by_hash[digest(path)].append(path)
        except OSError as error:
            row.update(status="read_error", detail=str(error))

    used = []
    features = []
    for paths in by_hash.values():
        annotated = [path for path in paths if sources[path][0] is not None]
        if len({sources[path][0] for path in annotated}) > 1:
            for path in paths:
                records[path].update(status="label_conflict", detail="Các bản cùng SHA-256 khác nhãn")
            continue
        main = (annotated or paths)[0]
        for path in paths:
            if path != main:
                records[path].update(status="duplicate", detail=display_path(main))
        row = records[main]
        label, _ = sources[main]
        if label is None:
            row["status"] = "unlabelled"
        elif label == "out_of_scope":
            row["status"] = "out_of_scope"
        else:
            try:
                day, values = extract(main)
            except (OSError, ValueError, csv.Error) as error:
                row.update(status="quality_rejected", detail=str(error))
            else:
                row.update(day=day, status="evaluated")
                used.append(row)
                features.append(values)
    return list(records.values()), used, np.asarray(features)


def evaluate(rows, features):
    labels = np.asarray([row["label"] for row in rows])
    days = [row["day"] for row in rows]
    if len(set(days)) < 2 or set(labels) != {0, 1}:
        raise ValueError("Cần mẫu hợp lệ của cả hai lớp trên ít nhất hai ngày thu")
    folds = list(LeaveOneGroupOut().split(features, labels, days))
    for train, test in folds:
        if len(set(labels[train])) < 2:
            raise ValueError(f"Giữ ngày {days[test[0]]} để test khiến tập train thiếu một lớp")

    models = (
        make_pipeline(StandardScaler(), LogisticRegression(class_weight="balanced", max_iter=5000)),
        RandomForestClassifier(n_estimators=300, class_weight="balanced", random_state=42),
        detector.build_model(),
    )
    summary = []
    for name, model in zip(MODEL_NAMES, models):
        predicted = cross_val_predict(model, features, labels, cv=folds)
        tn, fp, fn, tp = confusion_matrix(labels, predicted, labels=[0, 1]).ravel()
        summary.append(dict(model=name, accuracy=accuracy_score(labels, predicted),
                            balanced_accuracy=balanced_accuracy_score(labels, predicted),
                            f1=f1_score(labels, predicted, zero_division=0), TN=tn, FP=fp, FN=fn, TP=tp))
        for row, prediction in zip(rows, predicted):
            row[name] = int(prediction)
    return summary


def write_csv(path, rows, columns):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=HERE / "data", help="Thư mục chứa coffee/ và no_coffee/")
    parser.add_argument("--output", type=Path, default=HERE / "results", help="Thư mục lưu kết quả")
    args = parser.parse_args()
    args.input = args.input.resolve()
    try:
        if args.input != HERE / "data" and not args.input.is_dir():
            raise ValueError(f"Thư mục dữ liệu không tồn tại: {args.input}")
        if args.input == HERE / "data":
            for folder in INPUT_LABELS:
                (args.input / folder).mkdir(parents=True, exist_ok=True)
        records, used, features = load(discover(args.input))
        print(f"Đã quét {len(records)} file raw.csv")
        for status, count in sorted(Counter(row["status"] for row in records).items()):
            print(f"  {status:<18} {count:>4}")
        summary = evaluate(used, features)
        counts = Counter(row["label"] for row in used)
        days = sorted({row["day"] for row in used})
        print(f"\nLeave-one-day-out | {len(used)} lượt ({counts[0]} không CF, {counts[1]} có CF) | {len(days)} ngày")
        print("Ngày thu: " + ", ".join(days))
        print(f"{'Model':<22} {'Accuracy':>9} {'Balanced':>9} {'F1 (CF)':>9} {'TN':>4} {'FP':>4} {'FN':>4} {'TP':>4}")
        for row in summary:
            print(f"{row['model']:<22} {row['accuracy']:>9.1%} {row['balanced_accuracy']:>9.1%} "
                  f"{row['f1']:>9.1%} {row['TN']:>4} {row['FP']:>4} {row['FN']:>4} {row['TP']:>4}")
        args.output.mkdir(parents=True, exist_ok=True)
        write_csv(args.output / "summary.csv", summary, list(summary[0]))
        columns = ["raw_csv", "label", "label_source", "day", "status", "detail", *MODEL_NAMES]
        write_csv(args.output / "trials.csv", records, columns)
        print(f"\nKết quả đã lưu ở {args.output.resolve()}")
    except (OSError, ValueError, csv.Error) as error:
        print(f"Lỗi đánh giá: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
