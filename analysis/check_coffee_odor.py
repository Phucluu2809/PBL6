"""Conservative coffee-odor checker trained from labelled session folders.

The model uses 25 BASELINE-normalized EXPOSURE features and an RBF-SVM.  It
automatically discovers labelled human sessions from 2026-10-25, 2026-10-28,
and 2026-10-29.  A wide abstention region is intentional: the dataset contains
only four positive sessions, all recorded on 2026-10-28.

Usage:
    python analysis/check_coffee_odor.py path/to/raw.csv
    python analysis/check_coffee_odor.py path/to/raw.csv --json prediction.json
    python analysis/check_coffee_odor.py --self-test
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]


def ensure_scikit_learn() -> None:
    try:
        import sklearn  # noqa: F401
        return
    except ModuleNotFoundError:
        pass
    candidates = (
        ROOT / ".venv" / "Scripts" / "python.exe",
        ROOT / ".venv" / "bin" / "python.exe",
    )
    current = Path(sys.executable).resolve()
    for candidate in candidates:
        if candidate.is_file() and candidate.resolve() != current:
            completed = subprocess.run(
                [str(candidate), str(Path(__file__).resolve()), *sys.argv[1:]],
                check=False,
            )
            raise SystemExit(completed.returncode)
    raise ModuleNotFoundError(
        "Thiếu scikit-learn. Chạy: py -3.11 -m venv .venv; "
        ".\\.venv\\Scripts\\python.exe -m pip install numpy scipy scikit-learn"
    )


ensure_scikit_learn()

import numpy as np
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


DATA_ROOT = ROOT / "data"
PHASES = ("BASELINE", "EXPOSURE")
EXPECTED_ROWS = {"BASELINE": 60, "EXPOSURE": 120}
MIN_VALID_FRACTION = 0.90
POSITIVE_THRESHOLD = 0.75
NEGATIVE_THRESHOLD = -0.75
MODEL_C = 30.0
MODEL_GAMMA = 0.1

SENSORS = {
    "bme": {
        "label": "BME688 gas",
        "value": "gas_resistance_ohm",
        "status": "bme_status",
        "fresh": "bme_fresh",
    },
    "mq135_1": {
        "label": "MQ135-1",
        "value": "mq135_1_voltage_v",
        "status": "mq135_1_status",
        "fresh": "mq135_1_fresh",
        "quality": "mq135_1_quality",
    },
    "mq3_1": {
        "label": "MQ3-1",
        "value": "mq3_1_voltage_v",
        "status": "mq3_1_status",
        "fresh": "mq3_1_fresh",
        "quality": "mq3_1_quality",
    },
    "mq135_2": {
        "label": "MQ135-2",
        "value": "mq135_2_voltage_v",
        "status": "mq135_2_status",
        "fresh": "mq135_2_fresh",
        "quality": "mq135_2_quality",
    },
    "mq3_2": {
        "label": "MQ3-2",
        "value": "mq3_2_voltage_v",
        "status": "mq3_2_status",
        "fresh": "mq3_2_fresh",
        "quality": "mq3_2_quality",
    },
}

FEATURES = (
    ("exposure_mean", "mean EXPOSURE", "%"),
    ("exposure_middle_mean", "middle mean EXPOSURE", "%"),
    ("q10", "Q10 EXPOSURE", "%"),
    ("q90", "Q90 EXPOSURE", "%"),
    ("slope_pct_per_min", "slope EXPOSURE", "%/min"),
)
FEATURE_NAMES = tuple(
    f"{sensor}__{feature}" for sensor in SENSORS for feature, _, _ in FEATURES
)


def feature_label(name: str) -> str:
    sensor, feature = name.split("__", 1)
    _, label, unit = next(spec for spec in FEATURES if spec[0] == feature)
    return f"{SENSORS[sensor]['label']} – {label} ({unit})"


def parse_float(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def parse_bool(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def mean(values: Iterable[float]) -> float:
    return statistics.fmean(values)


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def slope(points: list[tuple[float, float]]) -> float:
    if len(points) < 3:
        raise ValueError("Không đủ điểm EXPOSURE để tính slope")
    x_center = mean(point[0] for point in points)
    y_center = mean(point[1] for point in points)
    denominator = sum((point[0] - x_center) ** 2 for point in points)
    if denominator == 0:
        raise ValueError("Thời gian EXPOSURE không thay đổi")
    return sum((x - x_center) * (y - y_center) for x, y in points) / denominator


def sensor_valid(row: dict[str, str], sensor: str) -> bool:
    config = SENSORS[sensor]
    if parse_float(row.get(config["value"])) is None:
        return False
    if row.get(config["status"]) != "OK" or not parse_bool(row.get(config["fresh"])):
        return False
    if sensor == "bme":
        return all(
            parse_bool(row.get(column))
            for column in ("gas_valid", "heater_stable", "new_data")
        )
    return row.get(config["quality"]) in {None, "", "OK"}


def read_raw(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"Không tìm thấy raw.csv: {path}")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"CSV không có header: {path}")
        required = {"phase", "phase_elapsed_s"}
        for config in SENSORS.values():
            required.update(
                {str(config["value"]), str(config["status"]), str(config["fresh"])}
            )
        missing = sorted(required - set(reader.fieldnames))
        if missing:
            raise ValueError("raw.csv thiếu cột: " + ", ".join(missing))
        return list(reader)


def extract_features(path: Path) -> dict[str, object]:
    rows = read_raw(path)
    phase_rows = {
        phase: [row for row in rows if row.get("phase") == phase] for phase in PHASES
    }
    missing_phases = [phase for phase, values in phase_rows.items() if not values]
    if missing_phases:
        raise ValueError("raw.csv thiếu pha: " + ", ".join(missing_phases))

    features: dict[str, float] = {}
    valid_fractions: dict[str, dict[str, float]] = {}
    warnings: list[str] = []
    for sensor, config in SENSORS.items():
        baseline_values = [
            value
            for row in phase_rows["BASELINE"]
            if sensor_valid(row, sensor)
            and (value := parse_float(row.get(config["value"]))) is not None
        ]
        if not baseline_values:
            raise ValueError(f"Không có BASELINE hợp lệ cho {config['label']}")
        baseline = statistics.median(baseline_values)
        if baseline == 0:
            raise ValueError(f"BASELINE bằng 0 cho {config['label']}")
        normalized: dict[str, list[tuple[float, float]]] = {}
        valid_fractions[sensor] = {}
        for phase in PHASES:
            points = []
            for row in phase_rows[phase]:
                if not sensor_valid(row, sensor):
                    continue
                elapsed = parse_float(row.get("phase_elapsed_s"))
                value = parse_float(row.get(config["value"]))
                if elapsed is None or value is None:
                    continue
                points.append((elapsed, 100 * (value - baseline) / abs(baseline)))
            points.sort()
            normalized[phase] = points
            fraction = len(points) / max(
                len(phase_rows[phase]), EXPECTED_ROWS[phase], 1
            )
            valid_fractions[sensor][phase] = fraction
            if fraction < MIN_VALID_FRACTION:
                warnings.append(
                    f"{config['label']} {phase} chỉ có {fraction:.1%} dữ liệu hợp lệ"
                )
        exposure = normalized["EXPOSURE"]
        values = [value for _, value in exposure]
        if not values:
            raise ValueError(f"Không có EXPOSURE hợp lệ cho {config['label']}")
        one_third = max(len(values) // 3, 1)
        middle = values[one_third : 2 * one_third]
        features.update(
            {
                f"{sensor}__exposure_mean": mean(values),
                f"{sensor}__exposure_middle_mean": mean(middle),
                f"{sensor}__q10": percentile(values, 0.10),
                f"{sensor}__q90": percentile(values, 0.90),
                f"{sensor}__slope_pct_per_min": slope(exposure) * 60,
            }
        )
    return {
        "features": features,
        "valid_fractions": valid_fractions,
        "warnings": warnings,
        "row_count": len(rows),
    }


def metadata_status(directory: Path) -> str:
    path = directory / "metadata.json"
    if not path.is_file():
        return ""
    return str(json.loads(path.read_text(encoding="utf-8-sig")).get("status", ""))


def discover_training_rows(data_root: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    day25 = data_root / "2026-10-25"
    for directory in day25.iterdir():
        if not directory.is_dir() or not (directory / "raw.csv").is_file():
            continue
        if directory.name.lower().startswith(("tai_", "aminh_", "aquy_", "adung_")):
            rows.append({"day": "2026-10-25", "directory": directory, "label": 0})

    day28 = data_root / "2026-10-28"
    with (day28 / "label_manifest.csv").open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("binary_use") == "ELIGIBLE":
                rows.append(
                    {
                        "day": "2026-10-28",
                        "directory": day28 / str(row["folder"]),
                        "label": int(row["coffee_on_person_label"]),
                    }
                )

    day29 = data_root / "2026-10-29"
    for directory in day29.iterdir():
        if not directory.is_dir() or not (directory / "raw.csv").is_file():
            continue
        if not directory.name.lower().startswith(
            ("tai_", "aquy_", "dat_", "duong_", "phuc_")
        ):
            continue
        if metadata_status(directory) == "COMPLETE":
            rows.append({"day": "2026-10-29", "directory": directory, "label": 0})
    return rows


def load_training_sessions(
    data_root: Path, excluded_raw: Path | None = None
) -> tuple[list[dict[str, object]], list[str]]:
    sessions = []
    skipped = []
    excluded_resolved = excluded_raw.resolve() if excluded_raw else None
    for row in discover_training_rows(data_root):
        raw_path = Path(row["directory"]) / "raw.csv"
        if excluded_resolved and raw_path.resolve() == excluded_resolved:
            continue
        try:
            extracted = extract_features(raw_path)
        except ValueError as error:
            skipped.append(f"{Path(row['directory']).name}: {error}")
            continue
        if extracted["warnings"]:
            skipped.append(
                f"{Path(row['directory']).name}: " + "; ".join(extracted["warnings"])
            )
            continue
        sessions.append(
            {
                "day": row["day"],
                "folder": Path(row["directory"]).name,
                "raw_path": raw_path,
                "label": int(row["label"]),
                "features": extracted["features"],
            }
        )
    positive_count = sum(int(session["label"]) == 1 for session in sessions)
    negative_count = sum(int(session["label"]) == 0 for session in sessions)
    if positive_count < 3 or negative_count < 10:
        raise ValueError(
            f"Tập học không đủ: {negative_count} âm, {positive_count} dương"
        )
    return sessions, skipped


def feature_matrix(sessions: list[dict[str, object]]) -> np.ndarray:
    return np.asarray(
        [
            [float(session["features"][name]) for name in FEATURE_NAMES]
            for session in sessions
        ],
        dtype=float,
    )


def build_model() -> Pipeline:
    return Pipeline(
        [
            ("scale", StandardScaler()),
            (
                "svm",
                SVC(
                    C=MODEL_C,
                    gamma=MODEL_GAMMA,
                    kernel="rbf",
                    class_weight="balanced",
                ),
            ),
        ]
    )


def classify_score(score: float, out_of_distribution: bool = False) -> tuple[str, str]:
    if out_of_distribution:
        return "UNCERTAIN", "Chưa thể kết luận – mẫu ngoài miền học"
    if score >= POSITIVE_THRESHOLD:
        return "COFFEE_ODOR_LIKELY", "Có khả năng có mùi cà phê"
    if score <= NEGATIVE_THRESHOLD:
        return "NO_COFFEE_ODOR_LIKELY", "Có khả năng không có mùi cà phê"
    return "UNCERTAIN", "Chưa thể kết luận"


def predict(raw_path: Path, data_root: Path) -> dict[str, object]:
    raw_path = raw_path.resolve()
    known_rows = {
        (Path(row["directory"]) / "raw.csv").resolve(): row
        for row in discover_training_rows(data_root)
    }
    known_row = known_rows.get(raw_path)
    known_label = int(known_row["label"]) if known_row is not None else None
    leave_one_out = known_row is not None
    sessions, skipped = load_training_sessions(
        data_root, excluded_raw=raw_path if leave_one_out else None
    )
    extracted = extract_features(raw_path)
    x_train = feature_matrix(sessions)
    y_train = np.asarray([int(session["label"]) for session in sessions])
    x_input = np.asarray(
        [[float(extracted["features"][name]) for name in FEATURE_NAMES]], dtype=float
    )
    model = build_model()
    model.fit(x_train, y_train)
    score = float(model.decision_function(x_input)[0])

    scaler: StandardScaler = model.named_steps["scale"]
    standardized_train = scaler.transform(x_train)
    standardized_input = scaler.transform(x_input)[0]
    distances = np.sqrt(np.mean((standardized_train - standardized_input) ** 2, axis=1))
    nearest_distance = float(np.min(distances))
    train_nearest = []
    for index, row in enumerate(standardized_train):
        others = np.delete(standardized_train, index, axis=0)
        train_nearest.append(float(np.min(np.sqrt(np.mean((others - row) ** 2, axis=1)))))
    ood_threshold = float(max(train_nearest) * 1.5)
    max_abs_z = float(np.max(np.abs(standardized_input)))
    out_of_distribution = nearest_distance > ood_threshold or max_abs_z > 5.0
    prediction, prediction_vi = classify_score(score, out_of_distribution)
    if known_label is None:
        evaluation_against_label = None
    elif prediction == "UNCERTAIN":
        evaluation_against_label = "ABSTAIN"
    else:
        predicted_label = int(prediction == "COFFEE_ODOR_LIKELY")
        evaluation_against_label = "CORRECT" if predicted_label == known_label else "WRONG"

    svm: SVC = model.named_steps["svm"]
    baseline_vector = scaler.mean_.reshape(1, -1)
    contributions = []
    for index, name in enumerate(FEATURE_NAMES):
        perturbed = x_input.copy()
        perturbed[0, index] = baseline_vector[0, index]
        perturbed_score = float(model.decision_function(perturbed)[0])
        contributions.append(
            {
                "feature": name,
                "feature_label": feature_label(name),
                "value": float(x_input[0, index]),
                "support_for_coffee": score - perturbed_score,
            }
        )
    contributions.sort(
        key=lambda row: abs(float(row["support_for_coffee"])), reverse=True
    )
    warnings = list(extracted["warnings"])
    if leave_one_out:
        warnings.append(
            "File thuộc tập đã gán nhãn nên đã tự loại chính phiên này khỏi train (leave-one-out)"
        )
    if prediction == "UNCERTAIN":
        warnings.append(
            "Score nằm trong vùng từ chối; ép thành có/không sẽ làm tăng false positive"
        )
    if out_of_distribution:
        warnings.append("Mẫu nằm xa miền đặc trưng của các phiên huấn luyện")
    return {
        "input_file": str(raw_path),
        "prediction": prediction,
        "prediction_vi": prediction_vi,
        "known_ground_truth": known_label,
        "known_ground_truth_vi": (
            "Có mùi cà phê" if known_label == 1 else "Không có mùi cà phê"
        )
        if known_label is not None
        else None,
        "evaluation_against_label": evaluation_against_label,
        "decision_score": score,
        "thresholds": {
            "coffee": POSITIVE_THRESHOLD,
            "no_coffee": NEGATIVE_THRESHOLD,
        },
        "leave_one_out_for_known_file": leave_one_out,
        "out_of_distribution": out_of_distribution,
        "nearest_training_distance": nearest_distance,
        "ood_threshold": ood_threshold,
        "max_abs_z": max_abs_z,
        "row_count": extracted["row_count"],
        "features": extracted["features"],
        "feature_support": contributions,
        "valid_fractions": extracted["valid_fractions"],
        "warnings": warnings,
        "training": {
            "sessions": len(sessions),
            "negative": int(np.sum(y_train == 0)),
            "positive": int(np.sum(y_train == 1)),
            "skipped": skipped,
            "model": "StandardScaler + RBF-SVM",
            "C": MODEL_C,
            "gamma": MODEL_GAMMA,
            "support_vectors": int(len(svm.support_)),
            "positive_sessions_note": "Tất cả positive hiện chỉ thuộc ngày 2026-10-28",
        },
    }


def evaluate_scores(labels: np.ndarray, scores: np.ndarray) -> dict[str, object]:
    raw_predictions = (scores >= 0).astype(int)
    decisions = [classify_score(float(score))[0] for score in scores]
    decisive_indices = [index for index, value in enumerate(decisions) if value != "UNCERTAIN"]
    decisive_correct = sum(
        (decisions[index] == "COFFEE_ODOR_LIKELY") == bool(labels[index])
        for index in decisive_indices
    )
    positive_count = int(np.sum(labels == 1))
    negative_count = int(np.sum(labels == 0))
    sensitivity = (
        float(np.sum((raw_predictions == 1) & (labels == 1)) / positive_count)
        if positive_count
        else None
    )
    specificity = (
        float(np.sum((raw_predictions == 0) & (labels == 0)) / negative_count)
        if negative_count
        else None
    )
    balanced_accuracy = (
        (sensitivity + specificity) / 2
        if sensitivity is not None and specificity is not None
        else None
    )
    return {
        "raw_balanced_accuracy": balanced_accuracy,
        "raw_sensitivity": sensitivity,
        "raw_specificity": specificity,
        "abstention_coverage": len(decisive_indices) / len(labels),
        "accuracy_when_decisive": (
            decisive_correct / len(decisive_indices) if decisive_indices else None
        ),
        "decisions": decisions,
    }


def self_test(data_root: Path) -> dict[str, object]:
    sessions, skipped = load_training_sessions(data_root)
    x = feature_matrix(sessions)
    y = np.asarray([int(session["label"]) for session in sessions])
    loo_scores = []
    for index in range(len(sessions)):
        mask = np.arange(len(sessions)) != index
        model = build_model()
        model.fit(x[mask], y[mask])
        loo_scores.append(float(model.decision_function(x[index : index + 1])[0]))
    loo_scores_array = np.asarray(loo_scores)

    day_holdouts = {}
    for day in ("2026-10-25", "2026-10-29"):
        train_mask = np.asarray([session["day"] != day for session in sessions])
        test_mask = ~train_mask
        model = build_model()
        model.fit(x[train_mask], y[train_mask])
        scores = model.decision_function(x[test_mask])
        day_holdouts[day] = {
            "labels": y[test_mask].tolist(),
            "scores": [float(value) for value in scores],
            "evaluation": evaluate_scores(y[test_mask], scores),
        }

    rows = []
    evaluations = evaluate_scores(y, loo_scores_array)
    for session, truth, score, decision in zip(
        sessions, y, loo_scores, evaluations["decisions"]
    ):
        rows.append(
            {
                "day": session["day"],
                "folder": session["folder"],
                "truth": int(truth),
                "score": score,
                "decision": decision,
            }
        )
    return {
        "sessions": len(sessions),
        "negative": int(np.sum(y == 0)),
        "positive": int(np.sum(y == 1)),
        "loo": evaluations,
        "day_holdouts": day_holdouts,
        "rows": rows,
        "skipped": skipped,
        "warning": (
            "Không có positive ở ngày khác 2026-10-28, nên chưa thể đo khả năng "
            "phát hiện cà phê trên một ngày hoàn toàn mới."
        ),
    }


def print_prediction(result: dict[str, object]) -> None:
    print("=" * 68)
    print("KẾT QUẢ RBF-SVM KIỂM TRA MÙI CÀ PHÊ")
    print("=" * 68)
    print(f"Kết luận       : {result['prediction_vi']}")
    print(f"Mã kết quả     : {result['prediction']}")
    if result["known_ground_truth"] is not None:
        print(f"Ground truth   : {result['known_ground_truth_vi']}")
        print(f"Đánh giá       : {result['evaluation_against_label']}")
    print(f"Decision score : {float(result['decision_score']):.3f}")
    print(
        f"Ngưỡng          : có >= {POSITIVE_THRESHOLD:.2f}; "
        f"không <= {NEGATIVE_THRESHOLD:.2f}; giữa hai ngưỡng = UNCERTAIN"
    )
    print(f"Leave-one-out  : {'Có' if result['leave_one_out_for_known_file'] else 'Không'}")
    print(f"Ngoài miền học : {'Có' if result['out_of_distribution'] else 'Không'}")
    training = result["training"]
    print(
        f"Tập học        : {training['sessions']} phiên "
        f"({training['negative']} âm, {training['positive']} dương)"
    )
    print("\nFeature ảnh hưởng mạnh nhất:")
    for row in result["feature_support"][:5]:
        direction = (
            "ủng hộ CÓ cà phê"
            if float(row["support_for_coffee"]) > 0
            else "ủng hộ KHÔNG cà phê"
        )
        print(
            f"  - {row['feature_label']}: {float(row['value']):.4f} – {direction}"
        )
    if result["warnings"]:
        print("\nCảnh báo:")
        for warning in result["warnings"]:
            print(f"  - {warning}")
    print("\nKhông diễn giải decision score như xác suất.")


def print_self_test(result: dict[str, object]) -> None:
    loo = result["loo"]
    print("SELF-TEST RBF-SVM")
    print(
        f"Dữ liệu: {result['sessions']} phiên "
        f"({result['negative']} âm, {result['positive']} dương)"
    )
    print(
        f"LOOCV raw balanced accuracy: {loo['raw_balanced_accuracy']:.1%}; "
        f"sensitivity: {loo['raw_sensitivity']:.1%}; "
        f"specificity: {loo['raw_specificity']:.1%}"
    )
    print(
        f"Sau vùng từ chối: coverage {loo['abstention_coverage']:.1%}; "
        f"accuracy khi dám kết luận: "
        f"{loo['accuracy_when_decisive']:.1%}" if loo["accuracy_when_decisive"] is not None else "Không có quyết định chắc chắn"
    )
    print("\nNgày | Nhãn | Score | Quyết định | Folder")
    for row in result["rows"]:
        print(
            f"{str(row['day'])[-5:]:>5} | {row['truth']:>4} | "
            f"{float(row['score']):>6.2f} | {row['decision']:<23} | {row['folder']}"
        )
    print("\nHoldout theo ngày âm:")
    for day, details in result["day_holdouts"].items():
        evaluation = details["evaluation"]
        print(
            f"  - {day}: raw specificity {evaluation['raw_specificity']:.1%}, "
            f"coverage {evaluation['abstention_coverage']:.1%}"
        )
    print(f"\nCẢNH BÁO: {result['warning']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="RBF-SVM kiểm tra raw.csv có giống mẫu người mang mùi cà phê hay không."
    )
    parser.add_argument("raw_csv", nargs="?", type=Path)
    parser.add_argument("--data-root", type=Path, default=DATA_ROOT)
    parser.add_argument("--json", type=Path, help="Ghi kết quả chi tiết ra JSON")
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.self_test:
            result = self_test(args.data_root)
            print_self_test(result)
        else:
            if args.raw_csv is None:
                raise ValueError("Cần truyền raw.csv hoặc dùng --self-test")
            result = predict(args.raw_csv, args.data_root)
            print_prediction(result)
        if args.json:
            args.json.parent.mkdir(parents=True, exist_ok=True)
            args.json.write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(f"\nĐã ghi JSON: {args.json}")
        return 0
    except (FileNotFoundError, ValueError, KeyError, csv.Error) as error:
        print(f"LỖI: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
