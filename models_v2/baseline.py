"""Compare baseline-adjusted exposure traces without changing the raw files."""

import csv
from dataclasses import dataclass
import math
from pathlib import Path
from statistics import fmean, median, quantiles

import numpy as np

from robonose_s3.inference import PREDICTION_SCHEMA, _timestamp
from robonose_s3.rescnn64 import MODEL_CHANNELS, prepare_trial
from robonose_s3.signals import number, validity


CHANNELS_V2 = (*MODEL_CHANNELS, ("temperature_c", "environment"))


@dataclass
class Trial:
    item: dict
    config_hash: str
    baseline_profile: tuple
    exposure: tuple
    bounded_drift: tuple
    warnings: list


def _phase(rows, phase, count):
    rows = [row for row in rows if row.get("phase") == phase]
    times = [number(row.get("mono_s")) for row in rows]
    if (len(times) != count or None in times
            or any(abs(right - left - 1) > .1 for left, right in zip(times, times[1:]))):
        raise ValueError(f"{phase}: cần {count} điểm đều ở 1 Hz.")
    return rows, times


def _channel(rows, key, sensor):
    if any(validity(row, key, sensor, modern=True) is not True for row in rows):
        raise ValueError(f"Tín hiệu {key} thiếu điểm hợp lệ.")
    return [float(row[key]) for row in rows]


def prepare(item, roots, encoder):
    if item["status"] != "COMPLETE" or not item["export_finalized"]:
        raise ValueError("Lượt chưa lưu hoàn chỉnh.")
    folder = Path(item["folder"]).resolve()
    raw = (folder / "raw.csv").resolve()
    if not any(raw.is_relative_to(root) for root in roots):
        raise ValueError("File tín hiệu nằm ngoài thư mục dữ liệu.")
    _, info = prepare_trial(folder, baseline_warn=encoder.settings.get("baseline_warn", False),
                            compatibility=encoder.artifact.get("compatibility"))
    with raw.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle, strict=True))
    if not rows or any(row.get("schema") != "robonose.dataset.v1" for row in rows):
        raise ValueError("Tín hiệu phải dùng schema robonose.dataset.v1.")
    baseline, base_times = _phase(rows, "BASELINE", 60)
    exposure, exposure_times = _phase(rows, "EXPOSURE", 120)
    if exposure_times[0] <= base_times[-1]:
        raise ValueError("EXPOSURE phải bắt đầu sau BASELINE.")
    configs = {row.get("config_hash") or "" for row in [*baseline, *exposure]}
    if len(configs) != 1:
        raise ValueError("Cấu hình thay đổi giữa BASELINE và EXPOSURE.")
    if any(row.get("air_path_commanded") != "SAMPLE" for row in [*baseline, *exposure]):
        raise ValueError("BASELINE và EXPOSURE phải đi qua đầu lấy mẫu.")

    time_center = fmean(base_times)
    offsets = [time - time_center for time in base_times]
    time_energy = math.fsum(offset ** 2 for offset in offsets)
    profile, traces, drift = [], [], []
    for key, sensor in CHANNELS_V2:
        values = _channel(baseline, key, sensor)
        center = median(values)
        low, *_, high = quantiles(values, n=10, method="inclusive")
        slope = math.fsum(offset * (value - center) for offset, value in zip(offsets, values)) / time_energy
        spread = high - low
        profile.extend((center, 60 * slope, spread))
        if key == "temperature_c":
            continue
        response = _channel(exposure, key, sensor)
        if key == "gas_resistance_ohm":
            # Work in log-ohms so the CNN still gets a log-ratio for this channel.
            values = [math.log(value) for value in values]
            response = [math.log(value) for value in response]
            center = median(values)
            low, *_, high = quantiles(values, n=10, method="inclusive")
            spread = high - low
            slope = math.fsum(offset * (value - center)
                              for offset, value in zip(offsets, values)) / time_energy
        traces.append([value - center for value in response])
        drift.append([max(-spread, min(spread, slope * (time - time_center)))
                      for time in exposure_times])
    return Trial(item, configs.pop(), tuple(profile), tuple(traces), tuple(drift), info["warnings"])


def _blank_group(trial):
    return trial.item["session_id"], trial.config_hash


