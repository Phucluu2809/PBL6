"""Augment the 2026-10-25 odor runs and extract cosine-ready features.

The pipeline uses the three channels shared by the old and new logger schemas:
BME gas resistance, MQ135 voltage, and MQ3 voltage.
Augmentation is phase-preserving and conservative. Person prototypes are built
from real runs only; augmented samples never count as independent real runs.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data" / "2026-10-25"
DEFAULT_OUTPUT = ROOT / "data" / "2026-10-25_augmented"

PHASE_LENGTHS = {"BASELINE": 60, "EXPOSURE": 120, "RECOVERY": 60}
PHASES = tuple(PHASE_LENGTHS)
MIN_VALID_FRACTION = 0.90
MIN_IDENTITY_SIMILARITY = 0.60

SENSORS = {
    "gas": {
        "value": "gas_resistance_ohm",
        "status": "bme_status",
        "fresh": "bme_fresh",
    },
    "mq135": {
        "value": "mq135_voltage_v",
        "status": "mq135_status",
        "fresh": "mq135_fresh",
        "quality": "mq135_quality",
    },
    "mq3": {
        "value": "mq3_voltage_v",
        "status": "mq3_status",
        "fresh": "mq3_fresh",
        "quality": "mq3_quality",
    },
}

FEATURE_COLUMNS = [
    "gas_exposure_mean_pct",
    "gas_exposure_middle_mean_pct",
    "gas_exposure_q10_pct",
    "gas_exposure_q90_pct",
    "mq135_exposure_middle_mean_pct",
    "mq135_exposure_slope_pct_per_s",
    "mq135_recovery_end_mean_pct",
    "mq3_exposure_middle_mean_pct",
    "mq3_exposure_slope_pct_per_s",
    "mq3_recovery_end_mean_pct",
]
VECTOR_DIMENSIONS = len(FEATURE_COLUMNS)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create phase-preserving augmented odor signals and feature vectors."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--variants-per-run",
        type=int,
        default=20,
        help="Number of augmented variants generated from each accepted real run.",
    )
    parser.add_argument("--seed", type=int, default=20261025)
    return parser.parse_args()


def parse_bool(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def parse_float(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def normalize_sensor_columns(rows: list[dict[str, str]]) -> None:
    """Map the newer *_1 logger columns onto the original sensor names."""
    suffixes = (
        "read_started_at",
        "read_elapsed_s",
        "read_duration_s",
        "status",
        "error",
        "fresh",
        "adc_count",
        "voltage_v",
        "ao_voltage_v",
        "quality",
    )
    for row in rows:
        for sensor in ("mq135", "mq3"):
            for suffix in suffixes:
                canonical = f"{sensor}_{suffix}"
                versioned = f"{sensor}_1_{suffix}"
                if row.get(canonical) in {None, ""} and row.get(versioned) not in {
                    None,
                    "",
                }:
                    row[canonical] = row[versioned]


def mean(values: Iterable[float]) -> float:
    items = list(values)
    return statistics.fmean(items) if items else math.nan


def standard_deviation(values: Iterable[float]) -> float:
    items = list(values)
    if len(items) < 2:
        return 0.0
    center = mean(items)
    return math.sqrt(sum((value - center) ** 2 for value in items) / len(items))


def percentile(values: Iterable[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return math.nan
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def linear_slope(values: list[float]) -> float:
    if len(values) < 2:
        return math.nan
    x_center = (len(values) - 1) / 2
    y_center = mean(values)
    denominator = sum((index - x_center) ** 2 for index in range(len(values)))
    return (
        sum((index - x_center) * (value - y_center) for index, value in enumerate(values))
        / denominator
    )


def canonical_person(folder_name: str) -> str:
    raw = folder_name.split("_", 1)[0]
    aliases = {"adung": "Dung", "aminh": "Minh", "aquy": "Quy", "tai": "Tai"}
    return aliases.get(raw.lower(), raw)


def sensor_value_is_valid(row: dict[str, str], sensor: str) -> bool:
    config = SENSORS[sensor]
    if parse_float(row.get(config["value"])) is None:
        return False
    if row.get(config["status"]) != "OK" or not parse_bool(row.get(config["fresh"])):
        return False
    if sensor == "gas":
        return all(
            parse_bool(row.get(column))
            for column in ("gas_valid", "heater_stable", "new_data")
        )
    return row.get(config["quality"]) in {"", None, "OK"}


def interpolate_at(points: list[tuple[float, float]], target: float) -> float:
    if target <= points[0][0]:
        return points[0][1]
    if target >= points[-1][0]:
        return points[-1][1]
    left = 0
    right = len(points) - 1
    while right - left > 1:
        middle = (left + right) // 2
        if points[middle][0] <= target:
            left = middle
        else:
            right = middle
    left_x, left_y = points[left]
    right_x, right_y = points[right]
    if right_x == left_x:
        return left_y
    weight = (target - left_x) / (right_x - left_x)
    return left_y * (1 - weight) + right_y * weight


def resample(points: list[tuple[float, float]], length: int) -> list[float]:
    points = sorted(points)
    if len(points) == 1:
        return [points[0][1]] * length
    start, end = points[0][0], points[-1][0]
    if end <= start:
        return [points[0][1]] * length
    return [
        interpolate_at(points, start + (end - start) * index / (length - 1))
        for index in range(length)
    ]


def load_run(directory: Path) -> tuple[dict[str, object] | None, dict[str, object]]:
    with (directory / "raw.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    normalize_sensor_columns(rows)
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))

    quality: dict[str, object] = {
        "source_run": directory.name,
        "source_run_id": metadata.get("run_id", ""),
        "person": canonical_person(directory.name),
        "accepted": True,
        "rejection_reasons": "",
    }
    reasons: list[str] = []
    phase_signals: dict[str, dict[str, list[float]]] = defaultdict(dict)

    for sensor, config in SENSORS.items():
        for phase_name, target_length in PHASE_LENGTHS.items():
            phase_rows = [row for row in rows if row.get("phase") == phase_name]
            valid_points = []
            for row in phase_rows:
                if not sensor_value_is_valid(row, sensor):
                    continue
                elapsed = parse_float(row.get("phase_elapsed_s"))
                value = parse_float(row.get(config["value"]))
                if elapsed is not None and value is not None:
                    valid_points.append((elapsed, value))
            fraction = len(valid_points) / max(len(phase_rows), target_length, 1)
            quality[f"{sensor}_{phase_name.lower()}_valid_fraction"] = fraction
            if fraction < MIN_VALID_FRACTION:
                reasons.append(f"{sensor}:{phase_name}:valid={fraction:.3f}")
                continue
            phase_signals[sensor][phase_name] = resample(valid_points, target_length)

    if metadata.get("baseline_unstable") is True:
        reasons.append("baseline_unstable")

    if reasons:
        quality["accepted"] = False
        quality["rejection_reasons"] = " | ".join(reasons)
        return None, quality

    normalized: dict[str, dict[str, list[float]]] = defaultdict(dict)
    baselines: dict[str, float] = {}
    for sensor in SENSORS:
        baseline = statistics.median(phase_signals[sensor]["BASELINE"])
        baselines[sensor] = baseline
        denominator = abs(baseline)
        for phase_name in PHASES:
            normalized[sensor][phase_name] = [
                100 * (value - baseline) / denominator
                for value in phase_signals[sensor][phase_name]
            ]

    run = {
        "source_run": directory.name,
        "source_run_id": metadata.get("run_id", ""),
        "person": canonical_person(directory.name),
        "signals": normalized,
        "baseline_values": baselines,
    }
    return run, quality


def sequence_at(sequence: list[float], coordinate: float) -> float:
    if coordinate <= 0:
        return sequence[0]
    if coordinate >= len(sequence) - 1:
        return sequence[-1]
    left = int(math.floor(coordinate))
    right = left + 1
    weight = coordinate - left
    return sequence[left] * (1 - weight) + sequence[right] * weight


def warp_sequence(
    sequence: list[float], time_scale: float, shift_samples: int
) -> list[float]:
    center = (len(sequence) - 1) / 2
    return [
        sequence_at(sequence, center + (index - center) / time_scale - shift_samples)
        for index in range(len(sequence))
    ]


def shifted_residual_noise(
    baseline: list[float], length: int, rng: random.Random
) -> list[float]:
    centered = [value - mean(baseline) for value in baseline]
    offset = rng.randrange(len(centered))
    return [centered[(offset + index) % len(centered)] for index in range(length)]


def make_sample(
    run: dict[str, object], variant_index: int, rng: random.Random
) -> dict[str, object]:
    is_augmented = variant_index > 0
    amplitude_scale = rng.uniform(0.97, 1.03) if is_augmented else 1.0
    time_scale = rng.uniform(0.98, 1.02) if is_augmented else 1.0
    shift_samples = rng.randint(-2, 2) if is_augmented else 0
    noise_scale = rng.uniform(0.10, 0.30) if is_augmented else 0.0
    signals = run["signals"]
    augmented: dict[str, dict[str, list[float]]] = defaultdict(dict)

    for sensor in SENSORS:
        baseline = signals[sensor]["BASELINE"]
        for phase_name in PHASES:
            source = signals[sensor][phase_name]
            warped = warp_sequence(source, time_scale, shift_samples) if is_augmented else list(source)
            noise = shifted_residual_noise(baseline, len(source), rng) if is_augmented else [0.0] * len(source)
            augmented[sensor][phase_name] = [
                amplitude_scale * value + noise_scale * residual
                for value, residual in zip(warped, noise)
            ]

    sample_id = f"{run['source_run']}__v{variant_index:03d}"
    return {
        "sample_id": sample_id,
        "person": run["person"],
        "source_run": run["source_run"],
        "source_run_id": run["source_run_id"],
        "variant_index": variant_index,
        "is_augmented": is_augmented,
        "amplitude_scale": amplitude_scale,
        "time_scale": time_scale,
        "time_shift_samples": shift_samples,
        "noise_scale": noise_scale,
        "signals": augmented,
    }


def extract_features(sample: dict[str, object]) -> dict[str, object]:
    signals = sample["signals"]
    gas_exposure = signals["gas"]["EXPOSURE"]
    mq135_exposure = signals["mq135"]["EXPOSURE"]
    mq135_recovery = signals["mq135"]["RECOVERY"]
    mq3_exposure = signals["mq3"]["EXPOSURE"]
    mq3_recovery = signals["mq3"]["RECOVERY"]
    gas_third = len(gas_exposure) // 3
    mq135_third = len(mq135_exposure) // 3
    mq3_third = len(mq3_exposure) // 3

    row = {
        key: sample[key]
        for key in (
            "sample_id",
            "person",
            "source_run",
            "source_run_id",
            "variant_index",
            "is_augmented",
            "amplitude_scale",
            "time_scale",
            "time_shift_samples",
            "noise_scale",
        )
    }
    row.update(
        {
            "gas_exposure_mean_pct": mean(gas_exposure),
            "gas_exposure_middle_mean_pct": mean(
                gas_exposure[gas_third : 2 * gas_third]
            ),
            "gas_exposure_q10_pct": percentile(gas_exposure, 0.10),
            "gas_exposure_q90_pct": percentile(gas_exposure, 0.90),
            "mq135_exposure_middle_mean_pct": mean(
                mq135_exposure[mq135_third : 2 * mq135_third]
            ),
            "mq135_exposure_slope_pct_per_s": linear_slope(mq135_exposure),
            "mq135_recovery_end_mean_pct": mean(mq135_recovery[-10:]),
            "mq3_exposure_middle_mean_pct": mean(
                mq3_exposure[mq3_third : 2 * mq3_third]
            ),
            "mq3_exposure_slope_pct_per_s": linear_slope(mq3_exposure),
            "mq3_recovery_end_mean_pct": mean(mq3_recovery[-10:]),
        }
    )
    return row


def fit_scaler(feature_rows: list[dict[str, object]]) -> dict[str, dict[str, float]]:
    real_rows = [row for row in feature_rows if not row["is_augmented"]]
    return {
        feature: {
            "mean": mean(float(row[feature]) for row in real_rows),
            "std": standard_deviation(float(row[feature]) for row in real_rows) or 1.0,
        }
        for feature in FEATURE_COLUMNS
    }


def add_cosine_vector(
    row: dict[str, object], scaler: dict[str, dict[str, float]]
) -> None:
    standardized = [
        (float(row[feature]) - scaler[feature]["mean"]) / scaler[feature]["std"]
        for feature in FEATURE_COLUMNS
    ]
    norm = math.sqrt(sum(value * value for value in standardized)) or 1.0
    for index, (feature, value) in enumerate(zip(FEATURE_COLUMNS, standardized), start=1):
        row[f"z_{feature}"] = value
        row[f"v_{index:02d}"] = value / norm


def build_prototypes(feature_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    real_rows = [row for row in feature_rows if not row["is_augmented"]]
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in real_rows:
        grouped[str(row["person"])].append(row)

    prototypes = []
    for person, rows in sorted(grouped.items()):
        vector = [
            mean(float(row[f"v_{index:02d}"]) for row in rows)
            for index in range(1, VECTOR_DIMENSIONS + 1)
        ]
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        prototype: dict[str, object] = {
            "person": person,
            "real_run_count": len(rows),
            "prototype_source": "real_runs_only",
        }
        for index, value in enumerate(vector, start=1):
            prototype[f"v_{index:02d}"] = value / norm
        prototypes.append(prototype)
    return prototypes


def row_vector(row: dict[str, object]) -> list[float]:
    return [
        float(row[f"v_{index:02d}"])
        for index in range(1, VECTOR_DIMENSIONS + 1)
    ]


def unit_vector(values: Iterable[float]) -> list[float]:
    vector = list(values)
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(unit_vector(left), unit_vector(right)))


def build_identity_model(
    feature_rows: list[dict[str, object]], seed: int
) -> tuple[dict[str, object], list[dict[str, object]]]:
    by_source: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in feature_rows:
        by_source[(str(row["person"]), str(row["source_run"]))].append(row)

    source_centroids: dict[str, list[tuple[str, list[float]]]] = defaultdict(list)
    for (person, source_run), rows in sorted(by_source.items()):
        centroid = unit_vector(
            mean(row_vector(row)[dimension] for row in rows)
            for dimension in range(VECTOR_DIMENSIONS)
        )
        source_centroids[person].append((source_run, centroid))

    person_centroids = {
        person: unit_vector(
            mean(vector[dimension] for _, vector in centroids)
            for dimension in range(VECTOR_DIMENSIONS)
        )
        for person, centroids in source_centroids.items()
    }

    profiles = []
    profile_rows = []
    people = sorted(person_centroids)
    for person in people:
        centroid = person_centroids[person]
        own_rows = [row for row in feature_rows if row["person"] == person]
        other_rows = [row for row in feature_rows if row["person"] != person]
        genuine = [cosine(row_vector(row), centroid) for row in own_rows]
        impostor = [cosine(row_vector(row), centroid) for row in other_rows]
        margins = []
        for row in own_rows:
            sample = row_vector(row)
            own_score = cosine(sample, centroid)
            best_other = max(
                cosine(sample, person_centroids[other])
                for other in people
                if other != person
            )
            margins.append(own_score - best_other)

        genuine_p05 = percentile(genuine, 0.05)
        impostor_max = max(impostor)
        separable = genuine_p05 > impostor_max
        calibrated_threshold = (
            (genuine_p05 + impostor_max) / 2 if separable else genuine_p05
        )
        similarity_threshold = max(MIN_IDENTITY_SIMILARITY, calibrated_threshold)
        margin_threshold = max(0.0, percentile(margins, 0.05))
        profile = {
            "person": person,
            "vector": centroid,
            "real_run_count": len(source_centroids[person]),
            "source_runs": [source for source, _ in source_centroids[person]],
            "augmented_sample_count": sum(bool(row["is_augmented"]) for row in own_rows),
            "total_sample_count": len(own_rows),
            "genuine_similarity_min": min(genuine),
            "genuine_similarity_p05": genuine_p05,
            "genuine_similarity_median": statistics.median(genuine),
            "impostor_similarity_max": impostor_max,
            "impostor_similarity_p95": percentile(impostor, 0.95),
            "similarity_threshold": similarity_threshold,
            "margin_threshold": margin_threshold,
            "training_separable": separable,
        }
        profiles.append(profile)
        flat_profile = {
            key: value
            for key, value in profile.items()
            if key not in {"vector", "source_runs"}
        }
        flat_profile["source_runs"] = " | ".join(profile["source_runs"])
        for index, value in enumerate(centroid, start=1):
            flat_profile[f"v_{index:02d}"] = value
        profile_rows.append(flat_profile)

    model = {
        "schema_version": 2,
        "model_type": "source-balanced cosine identity profiles",
        "feature_order": FEATURE_COLUMNS,
        "vector_columns": [
            f"v_{index:02d}" for index in range(1, VECTOR_DIMENSIONS + 1)
        ],
        "seed": seed,
        "centroid_policy": (
            "Average variants within each source run, L2-normalize, then average source "
            "centroids per person with equal source-run weight."
        ),
        "threshold_policy": (
            "Use the midpoint between own p05 and maximum impostor similarity when "
            "separable; otherwise use own p05 and mark training_separable=false. "
            f"Never use a cosine threshold below {MIN_IDENTITY_SIMILARITY:.2f}."
        ),
        "calibration_warning": (
            "Thresholds are estimated from augmented training data and are provisional "
            "until validated on independent real sessions."
        ),
        "profiles": profiles,
    }
    return model, profile_rows


def write_csv(path: Path, rows: list[dict[str, object]], columns: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def signal_rows(samples: list[dict[str, object]]) -> Iterable[dict[str, object]]:
    for sample in samples:
        common = {
            key: sample[key]
            for key in (
                "sample_id",
                "person",
                "source_run",
                "source_run_id",
                "variant_index",
                "is_augmented",
                "amplitude_scale",
                "time_scale",
                "time_shift_samples",
                "noise_scale",
            )
        }
        for phase_name in PHASES:
            length = PHASE_LENGTHS[phase_name]
            for index in range(length):
                yield {
                    **common,
                    "phase": phase_name,
                    "phase_index": index,
                    "phase_elapsed_s": float(index),
                    "gas_response_pct": sample["signals"]["gas"][phase_name][index],
                    "mq135_response_pct": sample["signals"]["mq135"][phase_name][index],
                    "mq3_response_pct": sample["signals"]["mq3"][phase_name][index],
                }


def write_readme(
    output: Path,
    accepted_runs: int,
    rejected_runs: int,
    samples: list[dict[str, object]],
    signal_row_count: int,
) -> None:
    class_counts = Counter(str(sample["person"]) for sample in samples)
    text = f"""# Dữ liệu mùi đã làm giàu

