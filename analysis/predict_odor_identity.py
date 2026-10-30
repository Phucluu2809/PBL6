"""Extract a feature vector from a new odor run and rank known people by cosine."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from pathlib import Path

from augment_and_extract_odor_features import (
    FEATURE_COLUMNS,
    MIN_VALID_FRACTION,
    PHASE_LENGTHS,
    PHASES,
    ROOT,
    SENSORS,
    add_cosine_vector,
    extract_features,
    normalize_sensor_columns,
    parse_float,
    resample,
    sensor_value_is_valid,
)


DEFAULT_MODEL_DIR = ROOT / "data" / "2026-10-25_augmented"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Identify a new odor run using the saved scaler and cosine prototypes."
    )
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="A raw.csv file or a run directory containing raw.csv.",
    )
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument(
        "--output",
        type=Path,
        help="Prediction JSON path. Defaults beside the input raw.csv.",
    )
    parser.add_argument(
        "--reject-below",
        type=float,
        help="Optional minimum cosine similarity. Omit until a threshold is calibrated.",
    )
    parser.add_argument(
        "--min-margin",
        type=float,
        help="Optional minimum gap between the best and second-best cosine scores.",
    )
    return parser.parse_args()


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    normalize_sensor_columns(rows)
    return rows


def resolve_input(path: Path) -> tuple[Path, Path]:
    resolved = path.resolve()
    if resolved.is_dir():
        raw_path = resolved / "raw.csv"
        run_dir = resolved
    else:
        raw_path = resolved
        run_dir = resolved.parent
    if not raw_path.is_file():
        raise FileNotFoundError(f"Cannot find raw.csv: {raw_path}")
    return raw_path, run_dir


def prepare_sample(rows: list[dict[str, str]], source_name: str) -> tuple[dict[str, object] | None, dict[str, object]]:
    quality: dict[str, object] = {
        "minimum_valid_fraction": MIN_VALID_FRACTION,
        "accepted": True,
        "reasons": [],
    }
    phase_signals: dict[str, dict[str, list[float]]] = {
        sensor: {} for sensor in SENSORS
    }
    reasons: list[str] = []

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
            valid_fraction = len(valid_points) / max(len(phase_rows), target_length, 1)
            quality[f"{sensor}_{phase_name.lower()}_valid_fraction"] = valid_fraction
            if not phase_rows:
                reasons.append(f"missing_phase:{phase_name}")
            elif valid_fraction < MIN_VALID_FRACTION:
                reasons.append(
                    f"{sensor}:{phase_name}:valid={valid_fraction:.3f}"
                )
            else:
                phase_signals[sensor][phase_name] = resample(
                    valid_points, target_length
                )

    if reasons:
        quality["accepted"] = False
        quality["reasons"] = sorted(set(reasons))
        return None, quality

    normalized: dict[str, dict[str, list[float]]] = {
        sensor: {} for sensor in SENSORS
    }
    baseline_values = {}
    for sensor in SENSORS:
        baseline = statistics.median(phase_signals[sensor]["BASELINE"])
        baseline_values[sensor] = baseline
        denominator = abs(baseline)
        if denominator == 0:
            quality["accepted"] = False
            quality["reasons"] = [f"{sensor}:zero_baseline"]
            return None, quality
        for phase_name in PHASES:
            normalized[sensor][phase_name] = [
                100 * (value - baseline) / denominator
                for value in phase_signals[sensor][phase_name]
            ]

    run_id = rows[0].get("run_id", "") if rows else ""
    sample = {
        "sample_id": f"new__{run_id or source_name}",
        "person": "UNKNOWN",
        "source_run": source_name,
        "source_run_id": run_id,
        "variant_index": 0,
        "is_augmented": False,
        "amplitude_scale": 1.0,
        "time_scale": 1.0,
        "time_shift_samples": 0,
        "noise_scale": 0.0,
        "signals": normalized,
    }
    quality["baseline_values"] = baseline_values
    return sample, quality


def cosine(left: list[float], right: list[float]) -> float:
    denominator = math.sqrt(
        sum(value * value for value in left)
        * sum(value * value for value in right)
    )
    return (
        sum(a * b for a, b in zip(left, right)) / denominator
        if denominator
        else 0.0
    )


def load_model(
    model_dir: Path,
) -> tuple[dict[str, object], list[dict[str, object]], dict[str, object]]:
    scaler_path = model_dir / "scaler.json"
    identity_model_path = model_dir / "identity_model.json"
    prototype_path = model_dir / "person_prototypes.csv"
    if not scaler_path.is_file():
        raise FileNotFoundError(f"Missing scaler.json in {model_dir}")
    if not identity_model_path.is_file() and not prototype_path.is_file():
        raise FileNotFoundError(
            f"Missing identity_model.json and person_prototypes.csv in {model_dir}"
        )
    scaler_document = json.loads(scaler_path.read_text(encoding="utf-8"))
    if scaler_document.get("feature_order") != FEATURE_COLUMNS:
        raise ValueError("Feature order in scaler.json does not match the predictor")
    if identity_model_path.is_file():
        identity_model = json.loads(identity_model_path.read_text(encoding="utf-8"))
        if identity_model.get("feature_order") != FEATURE_COLUMNS:
            raise ValueError("Feature order in identity_model.json does not match")
        metadata = {
            "source": "identity_model.json",
            "has_automatic_thresholds": True,
            "calibration_warning": identity_model.get("calibration_warning"),
        }
        return scaler_document["statistics"], identity_model["profiles"], metadata
    metadata = {
        "source": "person_prototypes.csv",
        "has_automatic_thresholds": False,
        "calibration_warning": "No automatic compatibility thresholds are available.",
    }
    return scaler_document["statistics"], load_csv(prototype_path), metadata


def prototype_vector(row: dict[str, object]) -> list[float]:
    if "vector" in row:
        return [float(value) for value in row["vector"]]
    return [
        float(row[f"v_{index:02d}"])
        for index in range(1, len(FEATURE_COLUMNS) + 1)
    ]


def default_output(raw_path: Path, run_dir: Path) -> Path:
    if raw_path.name.lower() == "raw.csv":
        return run_dir / "prediction.json"
    return raw_path.with_name(f"{raw_path.stem}_prediction.json")


def write_result(path: Path, result: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def main() -> None:
    args = parse_args()
    raw_path, run_dir = resolve_input(args.input)
    output_path = args.output.resolve() if args.output else default_output(raw_path, run_dir)
    rows = load_csv(raw_path)
    sample, quality = prepare_sample(rows, run_dir.name)

    if sample is None:
        result = {
            "status": "quality_rejected",
            "input": str(raw_path),
            "quality": quality,
            "prediction": None,
        }
        write_result(output_path, result)
        print("QUALITY_REJECTED")
        print("Reasons:", " | ".join(quality["reasons"]))
        print("Output:", output_path)
        raise SystemExit(2)

    scaler, prototypes, model_metadata = load_model(args.model_dir.resolve())
    feature_row = extract_features(sample)
    add_cosine_vector(feature_row, scaler)
    sample_vector = [
        float(feature_row[f"v_{index:02d}"])
        for index in range(1, len(FEATURE_COLUMNS) + 1)
    ]

    scores = []
    for prototype in prototypes:
        similarity = cosine(sample_vector, prototype_vector(prototype))
        scores.append(
            {
                "person": prototype["person"],
                "cosine_similarity": similarity,
                "l2_distance": math.sqrt(max(0.0, 2 - 2 * similarity)),
                "real_run_count": int(prototype["real_run_count"]),
                "model_similarity_threshold": (
                    float(prototype["similarity_threshold"])
                    if "similarity_threshold" in prototype
                    else None
                ),
                "model_margin_threshold": (
                    float(prototype["margin_threshold"])
                    if "margin_threshold" in prototype
                    else None
                ),
                "training_separable": prototype.get("training_separable"),
            }
        )
    scores.sort(key=lambda item: item["cosine_similarity"], reverse=True)
    best = scores[0]
    second = scores[1]
    margin = best["cosine_similarity"] - second["cosine_similarity"]

    automatic_similarity_threshold = best["model_similarity_threshold"]
    automatic_margin_threshold = best["model_margin_threshold"]
    similarity_threshold = (
        args.reject_below
        if args.reject_below is not None
        else automatic_similarity_threshold
    )
    margin_threshold = (
        args.min_margin
        if args.min_margin is not None
        else automatic_margin_threshold
    )

    rejection_reasons = []
    if similarity_threshold is not None and best["cosine_similarity"] < similarity_threshold:
        rejection_reasons.append(
            f"best_similarity<{similarity_threshold:.3f}"
        )
    if margin_threshold is not None and margin < margin_threshold:
        rejection_reasons.append(f"margin<{margin_threshold:.3f}")

    if rejection_reasons:
        status = "identity_rejected"
        predicted_person = None
    elif similarity_threshold is None and margin_threshold is None:
        status = "ranked_match_only"
        predicted_person = best["person"]
    else:
        status = "identity_accepted"
        predicted_person = best["person"]

    result = {
        "status": status,
        "input": str(raw_path),
        "model_dir": str(args.model_dir.resolve()),
        "model": model_metadata,
        "quality": quality,
        "prediction": {
            "person": predicted_person,
            "best_match": best["person"],
            "best_cosine_similarity": best["cosine_similarity"],
            "second_match": second["person"],
            "second_cosine_similarity": second["cosine_similarity"],
            "margin": margin,
            "similarity_threshold": similarity_threshold,
            "margin_threshold": margin_threshold,
            "threshold_source": (
                "command_line"
                if args.reject_below is not None or args.min_margin is not None
                else (
                    "augmented_identity_model"
                    if model_metadata["has_automatic_thresholds"]
                    else None
                )
            ),
            "rejection_reasons": rejection_reasons,
            "threshold_warning": model_metadata["calibration_warning"],
        },
        "scores": scores,
        "feature_order": FEATURE_COLUMNS,
        "raw_features": {
            feature: float(feature_row[feature]) for feature in FEATURE_COLUMNS
        },
        "cosine_vector": sample_vector,
    }
    write_result(output_path, result)

    print("STATUS:", status)
    print("BEST_MATCH:", best["person"])
    print("COSINE:", f"{best['cosine_similarity']:.6f}")
    print("MARGIN:", f"{margin:.6f}")
    print("RANKING:")
    for item in scores:
        print(
            f"  {item['person']}: cosine={item['cosine_similarity']:.6f}, "
            f"distance={item['l2_distance']:.6f}"
        )
    print("Output:", output_path)


if __name__ == "__main__":
    main()
