"""Conservative coffee-odor checker trained from labelled session folders.

The model uses 25 BASELINE-normalized EXPOSURE features and an RBF-SVM. It
automatically discovers labelled human sessions from 2026-10-28 and
2026-10-30. Coffee-only and ambient-air sessions are outside the binary task.

Usage:
    python analysis/check_coffee_odor.py path/to/raw.csv
    python analysis/check_coffee_odor.py path/to/raw.csv --json prediction.json
    python analysis/check_coffee_odor.py --self-test
"""

from __future__ import annotations

import argparse
import csv
import hashlib
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
MAX_PHASE_GAP_S = 3.0
MIN_PHASE_SPAN_S = {"BASELINE": 50.0, "EXPOSURE": 105.0}
MODEL_VERSION = "coffee-rbf-ensemble-v5-train-20261028-20261030"
FEATURE_VERSION = "baseline-normalized-exposure-v2-time-window"
BROAD_POSITIVE_GATE = 0.25
FOCUSED_POSITIVE_GATE = 0.60
NEGATIVE_BROAD_GATE = 0.0
NEGATIVE_FOCUSED_GATE = 0.0
MODEL_C = 30.0
MODEL_GAMMA = 0.1
FOCUSED_MODEL_C = 10.0
FOCUSED_MODEL_GAMMA = 0.1

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
FOCUSED_SENSORS = ("mq135_1", "mq3_1")
FOCUSED_FEATURE_NAMES = tuple(
    f"{sensor}__{feature}"
    for sensor in FOCUSED_SENSORS
    for feature, _, _ in FEATURES
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


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def measurement_structure_quality(
    rows: list[dict[str, str]],
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    run_ids = {str(row.get("run_id", "")).strip() for row in rows}
    run_ids.discard("")
    if len(run_ids) > 1:
        errors.append(f"CSV chứa {len(run_ids)} run_id khác nhau")
    for phase in PHASES:
        indices = [index for index, row in enumerate(rows) if row.get("phase") == phase]
        if not indices:
            errors.append(f"Thiếu pha {phase}")
            continue
        segment_count = 1 + sum(
            current != previous + 1
            for previous, current in zip(indices, indices[1:])
        )
        if segment_count != 1:
            errors.append(f"Pha {phase} bị tách thành {segment_count} đoạn")
        elapsed = [parse_float(rows[index].get("phase_elapsed_s")) for index in indices]
        if any(value is None for value in elapsed):
            errors.append(f"Pha {phase} có thời gian không hợp lệ")
            continue
        times = [float(value) for value in elapsed if value is not None]
        if any(current < previous for previous, current in zip(times, times[1:])):
            errors.append(f"Thời gian pha {phase} quay ngược; có thể đã gộp nhiều chu kỳ")
            continue
        span = times[-1] - times[0]
        if span < MIN_PHASE_SPAN_S[phase]:
            errors.append(
                f"Pha {phase} chỉ phủ {span:.1f}s, cần ít nhất {MIN_PHASE_SPAN_S[phase]:.0f}s"
            )
        max_gap = max(
            (current - previous for previous, current in zip(times, times[1:])),
            default=0.0,
        )
        if max_gap > MAX_PHASE_GAP_S:
            errors.append(f"Pha {phase} có khoảng trống lấy mẫu {max_gap:.1f}s")
    return errors, warnings


def extract_features(path: Path) -> dict[str, object]:
    rows = read_raw(path)
    quality_errors, quality_warnings = measurement_structure_quality(rows)
    phase_rows = {
        phase: [row for row in rows if row.get("phase") == phase] for phase in PHASES
    }
    missing_phases = [phase for phase, values in phase_rows.items() if not values]
    if missing_phases:
        return {
            "features": {},
            "valid_fractions": {},
            "warnings": quality_warnings,
            "quality": {"passed": False, "errors": quality_errors},
            "row_count": len(rows),
        }

    features: dict[str, float] = {}
    valid_fractions: dict[str, dict[str, float]] = {}
    warnings: list[str] = list(quality_warnings)
    for sensor, config in SENSORS.items():
        baseline_values = [
            value
            for row in phase_rows["BASELINE"]
            if sensor_valid(row, sensor)
            and (value := parse_float(row.get(config["value"]))) is not None
        ]
        if not baseline_values:
            quality_errors.append(f"Không có BASELINE hợp lệ cho {config['label']}")
            continue
        baseline = statistics.median(baseline_values)
        if baseline == 0:
            quality_errors.append(f"BASELINE bằng 0 cho {config['label']}")
            continue
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
                quality_errors.append(
                    f"{config['label']} {phase} chỉ có {fraction:.1%} dữ liệu hợp lệ"
                )
        exposure = normalized["EXPOSURE"]
        values = [value for _, value in exposure]
        if not values:
            quality_errors.append(f"Không có EXPOSURE hợp lệ cho {config['label']}")
            continue
        middle = [value for elapsed, value in exposure if 40.0 <= elapsed < 80.0]
        expected_middle_rows = 40
        if len(middle) / expected_middle_rows < MIN_VALID_FRACTION:
            quality_errors.append(
                f"{config['label']} cửa sổ 40–80s chỉ có {len(middle)}/{expected_middle_rows} mẫu hợp lệ"
            )
            continue
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
        "quality": {"passed": not quality_errors, "errors": quality_errors},
        "row_count": len(rows),
    }


def metadata_status(directory: Path) -> str:
    path = directory / "metadata.json"
    if not path.is_file():
        return ""
    return str(json.loads(path.read_text(encoding="utf-8-sig")).get("status", ""))


def discover_training_rows(data_root: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
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

    day30 = data_root / "2026-10-30"
    for directory in day30.iterdir():
        if not directory.is_dir() or not (directory / "raw.csv").is_file():
            continue
        if metadata_status(directory) == "COMPLETE":
            name = directory.name.lower()
            if name.startswith("duongcaphe2_"):
                rows.append({"day": "2026-10-30", "directory": directory, "label": 1})
            elif name.startswith(("duong_", "dat_")):
                rows.append({"day": "2026-10-30", "directory": directory, "label": 0})
    return rows


def load_training_sessions(
    data_root: Path, excluded_raw: Path | None = None
) -> tuple[list[dict[str, object]], list[str]]:
    sessions = []
    skipped = []
    excluded_resolved = excluded_raw.resolve() if excluded_raw else None
    excluded_hash = file_sha256(excluded_raw) if excluded_raw and excluded_raw.is_file() else None
    seen_hashes: dict[str, tuple[str, int]] = {}
    for row in discover_training_rows(data_root):
        raw_path = Path(row["directory"]) / "raw.csv"
        measurement_hash = file_sha256(raw_path)
        if (
            excluded_resolved
            and (
                raw_path.resolve() == excluded_resolved
                or measurement_hash == excluded_hash
            )
        ):
            continue
        if measurement_hash in seen_hashes:
            duplicate_folder, duplicate_label = seen_hashes[measurement_hash]
            if duplicate_label != int(row["label"]):
                raise ValueError(
                    f"Xung đột nhãn: {Path(row['directory']).name} và "
                    f"{duplicate_folder} có cùng nội dung"
                )
            skipped.append(
                f"{Path(row['directory']).name}: trùng nội dung với {duplicate_folder}"
            )
            continue
        try:
            extracted = extract_features(raw_path)
        except ValueError as error:
            skipped.append(f"{Path(row['directory']).name}: {error}")
            continue
        quality = extracted["quality"]
        if not quality["passed"]:
            skipped.append(
                f"{Path(row['directory']).name}: " + "; ".join(quality["errors"])
            )
            continue
        seen_hashes[measurement_hash] = (
            Path(row["directory"]).name,
            int(row["label"]),
        )
        sessions.append(
            {
                "day": row["day"],
                "folder": Path(row["directory"]).name,
                "raw_path": raw_path,
                "label": int(row["label"]),
                "features": extracted["features"],
                "measurement_hash": measurement_hash,
            }
        )
    positive_count = sum(int(session["label"]) == 1 for session in sessions)
    negative_count = sum(int(session["label"]) == 0 for session in sessions)
    if positive_count < 3 or negative_count < 3:
        raise ValueError(
            f"Tập học không đủ: {negative_count} âm, {positive_count} dương"
        )
    return sessions, skipped


def feature_matrix(
    sessions: list[dict[str, object]], feature_names: tuple[str, ...] = FEATURE_NAMES
) -> np.ndarray:
    return np.asarray(
        [
            [float(session["features"][name]) for name in feature_names]
            for session in sessions
        ],
        dtype=float,
    )


def build_model(c: float = MODEL_C, gamma: float = MODEL_GAMMA) -> Pipeline:
    return Pipeline(
        [
            ("scale", StandardScaler()),
            (
                "svm",
                SVC(
                    C=c,
                    gamma=gamma,
                    kernel="rbf",
                    class_weight="balanced",
                ),
            ),
        ]
    )


def domain_diagnostics(
    model: Pipeline, x_train: np.ndarray, x_test: np.ndarray
) -> list[dict[str, object]]:
    scaler: StandardScaler = model.named_steps["scale"]
    standardized_train = scaler.transform(x_train)
    standardized_test = scaler.transform(x_test)
    train_nearest = []
    for index, row in enumerate(standardized_train):
        others = np.delete(standardized_train, index, axis=0)
        train_nearest.append(
            float(np.min(np.sqrt(np.mean((others - row) ** 2, axis=1))))
        )
    ood_threshold = float(np.quantile(train_nearest, 0.95) * 1.5)
    results = []
    for row in standardized_test:
        nearest_distance = float(
            np.min(np.sqrt(np.mean((standardized_train - row) ** 2, axis=1)))
        )
        max_abs_z = float(np.max(np.abs(row)))
        results.append(
            {
                "out_of_distribution": nearest_distance > ood_threshold
                or max_abs_z > 5.0,
                "nearest_training_distance": nearest_distance,
                "ood_threshold": ood_threshold,
                "max_abs_z": max_abs_z,
            }
        )
    return results


def training_manifest_hash(sessions: list[dict[str, object]]) -> str:
    manifest = sorted(
        (str(session["measurement_hash"]), int(session["label"]))
        for session in sessions
    )
    return hashlib.sha256(
        json.dumps(manifest, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]


def classify_scores(
    broad_score: float,
    focused_score: float,
    out_of_distribution: bool = False,
) -> tuple[str, str]:
    if out_of_distribution:
        return "OUT_OF_DOMAIN", "Mẫu nằm ngoài miền dữ liệu đã học"
    if (
        broad_score >= BROAD_POSITIVE_GATE
        and focused_score >= FOCUSED_POSITIVE_GATE
    ):
        return "COFFEE_ODOR_LIKELY", "Có khả năng có mùi cà phê"
    if (
        broad_score < NEGATIVE_BROAD_GATE
        and focused_score < NEGATIVE_FOCUSED_GATE
    ):
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
    extracted = extract_features(raw_path)
    quality = extracted["quality"]
    if not quality["passed"]:
        return {
            "input_file": str(raw_path),
            "prediction": "INVALID_MEASUREMENT",
            "prediction_vi": "Dữ liệu đo chưa đủ chất lượng để phân loại",
            "known_ground_truth": known_label,
            "known_ground_truth_vi": (
                "Có mùi cà phê" if known_label == 1 else "Không có mùi cà phê"
            )
            if known_label is not None
            else None,
            "evaluation_against_label": "INVALID",
            "decision_score": None,
            "focused_mq135_mq3_score": None,
            "quality": quality,
            "row_count": extracted["row_count"],
            "warnings": extracted["warnings"],
            "model_version": MODEL_VERSION,
            "feature_version": FEATURE_VERSION,
        }
    sessions, skipped = load_training_sessions(
        data_root, excluded_raw=raw_path if leave_one_out else None
    )
    x_train = feature_matrix(sessions)
    x_focused_train = feature_matrix(sessions, FOCUSED_FEATURE_NAMES)
    y_train = np.asarray([int(session["label"]) for session in sessions])
    x_input = np.asarray(
        [[float(extracted["features"][name]) for name in FEATURE_NAMES]], dtype=float
    )
    x_focused_input = np.asarray(
        [
            [float(extracted["features"][name]) for name in FOCUSED_FEATURE_NAMES]
        ],
        dtype=float,
    )
    model = build_model()
    model.fit(x_train, y_train)
    score = float(model.decision_function(x_input)[0])
    focused_model = build_model(FOCUSED_MODEL_C, FOCUSED_MODEL_GAMMA)
    focused_model.fit(x_focused_train, y_train)
    focused_score = float(focused_model.decision_function(x_focused_input)[0])

    domain = domain_diagnostics(model, x_train, x_input)[0]
    nearest_distance = float(domain["nearest_training_distance"])
    ood_threshold = float(domain["ood_threshold"])
    max_abs_z = float(domain["max_abs_z"])
    out_of_distribution = bool(domain["out_of_distribution"])
    prediction, prediction_vi = classify_scores(
        score, focused_score, out_of_distribution
    )
    if known_label is None:
        evaluation_against_label = None
    elif prediction in {"UNCERTAIN", "OUT_OF_DOMAIN"}:
        evaluation_against_label = "ABSTAIN"
    else:
        predicted_label = int(prediction == "COFFEE_ODOR_LIKELY")
        evaluation_against_label = "CORRECT" if predicted_label == known_label else "WRONG"

    svm: SVC = model.named_steps["svm"]
    reference_vector = np.median(x_train, axis=0).reshape(1, -1)
    contributions = []
    for index, name in enumerate(FEATURE_NAMES):
        perturbed = x_input.copy()
        perturbed[0, index] = reference_vector[0, index]
        perturbed_score = float(model.decision_function(perturbed)[0])
        score_delta = score - perturbed_score
        contributions.append(
            {
                "feature": name,
                "feature_label": feature_label(name),
                "value": float(x_input[0, index]),
                "score_delta_vs_reference": score_delta,
                "support_for_coffee": score_delta,
            }
        )
    contributions.sort(
        key=lambda row: abs(float(row["score_delta_vs_reference"])), reverse=True
    )
    sensor_support = []
    for sensor, config in SENSORS.items():
        indices = [
            index
            for index, name in enumerate(FEATURE_NAMES)
            if name.startswith(f"{sensor}__")
        ]
        modified = x_input.copy()
        modified[0, indices] = reference_vector[0, indices]
        group_delta = score - float(model.decision_function(modified)[0])
        sensor_support.append(
            {
                "sensor": sensor,
                "sensor_label": config["label"],
                "score_delta_vs_reference": group_delta,
                "support_for_coffee": group_delta,
                "exposure_mean": float(
                    extracted["features"][f"{sensor}__exposure_mean"]
                ),
                "slope_pct_per_min": float(
                    extracted["features"][f"{sensor}__slope_pct_per_min"]
                ),
            }
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
    if (score >= 0) != (focused_score >= 0):
        warnings.append(
            "Mô hình tổng và mô hình MQ135-1/MQ3-1 không đồng thuận"
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
        "focused_mq135_mq3_score": focused_score,
        "thresholds": {
            "coffee_broad": BROAD_POSITIVE_GATE,
            "coffee_focused_mq135_mq3": FOCUSED_POSITIVE_GATE,
            "no_coffee_broad": NEGATIVE_BROAD_GATE,
            "no_coffee_focused_mq135_mq3": NEGATIVE_FOCUSED_GATE,
        },
        "leave_one_out_for_known_file": leave_one_out,
        "out_of_distribution": out_of_distribution,
        "nearest_training_distance": nearest_distance,
        "ood_threshold": ood_threshold,
        "max_abs_z": max_abs_z,
        "row_count": extracted["row_count"],
        "features": extracted["features"],
        "quality": quality,
        "feature_support": contributions,
        "sensor_support": sensor_support,
        "valid_fractions": extracted["valid_fractions"],
        "warnings": warnings,
        "model_version": MODEL_VERSION,
        "feature_version": FEATURE_VERSION,
        "training_manifest_hash": training_manifest_hash(sessions),
        "training": {
            "sessions": len(sessions),
            "negative": int(np.sum(y_train == 0)),
            "positive": int(np.sum(y_train == 1)),
            "skipped": skipped,
            "model": "StandardScaler + RBF-SVM",
            "C": MODEL_C,
            "gamma": MODEL_GAMMA,
            "focused_model": "RBF-SVM trên MQ135-1 + MQ3-1",
            "focused_C": FOCUSED_MODEL_C,
            "focused_gamma": FOCUSED_MODEL_GAMMA,
            "support_vectors": int(len(svm.support_)),
            "positive_sessions_note": "Positive hiện thuộc các ngày 2026-10-28 và 2026-10-30",
        },
    }


def evaluate_scores(
    labels: np.ndarray,
    scores: np.ndarray,
    focused_scores: np.ndarray,
    out_of_distribution: np.ndarray,
) -> dict[str, object]:
    raw_predictions = (scores >= 0).astype(int)
    decisions = [
        classify_scores(float(score), float(focused_score), bool(is_ood))[0]
        for score, focused_score, is_ood in zip(
            scores, focused_scores, out_of_distribution
        )
    ]
    decisive_indices = [
        index
        for index, value in enumerate(decisions)
        if value not in {"UNCERTAIN", "OUT_OF_DOMAIN"}
    ]
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
        "out_of_distribution_count": int(np.sum(out_of_distribution)),
        "positive_detected": int(sum(
            decision == "COFFEE_ODOR_LIKELY" and label == 1
            for decision, label in zip(decisions, labels)
        )),
        "positive_missed_as_no_coffee": int(sum(
            decision == "NO_COFFEE_ODOR_LIKELY" and label == 1
            for decision, label in zip(decisions, labels)
        )),
        "positive_abstained": int(sum(
            decision in {"UNCERTAIN", "OUT_OF_DOMAIN"} and label == 1
            for decision, label in zip(decisions, labels)
        )),
        "negative_false_positive": int(sum(
            decision == "COFFEE_ODOR_LIKELY" and label == 0
            for decision, label in zip(decisions, labels)
        )),
        "decisions": decisions,
    }


def self_test(data_root: Path) -> dict[str, object]:
    sessions, skipped = load_training_sessions(data_root)
    x = feature_matrix(sessions)
    x_focused = feature_matrix(sessions, FOCUSED_FEATURE_NAMES)
    y = np.asarray([int(session["label"]) for session in sessions])
    loo_scores = []
    loo_focused_scores = []
    loo_domains = []
    for index in range(len(sessions)):
        mask = np.arange(len(sessions)) != index
        model = build_model()
        model.fit(x[mask], y[mask])
        loo_scores.append(float(model.decision_function(x[index : index + 1])[0]))
        focused_model = build_model(FOCUSED_MODEL_C, FOCUSED_MODEL_GAMMA)
        focused_model.fit(x_focused[mask], y[mask])
        loo_focused_scores.append(
            float(focused_model.decision_function(x_focused[index : index + 1])[0])
        )
        loo_domains.append(domain_diagnostics(model, x[mask], x[index : index + 1])[0])
    loo_scores_array = np.asarray(loo_scores)
    loo_focused_scores_array = np.asarray(loo_focused_scores)

    day_holdouts = {}
    for day in ("2026-10-28", "2026-10-30"):
        train_mask = np.asarray([session["day"] != day for session in sessions])
        test_mask = ~train_mask
        model = build_model()
        model.fit(x[train_mask], y[train_mask])
        scores = model.decision_function(x[test_mask])
        focused_model = build_model(FOCUSED_MODEL_C, FOCUSED_MODEL_GAMMA)
        focused_model.fit(x_focused[train_mask], y[train_mask])
        focused_scores = focused_model.decision_function(x_focused[test_mask])
        domains = domain_diagnostics(model, x[train_mask], x[test_mask])
        ood_flags = np.asarray(
            [bool(domain["out_of_distribution"]) for domain in domains]
        )
        day_holdouts[day] = {
            "labels": y[test_mask].tolist(),
            "scores": [float(value) for value in scores],
            "focused_scores": [float(value) for value in focused_scores],
            "out_of_distribution": ood_flags.tolist(),
            "evaluation": evaluate_scores(
                y[test_mask], scores, focused_scores, ood_flags
            ),
        }

    rows = []
    loo_ood_flags = np.asarray(
        [bool(domain["out_of_distribution"]) for domain in loo_domains]
    )
    evaluations = evaluate_scores(
        y, loo_scores_array, loo_focused_scores_array, loo_ood_flags
    )
    for session, truth, score, focused_score, domain, decision in zip(
        sessions,
        y,
        loo_scores,
        loo_focused_scores,
        loo_domains,
        evaluations["decisions"],
    ):
        rows.append(
            {
                "day": session["day"],
                "folder": session["folder"],
                "truth": int(truth),
                "score": score,
                "focused_score": focused_score,
                "out_of_distribution": domain["out_of_distribution"],
                "nearest_training_distance": domain["nearest_training_distance"],
                "ood_threshold": domain["ood_threshold"],
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
        "model_version": MODEL_VERSION,
        "feature_version": FEATURE_VERSION,
        "training_manifest_hash": training_manifest_hash(sessions),
        "warning": (
            "Tập học chỉ có hai ngày; holdout 2026-10-28 chỉ được huấn luyện từ "
            "bốn phiên của 2026-10-30 nên kết quả theo ngày còn biến động lớn."
        ),
    }


def print_prediction(result: dict[str, object]) -> None:
    print("=" * 68)
    print("KẾT QUẢ RBF-SVM KIỂM TRA MÙI CÀ PHÊ")
    print("=" * 68)
    print(f"Kết luận       : {result['prediction_vi']}")
    print(f"Mã kết quả     : {result['prediction']}")
    if result["prediction"] == "INVALID_MEASUREMENT":
        if result["known_ground_truth"] is not None:
            print(f"Ground truth   : {result['known_ground_truth_vi']}")
        print("Chất lượng     : KHÔNG ĐẠT")
        for error in result["quality"]["errors"]:
            print(f"  - {error}")
        print(f"Model version  : {result['model_version']}")
        print(f"Feature version: {result['feature_version']}")
        return
    if result["known_ground_truth"] is not None:
        print(f"Ground truth   : {result['known_ground_truth_vi']}")
        print(f"Đánh giá       : {result['evaluation_against_label']}")
    print(f"Decision score : {float(result['decision_score']):.3f}")
    print(
        "MQ135/MQ3 score: "
        f"{float(result['focused_mq135_mq3_score']):.3f} "
        "(mô hình phụ MQ135-1 + MQ3-1)"
    )
    print(
        f"Ngưỡng CÓ      : tổng >= {BROAD_POSITIVE_GATE:.2f} VÀ "
        f"MQ135/MQ3 >= {FOCUSED_POSITIVE_GATE:.2f}"
    )
    print(
        f"Ngưỡng KHÔNG   : tổng < {NEGATIVE_BROAD_GATE:.2f} VÀ "
        f"MQ135/MQ3 < {NEGATIVE_FOCUSED_GATE:.2f}"
    )
    print(f"Leave-one-out  : {'Có' if result['leave_one_out_for_known_file'] else 'Không'}")
    print(f"Ngoài miền học : {'Có' if result['out_of_distribution'] else 'Không'}")
    print("Chất lượng     : ĐẠT")
    print(f"Model version  : {result['model_version']}")
    print(f"Feature version: {result['feature_version']}")
    print(f"Manifest hash  : {result['training_manifest_hash']}")
    training = result["training"]
    print(
        f"Tập học        : {training['sessions']} phiên "
        f"({training['negative']} âm, {training['positive']} dương)"
    )
    print("\nTổng hợp theo từng cảm biến (xấp xỉ):")
    for row in result["sensor_support"]:
        score_delta = float(row["score_delta_vs_reference"])
        direction = "tăng" if score_delta > 0 else "giảm"
        print(
            f"  - {row['sensor_label']:<10}: nhóm hiện tại làm score "
            f"{direction} {abs(score_delta):.3f} so với median train; "
            f"mean {float(row['exposure_mean']):+.2f}%; "
            f"slope {float(row['slope_pct_per_min']):+.2f}%/min"
        )
    print("\nFeature ảnh hưởng mạnh nhất:")
    for row in result["feature_support"][:8]:
        score_delta = float(row["score_delta_vs_reference"])
        direction = "làm tăng score" if score_delta > 0 else "làm giảm score"
        print(
            f"  - {row['feature_label']}: {float(row['value']):.4f} – "
            f"{direction} {abs(score_delta):.3f} so với median train"
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
    print(f"Ngoài miền học trong LOOCV: {loo['out_of_distribution_count']}")
    print(
        "Dương tính: "
        f"phát hiện {loo['positive_detected']}/{result['positive']}; "
        f"kết luận nhầm KHÔNG {loo['positive_missed_as_no_coffee']}; "
        f"từ chối {loo['positive_abstained']}"
    )
    print(f"Âm tính bị báo nhầm CÓ: {loo['negative_false_positive']}")
    print("\nNgày | Nhãn | Tổng | MQ135/MQ3 | Quyết định | Folder")
    for row in result["rows"]:
        print(
            f"{str(row['day'])[-5:]:>5} | {row['truth']:>4} | "
            f"{float(row['score']):>5.2f} | {float(row['focused_score']):>9.2f} | "
            f"{row['decision']:<23} | {row['folder']}"
        )
    print("\nHoldout theo ngày:")
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