- Nguồn: `data/2026-10-25/`
- Phiên thật đạt kiểm tra chất lượng: {accepted_runs}
- Phiên bị loại: {rejected_runs}
- Tổng mẫu gồm bản thật và augmented: {len(samples)}
- Tổng dòng tín hiệu: {signal_row_count}
- Số mẫu theo người: {dict(sorted(class_counts.items()))}

## Tệp đầu ra

- `augmented_signals.csv`: tín hiệu đã chuẩn hóa baseline, cố định 60/120/60 mẫu cho BASELINE/EXPOSURE/RECOVERY.
- `feature_vectors.csv`: mười đặc trưng gốc, z-score và vector `v_01..v_10` đã chuẩn hóa L2 để tính cosine similarity.
- `person_prototypes.csv`: vector đại diện tính từ các phiên thật, không dùng bản augmented như phiên độc lập.
- `identity_profiles.csv`: centroid cân bằng theo phiên và ngưỡng cosine/margin của từng người.
- `identity_model.json`: model vector hoàn chỉnh để kiểm tra một mẫu mới có phù hợp hay không.
- `run_quality.csv`: kết quả kiểm tra chất lượng và lý do loại phiên.
- `scaler.json`: mean/std học từ các phiên thật để áp dụng cho mẫu mới.
- `manifest.json`: cấu hình tái lập pipeline.

