from __future__ import annotations

import csv
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from .config import (
    CORE_PHASES,
    HAMPEL_THRESHOLD,
    HAMPEL_WINDOW,
    MAX_BASELINE_CV_PASS,
    MAX_BASELINE_CV_REVIEW,
    MAX_BASELINE_DRIFT_PASS,
    MAX_BASELINE_DRIFT_REVIEW,
    MAX_GAP_PASS,
    MAX_GAP_REVIEW,
    MAX_INTERPOLATION_GAP,
    MAX_OUTLIER_FRACTION_PASS,
    MAX_OUTLIER_FRACTION_REVIEW,
    MIN_COVERAGE_PASS,
    MIN_COVERAGE_REVIEW,
    PHASE_OFFSETS,
    SAVGOL_POLYORDER,
    SIGNALS,
)
from .filters import (
    finite_float,
    hampel_filter,
    interpolate_short_gaps,
    parse_bool,
    percentile_range,
    robust_cv_pct,
    robust_median,
    roughness,
    slope_pct_per_minute,
    smooth_contiguous,
)


@dataclass
class SignalResult:
    raw: np.ndarray
    valid: np.ndarray
    interpolated: np.ndarray
    outlier: np.ndarray
    despiked: np.ndarray
    smooth: np.ndarray
    normalized: np.ndarray
    baseline: float


@dataclass
class TrialResult:
    source: Path
    folder: str
    name: str
    status: str
    start_time: str
    rows: list[dict[str, str]]
    signals: dict[str, SignalResult]
    quality_rows: list[dict[str, object]]
    quality_status: str
    output_directory: Path


def signal_is_valid(row: dict[str, str], signal) -> bool:
    if not math.isfinite(finite_float(row.get(signal.key))):
        return False
    prefix = signal.status_prefix
    if row.get(f"{prefix}_status") != "OK":
        return False
    if not parse_bool(row.get(f"{prefix}_fresh")) or not parse_bool(row.get(f"{prefix}_valid")):
        return False
    if signal.key == "gas_resistance_ohm":
        return all(parse_bool(row.get(key)) for key in ("new_data", "gas_valid", "heater_stable"))
    return True


def maximum_phase_gap(rows: list[dict[str, str]], phase: str) -> float:
    times = [finite_float(row.get("mono_s")) for row in rows if row.get("phase") == phase]
    times = [value for value in times if math.isfinite(value)]
    return max((right - left for left, right in zip(times, times[1:])), default=math.nan)


def metric_change(before: float, after: float) -> float:
    return 100.0 * (after / before - 1.0) if math.isfinite(before) and before != 0 and math.isfinite(after) else math.nan


def classify_quality(coverage: float, max_gap: float, cv: float, drift: float, outliers: float) -> str:
    values = (coverage, max_gap, cv, abs(drift), outliers)
    if any(not math.isfinite(value) for value in values):
        return "REJECT"
    if (
        coverage < MIN_COVERAGE_REVIEW
        or max_gap > MAX_GAP_REVIEW
        or cv > MAX_BASELINE_CV_REVIEW
        or abs(drift) > MAX_BASELINE_DRIFT_REVIEW
        or outliers > MAX_OUTLIER_FRACTION_REVIEW
    ):
        return "REJECT"
    if (
        coverage < MIN_COVERAGE_PASS
        or max_gap > MAX_GAP_PASS
        or cv > MAX_BASELINE_CV_PASS
        or abs(drift) > MAX_BASELINE_DRIFT_PASS
        or outliers > MAX_OUTLIER_FRACTION_PASS
    ):
        return "REVIEW"
    return "PASS"


