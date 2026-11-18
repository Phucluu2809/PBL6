"""Screen original trial recordings without filtering or changing source data.

PASS means eligible for further inspection/preprocessing under the recorded
screening policy, not validated physical quality or verified class labels.
Only CSV/JSON results are generated. Uses the Python standard library.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

PHASES = ("BASELINE", "EXPOSURE", "RECOVERY")
POLICY = {
    "version": "raw-screening.v1",
    "pass_min_coverage": 0.95,
    "reject_below_coverage": 0.80,
    "pass_max_gap_s": 3.0,
    "baseline_tail_s": 30.0,
    "analog_tail_max_abs_drift_pct_per_min": 5.0,
    "analog_tail_max_robust_cv_pct": 2.0,
    "temperature_tail_max_abs_slope_c_per_min": 0.3,
    "temperature_tail_max_range_c": 0.2,
    "humidity_tail_max_abs_slope_pct_per_min": 1.0,
    "humidity_tail_max_range_pct": 1.0,
    "analog_thresholds_validated": False,
    "notes": "Screening only. Baseline warnings require review, never automatic rejection. Labels are not inferred from folder names. Containers are inventoried separately from collect/trial exports.",
}


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def truth(value):
    return str(value).strip().lower() in {"true", "1", "yes"}


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def write_csv(path, records):
    fields = list(dict.fromkeys(key for record in records for key in record))
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)


def metrics(points):
    if not points:
        return {"median": None, "robust_cv_pct": None, "slope_per_min": None,
                "drift_pct_per_min": None, "range": None, "range_pct": None}
    xs, ys = zip(*points)
    middle = statistics.median(ys)
    mean_x, mean_y = statistics.mean(xs), statistics.mean(ys)
    denominator = sum((x - mean_x) ** 2 for x in xs)
    slope = (60 * sum((x - mean_x) * (y - mean_y) for x, y in points) / denominator
             if denominator else None)
    spread = max(ys) - min(ys)
    cv = 100 * 1.4826 * statistics.median(abs(y - middle) for y in ys) / abs(middle) if middle else None
    return {"median": middle, "robust_cv_pct": cv, "slope_per_min": slope,
            "drift_pct_per_min": 100 * slope / abs(middle) if middle and slope is not None else None,
            "range": spread, "range_pct": 100 * spread / abs(middle) if middle else None}


def time_coverage(times, start, end, period):
    covered, previous_end = 0.0, start
    for t in sorted(set(times)):
        left, right = max(start, t, previous_end), min(end, t + period)
        if right > left:
            covered += right - left
            previous_end = right
    return covered / (end - start) if end > start else 0.0


def sensors_for(metadata, modern):
    if modern:
        analog = ("tgs2602", "mq3_1", "mq135_2", "mq3_2")
    elif metadata.get("config", {}).get("hardware", {}).get("mq_layout") == "four":
        analog = ("mq135_1", "mq3_1", "mq135_2", "mq3_2")
    else:
        analog = ("mq135", "mq3")
    bme = "bme688" if modern else "bme"
    return [(f"{p}_voltage_v", p, "analog") for p in analog] + [
        ("gas_resistance_ohm", bme, "gas"),
        ("temperature_c", bme, "environment"),
        ("humidity_pct", bme, "environment"),
        ("pressure_hpa", bme, "environment"),
    ]


def is_valid(row, key, prefix, modern):
    value = number(row.get(key))
    if value is None or row.get(prefix + "_status") != "OK" or not truth(row.get(prefix + "_fresh")):
        return False
    if modern and not truth(row.get(prefix + "_valid")):
        return False
    if key == "gas_resistance_ohm":
        return value > 0 and all(truth(row.get(flag)) for flag in ("new_data", "gas_valid", "heater_stable"))
    if key.endswith("_voltage_v"):
        return value >= 0
    return True


def evaluate(path, root, metadata, source_hash):
    modern = metadata.get("schema") == "robonose.dataset.v1"
    config = metadata.get("config", {})
    group = path.relative_to(root).parts[0]
    interval_key = "intervals" if modern else "phase_intervals"
    intervals = metadata.get(interval_key, [])
    identifier = metadata.get("trial_id") or metadata.get("run_id") or path.parent.name
    label = metadata.get("name") if modern else metadata.get("original_name")
    result = {"group": group, "trial_id": identifier, "name": label or "",
              "raw_path": path.as_posix(), "sha256": source_hash,
              "schema": metadata.get("schema", metadata.get("schema_version", "UNKNOWN")),
              "source_status": metadata.get("status", "UNKNOWN"),
              "label_status": "PRESENT_UNVERIFIED" if label else "MISSING",
              "profile_id": config.get("device_configuration", {}).get("profile_id", ""),
              "heater_requested_c": config.get("bme_requested", {}).get("heater_c", config.get("hardware", {}).get("heater_c")),
              "sensor_layout": "S3_TGS_4_ANALOG" if modern else "PI_4_ANALOG" if config.get("hardware", {}).get("mq_layout") == "four" else "PI_2_ANALOG"}
    review, reject, notes, details = [], [], [], []
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            columns = reader.fieldnames or []
            rows = list(reader)
    except (OSError, UnicodeError, csv.Error) as exc:
        return {**result, "status": "REJECT", "technical_status": "REJECT", "reasons": f"CSV_UNREADABLE:{exc}"}, []
    result["rows_total"] = len(rows)
    if isinstance(metadata.get("rows"), int) and metadata["rows"] != len(rows):
        review.append("ROW_COUNT_DIFFERS_FROM_METADATA")
    counts = Counter(row.get("phase") for row in rows)
    result["phase_counts"] = json.dumps(counts, ensure_ascii=False)
    if not rows:
        reject.append("EMPTY_CSV")
    if any(None in row or any(v is None for v in row.values()) for row in rows):
        reject.append("MALFORMED_CSV_ROW")
    time_key = "mono_s" if modern else "elapsed_s"
    required = {"phase", "seq", "timestamp", time_key}
    for key, prefix, kind in sensors_for(metadata, modern):
        required.update((key, prefix + "_status", prefix + "_fresh"))
        if modern:
            required.add(prefix + "_valid")
    required.update(("new_data", "gas_valid", "heater_stable"))
    if required.difference(columns):
        reject.append("MISSING_COLUMNS:" + ",".join(sorted(required.difference(columns))))
    if metadata.get("status") != "COMPLETE":
        reject.append("TRIAL_NOT_COMPLETE:" + str(metadata.get("status")))
    if str(metadata.get("mode", metadata.get("backend", ""))).upper() != "HARDWARE":
        review.append("SOURCE_NOT_CONFIRMED_HARDWARE")
    period_hz = number(config.get("sampling_hz", config.get("sample_hz")))
    if not period_hz or period_hz <= 0:
        period_hz = 1.0
        review.append("SAMPLING_RATE_MISSING_ASSUMED_1HZ")
    period = 1.0 / period_hz
    times = [number(row.get(time_key)) for row in rows]
    sequences = [number(row.get("seq")) for row in rows]
    if any(t is None for t in times):
        reject.append("INVALID_MONOTONIC_TIME")
    if any(b <= a for a, b in zip(times, times[1:]) if a is not None and b is not None):
        reject.append("NONINCREASING_MONOTONIC_TIME")
    if any(n is None or not n.is_integer() for n in sequences):
        reject.append("INVALID_SEQUENCE")
    if any(b <= a for a, b in zip(sequences, sequences[1:]) if a is not None and b is not None):
        reject.append("NONINCREASING_SEQUENCE")
    stamps = []
    for row in rows:
        try:
            stamps.append(datetime.fromisoformat(row.get("timestamp", "")).timestamp())
        except (ValueError, TypeError, OverflowError):
            reject.append("INVALID_WALL_TIMESTAMP")
            break
    if any(b < a for a, b in zip(stamps, stamps[1:])):
        review.append("WALL_CLOCK_MOVED_BACKWARDS")
    core_runs = []
    previous_phase = None
    for row in rows:
        phase = row.get("phase")
        if phase != previous_phase and phase in PHASES:
            core_runs.append(phase)
        previous_phase = phase
    if core_runs != list(PHASES):
        reject.append("MISSING_REPEATED_OR_MISORDERED_CORE_PHASES")
    result["context_straddled_core"] = sum(truth(r.get("context_straddled")) for r in rows if r.get("phase") in PHASES)
    if result["context_straddled_core"]:
        notes.append("BOUNDARY_CONTEXT_FLAGS_INSPECT_BEFORE_PROCESSING")
    core_skipped = [number(r.get("skipped_cycles")) or 0 for r in rows if r.get("phase") in PHASES]
    result["skipped_cycles_core"] = sum(core_skipped)
    if result["skipped_cycles_core"]:
        review.append("SKIPPED_CYCLES_IN_CORE")
    sensor_points = defaultdict(list)
    for phase in PHASES:
        phase_rows = [r for r in rows if r.get("phase") == phase]
        phase_times = [number(r.get(time_key)) for r in phase_rows]
        finite_times = [t for t in phase_times if t is not None]
        phase_intervals = [i for i in intervals if i.get("phase") == phase]
        if len(phase_intervals) == 1:
            item = phase_intervals[0]
            start = number(item.get("start_mono_s" if modern else "start_s"))
            end = number(item.get("end_mono_s" if modern else "end_s"))
        else:
            start = end = None
        if start is None or end is None or end <= start:
            start = min(finite_times, default=0.0)
            duration = number(config.get(phase.lower() + "_s")) or {"BASELINE": 60, "EXPOSURE": 120, "RECOVERY": 60}[phase]
            end = start + duration
            review.append(phase + ":INTERVAL_METADATA_MISSING")
        result[phase.lower() + "_rows"] = len(phase_rows)
        result[phase.lower() + "_duration_s"] = end - start
        planned = number(phase_intervals[0].get("planned_s")) if len(phase_intervals) == 1 else None
        if planned and end - start < planned * POLICY["reject_below_coverage"]:
            reject.append(phase + ":DURATION_BELOW_80PCT_PLANNED")
        elif planned and end - start < planned * POLICY["pass_min_coverage"]:
            review.append(phase + ":DURATION_BELOW_95PCT_PLANNED")
        if any(t < start - period or t > end + period for t in finite_times):
            reject.append(phase + ":TIME_OUTSIDE_INTERVAL")
        for key, prefix, kind in sensors_for(metadata, modern):
            points = [(t, number(r.get(key))) for r, t in zip(phase_rows, phase_times)
                      if t is not None and is_valid(r, key, prefix, modern)]
            valid_times = sorted(set(t for t, _ in points))
            coverage = time_coverage(valid_times, start, end, period)
            fraction = len(points) / len(phase_rows) if phase_rows else 0.0
            gap = max((b - a for a, b in zip([start, *valid_times], [*valid_times, end])), default=end-start)
            reasons = []
            hard = kind != "environment"
            if min(coverage, fraction) < POLICY["reject_below_coverage"]:
                reasons.append("INSUFFICIENT_VALID_DATA")
                (reject if hard else review).append(f"{phase}:{key}:INSUFFICIENT_VALID_DATA")
            elif min(coverage, fraction) < POLICY["pass_min_coverage"]:
                reasons.append("LOW_VALID_COVERAGE")
                review.append(f"{phase}:{key}:LOW_VALID_COVERAGE")
            if gap > POLICY["pass_max_gap_s"] + 1e-6:
                reasons.append("VALID_SAMPLE_GAP_GT_3S")
                review.append(f"{phase}:{key}:VALID_SAMPLE_GAP_GT_3S")
            all_values = [number(r.get(key)) for r in phase_rows]
            adc = [number(r.get(prefix + "_adc_count")) for r in phase_rows]
            saturated = sum(v is not None and abs(v) >= 32700 for v in adc)
            if saturated:
                reasons.append("ADC_NEAR_FULL_SCALE")
                review.append(f"{phase}:{key}:ADC_NEAR_FULL_SCALE")
            if hard and points and all(v == 0 for _, v in points):
                reject.append(f"{phase}:{key}:ZERO_SIGNAL")
            info = {"trial_id": identifier, "group": group, "raw_path": path.as_posix(),
                    "phase": phase, "signal": key, "kind": kind, "rows": len(phase_rows),
                    "expected_duration_s": end-start, "valid_points": len(points),
                    "missing_numeric": sum(v is None for v in all_values),
                    "valid_fraction": fraction, "time_coverage": coverage, "max_valid_gap_s": gap,
                    "adc_near_full_scale": saturated}
            if phase == "BASELINE":
                tail = [(t, v) for t, v in points if t >= end-POLICY["baseline_tail_s"]]
                stats = metrics(points)
                tail_stats = metrics(tail)
                info.update({"baseline_" + k: v for k, v in stats.items()})
                info.update({"tail_" + k: v for k, v in tail_stats.items()})
                tail_coverage = time_coverage([t for t, _ in points], max(start, end-POLICY["baseline_tail_s"]), end, period)
                info["tail_coverage"] = tail_coverage
                if tail_coverage < POLICY["pass_min_coverage"]:
                    review.append(f"{key}:BASELINE_TAIL_LOW_COVERAGE")
                if kind in {"gas", "analog"}:
                    drift_limit = (POLICY["analog_tail_max_abs_drift_pct_per_min"] if kind == "analog" else
                                   number(config.get("gas_slope_pct_per_min", config.get("stability", {}).get("gas_pct_per_min"))) or 5.0)
                    info["tail_drift_limit_pct_per_min"] = drift_limit
                    info["tail_cv_limit_pct"] = POLICY["analog_tail_max_robust_cv_pct"]
                    if tail_stats["drift_pct_per_min"] is not None and abs(tail_stats["drift_pct_per_min"]) > drift_limit:
                        review.append(f"{key}:BASELINE_TAIL_DRIFT")
                    if tail_stats["robust_cv_pct"] is not None and tail_stats["robust_cv_pct"] > POLICY["analog_tail_max_robust_cv_pct"]:
                        review.append(f"{key}:BASELINE_TAIL_VARIATION")
                elif key in {"temperature_c", "humidity_pct"}:
                    limits = ((POLICY["temperature_tail_max_abs_slope_c_per_min"], POLICY["temperature_tail_max_range_c"])
                              if key == "temperature_c" else
                              (POLICY["humidity_tail_max_abs_slope_pct_per_min"], POLICY["humidity_tail_max_range_pct"]))
                    if ((tail_stats["slope_per_min"] is not None and abs(tail_stats["slope_per_min"]) > limits[0])
                            or (tail_stats["range"] is not None and tail_stats["range"] > limits[1])):
                        review.append(f"{key}:BASELINE_ENVIRONMENT_CHANGE")
            info["reasons"] = ";".join(reasons)
            details.append(info)
            sensor_points[key].extend(points)
    for key, prefix, kind in sensors_for(metadata, modern):
        if kind != "environment" and len(sensor_points[key]) > 10 and len({v for _, v in sensor_points[key]}) == 1:
            review.append(key + ":CONSTANT_CORE_SIGNAL")
    technical = "REJECT" if reject else "REVIEW" if review else "PASS"
    if not label or str(label).strip().lower() in {"chưa đặt tên", "chua dat ten", "unknown"}:
        review.append("MISSING_SAMPLE_NAME")
        result["label_status"] = "MISSING"
    result.update(technical_status=technical, status="REJECT" if reject else "REVIEW" if review else "PASS",
                  reasons=";".join(dict.fromkeys(reject + review)), notes=";".join(notes))
    return result, details


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path(__file__).resolve().parents[1] / "data")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "quality_audit")
    args = parser.parse_args()
    root, output = args.data_root.resolve(), args.output.resolve()
    if output == root or root in output.parents:
        parser.error("Output must be outside the source data directory")
    inventory, trials, details = [], [], []
    fingerprints, metadata_hashes = {}, {}
    seen = {}
    for path in sorted(root.rglob("raw.csv")):
        fingerprint = digest(path)
        fingerprints[path] = fingerprint
        meta_path = path.with_name("metadata.json")
        try:
            if meta_path.exists():
                metadata_hashes[meta_path] = digest(meta_path)
            metadata = json.loads(meta_path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            metadata = {}
        modern = metadata.get("schema") == "robonose.dataset.v1"
        is_trial = "trials" in path.relative_to(root).parts if modern else metadata.get("kind") == "collect"
        record = {"raw_path": path.as_posix(), "group": path.relative_to(root).parts[0],
                  "sha256": fingerprint, "source_status": metadata.get("status"),
                  "role": "TRIAL" if is_trial else "CONTAINER_OR_DIAGNOSTIC"}
        inventory.append(record)
        if not is_trial:
            continue
        if fingerprint in seen:
            record.update(role="DUPLICATE_TRIAL_FILE", duplicate_of=seen[fingerprint])
            continue
        seen[fingerprint] = path.as_posix()
        trial, signal_details = evaluate(path, root, metadata, fingerprint)
        trials.append(trial)
        details.extend(signal_details)
    unchanged = all(digest(p) == h for p, h in {**fingerprints, **metadata_hashes}.items())
    if not unchanged:
        raise RuntimeError("Source files changed during audit; rerun before using results")
    by_group = []
    for group in sorted({r["group"] for r in inventory}):
        subset = [r for r in trials if r["group"] == group]
        by_group.append({"group": group, "raw_files": sum(r["group"] == group for r in inventory),
                         "trials": len(subset), **{s: sum(r["status"] == s for r in subset) for s in ("PASS", "REVIEW", "REJECT")},
                         "technical_PASS": sum(r["technical_status"] == "PASS" for r in subset)})
    summary = {"created_utc": datetime.now(timezone.utc).isoformat(), "policy": POLICY,
               "raw_files": len(inventory), "unique_trial_files": len(trials),
               "inventory_roles": dict(Counter(r["role"] for r in inventory)),
               "status_counts": dict(Counter(r["status"] for r in trials)),
               "by_group": by_group, "sources_unchanged_sha256": unchanged,
               "hashed_source_files": len(fingerprints) + len(metadata_hashes)}
    output.mkdir(parents=True, exist_ok=True)
    write_csv(output / "inventory.csv", inventory)
    write_csv(output / "trials.csv", trials)
    write_csv(output / "signal_quality.csv", details)
    write_csv(output / "by_group.csv", by_group)
    for status in ("PASS", "REVIEW", "REJECT"):
        write_csv(output / (status.lower() + "_trials.csv"), [r for r in trials if r["status"] == status])
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