## Augmentation

Mỗi biến thể dùng cùng hệ số cho cả ba cảm biến: amplitude scaling 0.97–1.03, time stretching 0.98–1.02, dịch ±2 mẫu và cộng 0.10–0.30 lần residual noise của baseline. Các pha không bị đảo hoặc trộn.

## Lưu ý

Ba người Dung, Minh và Quy chỉ có một phiên thật. Các mẫu augmented không thay thế được phiên đo thật và không được dùng để chia ngẫu nhiên giữa train/test nếu cùng `source_run`.
"""
    (output / "README.md").write_text(text, encoding="utf-8")


def main() -> None:
    args = parse_args()
    if args.variants_per_run < 0:
        raise ValueError("--variants-per-run must be non-negative")
    input_dir = args.input.resolve()
    output_dir = args.output.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    accepted_runs = []
    quality_rows = []
    for directory in sorted(
        path
        for path in input_dir.iterdir()
        if path.is_dir() and (path / "raw.csv").is_file()
    ):
        run, quality = load_run(directory)
        quality_rows.append(quality)
        if run is not None:
            accepted_runs.append(run)

    samples = []
    for run_index, run in enumerate(accepted_runs):
        run_rng = random.Random(args.seed + run_index * 100_003)
        for variant_index in range(args.variants_per_run + 1):
            samples.append(make_sample(run, variant_index, run_rng))

    feature_rows = [extract_features(sample) for sample in samples]
    scaler = fit_scaler(feature_rows)
    for row in feature_rows:
        add_cosine_vector(row, scaler)
    prototypes = build_prototypes(feature_rows)
    identity_model, identity_profiles = build_identity_model(feature_rows, args.seed)

    signal_columns = [
        "sample_id",
        "person",
        "source_run",
        "source_run_id",
        "variant_index",
        "is_augmented",
        "phase",
        "phase_index",
        "phase_elapsed_s",
        "gas_response_pct",
        "mq135_response_pct",
        "mq3_response_pct",
        "amplitude_scale",
        "time_scale",
        "time_shift_samples",
        "noise_scale",
    ]
    signal_table = list(signal_rows(samples))
    write_csv(output_dir / "augmented_signals.csv", signal_table, signal_columns)

    provenance_columns = [
        "sample_id",
        "person",
        "source_run",
        "source_run_id",
        "variant_index",
        "is_augmented",
        "amplitude_scale",
        "time_scale",
        "time_shift_samples",
        "noise_scale",
    ]
    standardized_columns = [f"z_{feature}" for feature in FEATURE_COLUMNS]
    vector_columns = [
        f"v_{index:02d}" for index in range(1, VECTOR_DIMENSIONS + 1)
    ]
    write_csv(
        output_dir / "feature_vectors.csv",
        feature_rows,
        provenance_columns + FEATURE_COLUMNS + standardized_columns + vector_columns,
    )
    write_csv(
        output_dir / "person_prototypes.csv",
        prototypes,
        ["person", "real_run_count", "prototype_source"] + vector_columns,
    )
    profile_columns = [
        "person",
        "real_run_count",
        "source_runs",
        "augmented_sample_count",
        "total_sample_count",
        "genuine_similarity_min",
        "genuine_similarity_p05",
        "genuine_similarity_median",
        "impostor_similarity_max",
        "impostor_similarity_p95",
        "similarity_threshold",
        "margin_threshold",
        "training_separable",
    ] + vector_columns
    write_csv(
        output_dir / "identity_profiles.csv",
        identity_profiles,
        profile_columns,
    )
    (output_dir / "identity_model.json").write_text(
        json.dumps(identity_model, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    quality_columns = [
        "source_run",
        "source_run_id",
        "person",
        "accepted",
        "rejection_reasons",
    ] + [
        f"{sensor}_{phase.lower()}_valid_fraction"
        for sensor in SENSORS
        for phase in PHASES
    ]
    write_csv(output_dir / "run_quality.csv", quality_rows, quality_columns)

    (output_dir / "scaler.json").write_text(
        json.dumps(
            {
                "feature_order": FEATURE_COLUMNS,
                "fit_source": "accepted_real_runs_only",
                "statistics": scaler,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input": str(input_dir),
        "output": str(output_dir),
        "seed": args.seed,
        "variants_per_run": args.variants_per_run,
        "minimum_valid_fraction": MIN_VALID_FRACTION,
        "minimum_identity_similarity": MIN_IDENTITY_SIMILARITY,
        "phase_lengths": PHASE_LENGTHS,
        "selected_sensors": SENSORS,
        "feature_order": FEATURE_COLUMNS,
        "accepted_real_runs": [run["source_run"] for run in accepted_runs],
        "rejected_real_runs": [
            row["source_run"] for row in quality_rows if not row["accepted"]
        ],
        "sample_count": len(samples),
        "signal_row_count": len(signal_table),
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_readme(
        output_dir,
        accepted_runs=len(accepted_runs),
        rejected_runs=len(quality_rows) - len(accepted_runs),
        samples=samples,
        signal_row_count=len(signal_table),
    )

    print(f"Accepted real runs: {len(accepted_runs)}")
    print(f"Rejected real runs: {len(quality_rows) - len(accepted_runs)}")
    print(f"Samples written: {len(samples)}")
    print(f"Signal rows written: {len(signal_table)}")
    print(f"Output: {output_dir}")


if __name__ == "__main__":
    main()
