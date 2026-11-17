from __future__ import annotations

import math

import numpy as np
from scipy.signal import savgol_filter


def finite_float(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return math.nan
    return number if math.isfinite(number) else math.nan


def parse_bool(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def interpolate_short_gaps(values: np.ndarray, max_gap: int) -> tuple[np.ndarray, np.ndarray]:
    output = np.asarray(values, dtype=float).copy()
    flags = np.zeros(len(output), dtype=bool)
    index = 0
    while index < len(output):
        if math.isfinite(output[index]):
            index += 1
            continue
        start = index
        while index < len(output) and not math.isfinite(output[index]):
            index += 1
        end = index
        gap = end - start
        if gap <= max_gap and start > 0 and end < len(output):
            left = output[start - 1]
            right = output[end]
            if math.isfinite(left) and math.isfinite(right):
                output[start:end] = np.linspace(left, right, gap + 2)[1:-1]
                flags[start:end] = True
    return output, flags


def hampel_filter(values: np.ndarray, window: int, threshold: float) -> tuple[np.ndarray, np.ndarray]:
    source = np.asarray(values, dtype=float)
    output = source.copy()
    flags = np.zeros(len(source), dtype=bool)
    radius = window // 2
    for index, value in enumerate(source):
        if not math.isfinite(value):
            continue
        local = source[max(0, index - radius) : min(len(source), index + radius + 1)]
        local = local[np.isfinite(local)]
        if len(local) < 3:
            continue
        center = float(np.median(local))
        mad = float(np.median(np.abs(local - center)))
        robust_sigma = 1.4826 * mad
        if robust_sigma > 0 and abs(value - center) > threshold * robust_sigma:
            output[index] = center
            flags[index] = True
    return output, flags


def smooth_contiguous(values: np.ndarray, window: int, polyorder: int) -> np.ndarray:
    source = np.asarray(values, dtype=float)
    output = source.copy()
    index = 0
    while index < len(source):
        if not math.isfinite(source[index]):
            index += 1
            continue
        start = index
        while index < len(source) and math.isfinite(source[index]):
            index += 1
        end = index
        segment = source[start:end]
        usable_window = min(window, len(segment) if len(segment) % 2 else len(segment) - 1)
        if usable_window >= polyorder + 2 and usable_window >= 3:
            output[start:end] = savgol_filter(segment, usable_window, polyorder, mode="interp")
    return output


def robust_median(values: np.ndarray) -> float:
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    return float(np.median(finite)) if len(finite) else math.nan


def robust_cv_pct(values: np.ndarray) -> float:
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    if not len(finite):
        return math.nan
    center = float(np.median(finite))
    if center == 0:
        return math.nan
    mad = float(np.median(np.abs(finite - center)))
    return 100.0 * 1.4826 * mad / abs(center)


def slope_pct_per_minute(values: np.ndarray) -> float:
    finite_indices = np.flatnonzero(np.isfinite(values))
    if len(finite_indices) < 2:
        return math.nan
    y_values = values[finite_indices]
    slope = float(np.polyfit(finite_indices.astype(float), y_values, 1)[0])
    center = robust_median(y_values)
    return 100.0 * 60.0 * slope / abs(center) if center else math.nan


def roughness(values: np.ndarray) -> float:
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    return float(np.median(np.abs(np.diff(finite, n=2)))) if len(finite) >= 3 else math.nan


def percentile_range(values: np.ndarray) -> float:
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    return float(np.percentile(finite, 95) - np.percentile(finite, 5)) if len(finite) else math.nan