def process_signal(rows: list[dict[str, str]], signal) -> tuple[SignalResult, dict[str, object]]:
    count = len(rows)
    raw = np.array([finite_float(row.get(signal.key)) for row in rows], dtype=float)
    valid = np.array([signal_is_valid(row, signal) for row in rows], dtype=bool)
    working = np.where(valid, raw, np.nan)
    interpolated = np.zeros(count, dtype=bool)
    outlier = np.zeros(count, dtype=bool)
    despiked = np.full(count, np.nan)
    smooth = np.full(count, np.nan)

    roughness_reductions = []
    range_changes = []
    for phase in CORE_PHASES:
        indices = np.array([index for index, row in enumerate(rows) if row.get("phase") == phase], dtype=int)
        if not len(indices):
            continue
        phase_values, phase_interpolated = interpolate_short_gaps(working[indices], MAX_INTERPOLATION_GAP)
        interpolated[indices] = phase_interpolated
        if signal.kind == "gas":
            phase_despiked, phase_outlier = hampel_filter(phase_values, HAMPEL_WINDOW, HAMPEL_THRESHOLD)
        else:
            phase_despiked = phase_values.copy()
            phase_outlier = np.zeros(len(indices), dtype=bool)
        phase_smooth = smooth_contiguous(phase_despiked, signal.smooth_window, SAVGOL_POLYORDER)
        despiked[indices] = phase_despiked
        outlier[indices] = phase_outlier
        smooth[indices] = phase_smooth
        raw_roughness = roughness(phase_despiked)
        smooth_roughness = roughness(phase_smooth)
        if math.isfinite(raw_roughness) and raw_roughness > 0 and math.isfinite(smooth_roughness):
            roughness_reductions.append(100.0 * (1.0 - smooth_roughness / raw_roughness))
        range_changes.append(metric_change(percentile_range(phase_despiked), percentile_range(phase_smooth)))

    baseline_indices = np.array([index for index, row in enumerate(rows) if row.get("phase") == "BASELINE"], dtype=int)
    baseline = robust_median(despiked[baseline_indices]) if len(baseline_indices) else math.nan
    normalized = np.full(count, np.nan)
    if math.isfinite(baseline):
        if signal.kind == "gas" and baseline != 0:
            normalized = 100.0 * (smooth - baseline) / abs(baseline)
        elif signal.kind == "environment":
            normalized = smooth - baseline

    core_indices = np.array([index for index, row in enumerate(rows) if row.get("phase") in CORE_PHASES], dtype=int)
    total_core = len(core_indices)
    coverage = float(np.sum(valid[core_indices]) / total_core) if total_core else 0.0
    gaps = [maximum_phase_gap(rows, phase) for phase in CORE_PHASES]
    finite_gaps = [value for value in gaps if math.isfinite(value)]
    max_gap = max(finite_gaps, default=math.nan)
    baseline_cv = robust_cv_pct(despiked[baseline_indices]) if len(baseline_indices) else math.nan
    baseline_drift = slope_pct_per_minute(despiked[baseline_indices]) if len(baseline_indices) else math.nan
    outlier_fraction = float(np.sum(outlier[core_indices]) / total_core) if total_core else 0.0
    quality_status = classify_quality(coverage, max_gap, baseline_cv, baseline_drift, outlier_fraction)
    finite_roughness = [value for value in roughness_reductions if math.isfinite(value)]
    finite_range = [value for value in range_changes if math.isfinite(value)]

    exposure_indices = np.array([index for index, row in enumerate(rows) if row.get("phase") == "EXPOSURE"], dtype=int)
    raw_exposure = despiked[exposure_indices]
    smooth_exposure = smooth[exposure_indices]
    finite_pairs = np.isfinite(raw_exposure) & np.isfinite(smooth_exposure)
    mean_change = math.nan
    auc_change = math.nan
    peak_shift = math.nan
    if np.any(finite_pairs):
        before = raw_exposure[finite_pairs]
        after = smooth_exposure[finite_pairs]
        mean_change = metric_change(float(np.mean(before)), float(np.mean(after)))
        auc_change = metric_change(float(np.trapezoid(before)), float(np.trapezoid(after)))
        peak_shift = float(abs(int(np.argmax(np.abs(before - baseline))) - int(np.argmax(np.abs(after - baseline)))))

    quality = {
        "signal": signal.key,
        "label": signal.label,
        "status": quality_status,
        "coverage": coverage,
        "max_gap_s": max_gap,
        "baseline": baseline,
        "baseline_robust_cv_pct": baseline_cv,
        "baseline_drift_pct_per_min": baseline_drift,
        "interpolated_points": int(np.sum(interpolated[core_indices])),
        "outlier_points": int(np.sum(outlier[core_indices])),
        "outlier_fraction": outlier_fraction,
        "roughness_reduction_pct": float(np.median(finite_roughness)) if finite_roughness else math.nan,
        "range_change_pct": float(np.median(finite_range)) if finite_range else math.nan,
        "exposure_mean_change_pct": mean_change,
        "exposure_auc_change_pct": auc_change,
        "exposure_peak_shift_s": peak_shift,
    }
    return SignalResult(raw, valid, interpolated, outlier, despiked, smooth, normalized, baseline), quality


def process_trial(raw_path: Path, output_root: Path) -> TrialResult:
    with raw_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    metadata = json.loads((raw_path.parent / "metadata.json").read_text(encoding="utf-8"))
    output_directory = output_root / "trials" / raw_path.parent.name
    output_directory.mkdir(parents=True, exist_ok=True)
    signal_results = {}
    quality_rows = []
    for signal in SIGNALS:
        result, quality = process_signal(rows, signal)
        signal_results[signal.key] = result
        quality_rows.append(quality)
    rank = {"PASS": 0, "REVIEW": 1, "REJECT": 2}
    quality_status = max((row["status"] for row in quality_rows), key=lambda status: rank[status], default="REJECT")
    start_time = rows[0].get("timestamp", "") if rows else metadata.get("started_at", "") or ""
    return TrialResult(
        source=raw_path,
        folder=raw_path.parent.name,
        name=metadata.get("name") or "Chưa đặt tên",
        status=metadata.get("status") or "UNKNOWN",
        start_time=start_time,
        rows=rows,
        signals=signal_results,
        quality_rows=quality_rows,
        quality_status=quality_status,
        output_directory=output_directory,
    )