def _blank_distance(sample, blank):
    # Use the channel's baseline level as scale for its level, slope and spread.
    scales = (max(abs(value), 1e-9) for value in sample.baseline_profile[::3])
    return math.fsum(
        ((a - b) / scale) ** 2
        for index, scale in enumerate(scales)
        for a, b in zip(sample.baseline_profile[3 * index:3 * (index + 1)],
                        blank.baseline_profile[3 * index:3 * (index + 1)], strict=True)
    )


def _embedding(encoder, trial, blank):
    correction = blank.exposure if blank else trial.bounded_drift
    tensor = np.asarray(trial.exposure, dtype=np.float32) - np.asarray(correction, dtype=np.float32)
    return encoder.encode_tensor(tensor)


class BaselineComparator:
    def __init__(self, catalog, encoder):
        self.catalog = catalog
        self.encoder = encoder

    def compare(self, reference_id, candidates):
        catalog = {item["trial_id"]: item for item in self.catalog.list()}
        selected = {reference_id, *candidates}
        if reference_id in candidates:
            raise ValueError("Mẫu tham chiếu đã có trong danh sách đối sánh.")

        def load(trial_id):
            if trial_id not in catalog:
                raise ValueError(f"Không tìm thấy lượt {trial_id}.")
            item = catalog[trial_id]
            if item["mode"] != "HARDWARE":
                raise ValueError("V2 cần lượt thu từ thiết bị.")
            return prepare(item, self.catalog.data_roots, self.encoder)

        reference = load(reference_id)
        prepared, skipped = [], []
        for order, trial_id in enumerate(candidates, 1):
            try:
                prepared.append((order, load(trial_id)))
            except (OSError, csv.Error, KeyError, ValueError) as error:
                skipped.append({"candidate_id": trial_id, "reason": str(error)})

        blanks = {}
        groups = {_blank_group(trial) for trial in [reference, *(trial for _, trial in prepared)]}
        sessions = {session_id for session_id, _ in groups}
        for trial_id, item in catalog.items():
            name = (item["name"] or "").strip().casefold()
            if (trial_id in selected or not (name == "blank" or name.startswith(("blank_", "blank ")))
                    or item["session_id"] not in sessions or not item["session_id"]):
                continue
            try:
                blank = load(trial_id)
            except (OSError, csv.Error, KeyError, ValueError):
                continue
            if blank.config_hash:
                blanks.setdefault(_blank_group(blank), []).append(blank)

        use_blanks = groups.issubset(blanks)
        mode = "matched_blank" if use_blanks else "bounded_drift"

        def closest(trial):
            if not use_blanks:
                return None
            return min(blanks[_blank_group(trial)], key=lambda blank: _blank_distance(trial, blank))

        ref_blank = closest(reference)
        ref_vector = _embedding(self.encoder, reference, ref_blank)
        ranking = []
        for order, trial in prepared:
            trial_id = trial.item["trial_id"]
            blank = closest(trial)
            candidate = _embedding(self.encoder, trial, blank)
            similarity = (ref_vector @ candidate.T).clamp(-1, 1).item()
            ranking.append({
                "candidate_id": trial_id, "input_order": order,
                "similarity": round(max(-1., min(1., similarity)), 6),
                "blank_id": blank.item["trial_id"] if blank else None,
                "warnings": trial.warnings,
            })
        ranking.sort(key=lambda item: (-item["similarity"], item["candidate_id"]))
        for rank, item in enumerate(ranking, 1):
            item["rank"] = rank
        return {
            "schema": PREDICTION_SCHEMA, "task": "reference_comparison",
            "reference_id": reference_id, "model_id": f"{self.encoder.model_id}:baseline-v2",
            "model_backend": "RESCNN64_BASELINE_V2",
            "synthetic_prediction": False, "experimental": True,
            "status": "RANKED" if ranking else "UNAVAILABLE", "ranking": ranking,
            "skipped_candidates": skipped, "preprocessing_mode": mode,
            "reference_blank_id": ref_blank.item["trial_id"] if ref_blank else None,
            "reference_warnings": reference.warnings, "embedding_dims": 64,
            "created_at": _timestamp(),
        }