def format_number(value: float) -> str:
    return "" if not math.isfinite(value) else f"{value:.12g}"


def write_trial_csv(trial: TrialResult) -> None:
    identity_columns = ("schema", "mode", "session_id", "seq", "timestamp", "mono_s", "trial_id", "phase", "segment_id", "phase_elapsed_s")
    fieldnames = list(identity_columns)
    for signal in SIGNALS:
        prefix = signal.key
        fieldnames.extend(
            (
                f"{prefix}__raw",
                f"{prefix}__valid",
                f"{prefix}__interpolated",
                f"{prefix}__outlier",
                f"{prefix}__despiked",
                f"{prefix}__smooth",
                f"{prefix}__normalized",
            )
        )
    output_path = trial.output_directory / "preprocessed.csv"
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for index, row in enumerate(trial.rows):
            output = {column: row.get(column, "") for column in identity_columns}
            for signal in SIGNALS:
                result = trial.signals[signal.key]
                prefix = signal.key
                output[f"{prefix}__raw"] = format_number(result.raw[index])
                output[f"{prefix}__valid"] = bool(result.valid[index])
                output[f"{prefix}__interpolated"] = bool(result.interpolated[index])
                output[f"{prefix}__outlier"] = bool(result.outlier[index])
                output[f"{prefix}__despiked"] = format_number(result.despiked[index])
                output[f"{prefix}__smooth"] = format_number(result.smooth[index])
                output[f"{prefix}__normalized"] = format_number(result.normalized[index])
            writer.writerow(output)


def write_quality_json(trial: TrialResult) -> None:
    document = {
        "trial": trial.folder,
        "name": trial.name,
        "source_status": trial.status,
        "preprocessing_status": trial.quality_status,
        "signals": trial.quality_rows,
    }
    (trial.output_directory / "quality.json").write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")


def write_quality_report(trials: list[TrialResult], output_root: Path) -> None:
    fieldnames = ["trial", "name", "start_time", "trial_status", *trials[0].quality_rows[0].keys()]
    with (output_root / "quality_report.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for trial in trials:
            for quality in trial.quality_rows:
                writer.writerow({
                    "trial": trial.folder,
                    "name": trial.name,
                    "start_time": trial.start_time,
                    "trial_status": trial.status,
                    **quality,
                })


def write_canonical_signals(trials: list[TrialResult], output_root: Path) -> None:
    fieldnames = ["trial", "name", "phase", "phase_second", "canonical_second", *[signal.key for signal in SIGNALS]]
    with (output_root / "canonical_signals.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for trial in trials:
            phase_counts = {phase: 0 for phase in CORE_PHASES}
            for index, row in enumerate(trial.rows):
                phase = row.get("phase")
                if phase not in CORE_PHASES:
                    continue
                phase_second = phase_counts[phase]
                phase_counts[phase] += 1
                output = {
                    "trial": trial.folder,
                    "name": trial.name,
                    "phase": phase,
                    "phase_second": phase_second,
                    "canonical_second": PHASE_OFFSETS[phase] + phase_second,
                }
                for signal in SIGNALS:
                    output[signal.key] = format_number(trial.signals[signal.key].normalized[index])
                writer.writerow(output)


def write_manifest(data_root: Path, output_root: Path, trials: list[TrialResult]) -> None:
    manifest = {
        "schema": "robonose.preprocessing.v1",
        "source": str(data_root),
        "trial_count": len(trials),
        "core_phases": list(CORE_PHASES),
        "signals": [asdict(signal) for signal in SIGNALS],
        "parameters": {
            "hampel_window": HAMPEL_WINDOW,
            "hampel_threshold": HAMPEL_THRESHOLD,
            "savgol_polyorder": SAVGOL_POLYORDER,
            "max_interpolation_gap": MAX_INTERPOLATION_GAP,
        },
    }
    (output_root / "preprocessing_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def run_preprocessing(data_root: Path) -> Path:
    data_root = data_root.resolve()
    if not data_root.is_dir():
        raise FileNotFoundError(f"Data directory not found: {data_root}")
    raw_paths = sorted(data_root.glob("*/trials/*/raw.csv"))
    if not raw_paths:
        raise FileNotFoundError(f"No trial raw.csv files found in {data_root}")
    output_root = data_root / "PREPROCESSED"
    output_root.mkdir(parents=True, exist_ok=True)
    trials = [process_trial(path, output_root) for path in raw_paths]
    trials.sort(key=lambda trial: (trial.start_time or "9999", trial.folder))
    for trial in trials:
        write_trial_csv(trial)
        write_quality_json(trial)
    write_quality_report(trials, output_root)
    write_canonical_signals(trials, output_root)
    write_manifest(data_root, output_root, trials)
    return output_root
