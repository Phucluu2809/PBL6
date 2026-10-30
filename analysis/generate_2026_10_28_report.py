"""Generate a comprehensive Markdown report for data/2026-10-28."""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
from datetime import datetime
from html import escape
import json
import math
from pathlib import Path
import statistics


ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data" / "2026-10-28"
OUTPUT = DATA_ROOT / "README_PHAN_TICH.md"
ASSET_ROOT = DATA_ROOT / "report_assets"

PHASES = ("BASELINE", "EXPOSURE", "RECOVERY")
EXPECTED_ROWS = {"BASELINE": 60, "EXPOSURE": 120, "RECOVERY": 60}
MIN_VALID_FRACTION = 0.90
COFFEE_ON_TAI_LABELS = {
    "Tài + cà phê",
    "Tài + cà phê ít",
    "Tài + cà phê nhiều",
}

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


def parse_float(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def parse_bool(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def slope(points: list[tuple[float, float]]) -> float | None:
    if len(points) < 3:
        return None
    x_center = statistics.fmean(point[0] for point in points)
    y_center = statistics.fmean(point[1] for point in points)
    denominator = sum((point[0] - x_center) ** 2 for point in points)
    if denominator == 0:
        return None
    return sum(
        (x - x_center) * (y - y_center) for x, y in points
    ) / denominator


def trapezoid_auc(points: list[tuple[float, float]]) -> float | None:
    if len(points) < 2:
        return None
    ordered = sorted(points)
    return sum(
        (right_x - left_x) * (left_y + right_y) / 2
        for (left_x, left_y), (right_x, right_y) in zip(ordered, ordered[1:])
    )


def pearson(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or len(left) < 3:
        return None
    left_mean = statistics.fmean(left)
    right_mean = statistics.fmean(right)
    numerator = sum(
        (left_value - left_mean) * (right_value - right_mean)
        for left_value, right_value in zip(left, right)
    )
    left_scale = math.sqrt(sum((value - left_mean) ** 2 for value in left))
    right_scale = math.sqrt(sum((value - right_mean) ** 2 for value in right))
    denominator = left_scale * right_scale
    return numerator / denominator if denominator else None


def cosine(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or not left:
        return None
    denominator = math.sqrt(sum(value**2 for value in left)) * math.sqrt(
        sum(value**2 for value in right)
    )
    return sum(a * b for a, b in zip(left, right)) / denominator if denominator else None


def fmt(value: object, digits: int = 2) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "Có" if value else "Không"
    if isinstance(value, (int, float)):
        number = float(value)
        if not math.isfinite(number):
            return "—"
        return f"{number:.{digits}f}"
    return str(value)


def markdown_escape(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def classify_run(folder: str) -> tuple[str, str]:
    lower = folder.lower()
    if lower.startswith("basetai_exposetaivscf_"):
        return "Tài nền → Tài + cà phê", "Thí nghiệm chuyển mẫu"
    if lower.startswith("taivscf_nhieu_"):
        return "Tài + cà phê nhiều", "Mẫu hỗn hợp"
    if lower.startswith("taivscf_it_"):
        return "Tài + cà phê ít", "Mẫu hỗn hợp"
    if lower.startswith("taivscf_"):
        return "Tài + cà phê", "Mẫu hỗn hợp"
    if lower.startswith("cf_nhieu_"):
        return "Cà phê nhiều", "Mẫu đối chứng cà phê"
    if lower.startswith("cf_it_"):
        return "Cà phê ít", "Mẫu đối chứng cà phê"
    if lower.startswith("khongkhi_"):
        return "Không khí", "Mẫu nền"
    if lower.startswith("aminh_"):
        return "Minh", "Mẫu người"
    if lower.startswith("aquy_"):
        return "Quy", "Mẫu người"
    if lower.startswith("tai_"):
        return "Tài", "Mẫu người"
    return folder.split("_2026", 1)[0], "Chưa phân loại"


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


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_run(directory: Path) -> dict[str, object]:
    metadata = read_json(directory / "metadata.json")
    summary = read_json(directory / "summary.json")
    with (directory / "raw.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    with (directory / "events.csv").open(encoding="utf-8-sig", newline="") as handle:
        events = list(csv.DictReader(handle))

    label, category = classify_run(directory.name)
    started_at = datetime.fromisoformat(str(metadata["started_at"]))
    ended_at = datetime.fromisoformat(str(metadata["ended_at"]))
    duration = (ended_at - started_at).total_seconds()
    measurement_quality = summary.get(
        "measurement_quality", metadata.get("measurement_quality", {})
    )
    baseline_quality = (
        measurement_quality.get("baseline", {})
        if isinstance(measurement_quality, dict)
        else {}
    )
    baseline_stable = baseline_quality.get("stable")

    phase_rows = {
        phase: [row for row in rows if row.get("phase") == phase] for phase in PHASES
    }
    baselines: dict[str, float | None] = {}
    normalized: dict[str, dict[str, list[tuple[float, float]]]] = defaultdict(dict)
    valid_fractions: dict[str, dict[str, float]] = defaultdict(dict)
    features: dict[str, dict[str, float | None]] = defaultdict(dict)

    for sensor, config in SENSORS.items():
        baseline_values = [
            value
            for row in phase_rows["BASELINE"]
            if sensor_valid(row, sensor)
            and (value := parse_float(row.get(config["value"]))) is not None
        ]
        baseline = median(baseline_values)
        baselines[sensor] = baseline
        for phase in PHASES:
            candidates = phase_rows[phase]
            points: list[tuple[float, float]] = []
            for row in candidates:
                if not sensor_valid(row, sensor):
                    continue
                elapsed = parse_float(row.get("phase_elapsed_s"))
                value = parse_float(row.get(config["value"]))
                if elapsed is None or value is None or baseline in {None, 0}:
                    continue
                points.append((elapsed, 100 * (value - baseline) / abs(baseline)))
            normalized[sensor][phase] = sorted(points)
            valid_fractions[sensor][phase] = len(points) / max(
                len(candidates), EXPECTED_ROWS[phase], 1
            )

        exposure = normalized[sensor]["EXPOSURE"]
        recovery = normalized[sensor]["RECOVERY"]
        exposure_values = [value for _, value in exposure]
        if exposure_values:
            one_third = max(len(exposure_values) // 3, 1)
            middle = exposure_values[one_third : 2 * one_third]
            features[sensor] = {
                "exposure_mean": mean(exposure_values),
                "exposure_middle_mean": mean(middle),
                "q10": percentile(exposure_values, 0.10),
                "q90": percentile(exposure_values, 0.90),
                "minimum": min(exposure_values),
                "maximum": max(exposure_values),
                "slope_pct_per_s": slope(exposure),
                "auc_pct_s": trapezoid_auc(exposure),
                "recovery_end": mean([value for _, value in recovery[-10:]]),
            }
        else:
            features[sensor] = {
                key: None
                for key in (
                    "exposure_mean",
                    "exposure_middle_mean",
                    "q10",
                    "q90",
                    "minimum",
                    "maximum",
                    "slope_pct_per_s",
                    "auc_pct_s",
                    "recovery_end",
                )
            }

    environmental: dict[str, float | None] = {}
    for column in ("temperature_c", "humidity_pct", "pressure_hpa"):
        baseline_values = [
            value
            for row in phase_rows["BASELINE"]
            if (value := parse_float(row.get(column))) is not None
        ]
        exposure_values = [
            value
            for row in phase_rows["EXPOSURE"]
            if (value := parse_float(row.get(column))) is not None
        ]
        baseline_value = median(baseline_values)
        exposure_value = mean(exposure_values)
        environmental[f"baseline_{column}"] = baseline_value
        environmental[f"delta_{column}"] = (
            exposure_value - baseline_value
            if baseline_value is not None and exposure_value is not None
            else None
        )

    read_errors = Counter()
    for event in events:
        if event.get("event") != "read_error":
            continue
        try:
            details = json.loads(event.get("details_json") or "{}")
        except json.JSONDecodeError:
            details = {}
        read_errors[str(details.get("device", "unknown"))] += 1

    warnings = summary.get("warnings", [])
    quality_reasons = []
    for sensor in SENSORS:
        for phase in PHASES:
            fraction = valid_fractions[sensor][phase]
            if fraction < MIN_VALID_FRACTION:
                quality_reasons.append(
                    f"{SENSORS[sensor]['label']} {phase} chỉ {fraction:.1%} hợp lệ"
                )
    if baseline_stable is False:
        quality_reasons.append("baseline không ổn định")

    return {
        "folder": directory.name,
        "label": label,
        "category": category,
        "metadata": metadata,
        "summary": summary,
        "rows": rows,
        "started_at": started_at,
        "ended_at": ended_at,
        "duration": duration,
        "phase_rows": phase_rows,
        "baselines": baselines,
        "normalized": normalized,
        "valid_fractions": valid_fractions,
        "features": features,
        "environmental": environmental,
        "read_errors": read_errors,
        "warnings": warnings,
        "baseline_stable": baseline_stable,
        "accepted": not quality_reasons,
        "quality_reasons": quality_reasons,
    }


def group_feature_summary(runs: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for run in runs:
        grouped[str(run["label"])].append(run)
    result: dict[str, dict[str, object]] = {}
    for label, label_runs in grouped.items():
        result[label] = {"count": len(label_runs), "sensors": {}}
        for sensor in SENSORS:
            values = [
                value
                for run in label_runs
                if (value := run["features"][sensor]["exposure_mean"]) is not None
            ]
            result[label]["sensors"][sensor] = {
                "mean": mean(values),
                "minimum": min(values) if values else None,
                "maximum": max(values) if values else None,
            }
    return result


def duplicate_sensor_correlations(runs: list[dict[str, object]]) -> dict[str, float | None]:
    pairs = {
        "MQ135-1 ↔ MQ135-2": ("mq135_1", "mq135_2"),
        "MQ3-1 ↔ MQ3-2": ("mq3_1", "mq3_2"),
    }
    output = {}
    for label, (left_sensor, right_sensor) in pairs.items():
        left_values: list[float] = []
        right_values: list[float] = []
        for run in runs:
            for phase in PHASES:
                left_points = run["normalized"][left_sensor][phase]
                right_points = run["normalized"][right_sensor][phase]
                for (_, left_value), (_, right_value) in zip(left_points, right_points):
                    left_values.append(left_value)
                    right_values.append(right_value)
        output[label] = pearson(left_values, right_values)
    return output


def repeatability_rows(runs: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for run in runs:
        grouped[str(run["label"])].append(run)
    rows = []
    for label, label_runs in grouped.items():
        if len(label_runs) < 2:
            continue
        vectors = []
        for run in label_runs:
            vector = [
                run["features"][sensor]["exposure_mean"] for sensor in SENSORS
            ]
            if all(value is not None for value in vector):
                vectors.append([float(value) for value in vector])
        similarities = [
            value
            for index, left in enumerate(vectors)
            for right in vectors[index + 1 :]
            if (value := cosine(left, right)) is not None
        ]
        rows.append(
            {
                "label": label,
                "count": len(label_runs),
                "pair_count": len(similarities),
                "median_cosine": median(similarities),
                "minimum_cosine": min(similarities) if similarities else None,
            }
        )
    return rows


def coffee_status_summary(runs: list[dict[str, object]]) -> list[dict[str, object]]:
    pure_tai = [run for run in runs if run["label"] == "Tài"]
    coffee_tai = [run for run in runs if run["label"] in COFFEE_ON_TAI_LABELS]
    rows = []
    for sensor, config in SENSORS.items():
        pure_values = [
            float(value)
            for run in pure_tai
            if (value := run["features"][sensor]["exposure_mean"]) is not None
        ]
        coffee_values = [
            float(value)
            for run in coffee_tai
            if (value := run["features"][sensor]["exposure_mean"]) is not None
        ]
        pure_mean = mean(pure_values)
        coffee_mean = mean(coffee_values)
        rows.append(
            {
                "sensor": sensor,
                "label": config["label"],
                "pure_count": len(pure_values),
                "coffee_count": len(coffee_values),
                "pure_mean": pure_mean,
                "coffee_mean": coffee_mean,
                "difference": (
                    coffee_mean - pure_mean
                    if pure_mean is not None and coffee_mean is not None
                    else None
                ),
                "pure_values": pure_values,
                "coffee_values": coffee_values,
            }
        )
    return rows


def save_figure(filename: str) -> None:
    ASSET_ROOT.mkdir(parents=True, exist_ok=True)
    plt.savefig(ASSET_ROOT / filename, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close()


def annotate_heatmap(axis: plt.Axes, matrix: np.ndarray, threshold: float) -> None:
    for row_index in range(matrix.shape[0]):
        for column_index in range(matrix.shape[1]):
            value = matrix[row_index, column_index]
            color = "white" if abs(value) > threshold else "black"
            axis.text(
                column_index,
                row_index,
                f"{value:.1f}",
                ha="center",
                va="center",
                fontsize=7,
                color=color,
            )


def _generate_figures_matplotlib(runs: list[dict[str, object]]) -> None:
    runs = sorted(runs, key=lambda run: run["started_at"])
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "figure.dpi": 120,
            "axes.titlesize": 12,
            "axes.labelsize": 10,
        }
    )

    exposure_matrix = np.array(
        [
            [float(run["features"][sensor]["exposure_mean"]) for sensor in SENSORS]
            for run in runs
        ]
    )
    limit = max(float(np.nanpercentile(np.abs(exposure_matrix), 95)), 1.0)
    figure, axis = plt.subplots(figsize=(10, 9))
    image = axis.imshow(exposure_matrix, cmap="RdBu_r", vmin=-limit, vmax=limit, aspect="auto")
    axis.set_xticks(range(len(SENSORS)), [config["label"] for config in SENSORS.values()])
    axis.set_yticks(
        range(len(runs)),
        [f"{run['started_at'].strftime('%H:%M')} · {run['label']}" for run in runs],
    )
    axis.set_title("Đáp ứng trung bình trong EXPOSURE của toàn bộ phiên")
    axis.set_xlabel("Cảm biến")
    axis.set_ylabel("Phiên theo thứ tự thời gian")
    annotate_heatmap(axis, exposure_matrix, limit * 0.55)
    colorbar = figure.colorbar(image, ax=axis, fraction=0.035, pad=0.02)
    colorbar.set_label("Thay đổi so với median BASELINE (%)")
    figure.tight_layout()
    save_figure("01_heatmap_dap_ung_toan_bo.png")

    comparison = coffee_status_summary(runs)
    figure, axes = plt.subplots(1, len(comparison), figsize=(15, 4.8), sharey=False)
    rng = np.random.default_rng(20261028)
    for axis, item in zip(axes, comparison):
        values = [item["pure_values"], item["coffee_values"]]
        axis.boxplot(
            values,
            positions=[0, 1],
            widths=0.5,
            patch_artist=True,
            medianprops={"color": "black", "linewidth": 1.5},
            boxprops={"facecolor": "#d9e8fb", "edgecolor": "#245a9b"},
            whiskerprops={"color": "#245a9b"},
            capprops={"color": "#245a9b"},
        )
        for position, points, color in (
            (0, item["pure_values"], "#245a9b"),
            (1, item["coffee_values"], "#c83e4d"),
        ):
            jitter = rng.uniform(-0.08, 0.08, len(points))
            axis.scatter(
                np.full(len(points), position) + jitter,
                points,
                color=color,
                s=32,
                zorder=3,
                alpha=0.9,
            )
        axis.axhline(0, color="#777777", linewidth=0.8, linestyle="--")
        axis.set_xticks([0, 1], ["Tài\nkhông CF", "Tài\n+cà phê"])
        axis.set_title(str(item["label"]))
        axis.grid(axis="y", alpha=0.25)
    axes[0].set_ylabel("Đáp ứng EXPOSURE trung bình (%)")
    figure.suptitle("So sánh trực tiếp: Tài không cà phê và Tài có cà phê", y=1.02, fontsize=14)
    figure.tight_layout()
    save_figure("02_tai_co_khong_ca_phe.png")

    grouped = group_feature_summary(runs)
    group_labels = sorted(grouped)
    group_matrix = np.array(
        [
            [float(grouped[label]["sensors"][sensor]["mean"]) for sensor in SENSORS]
            for label in group_labels
        ]
    )
    group_limit = max(float(np.nanpercentile(np.abs(group_matrix), 95)), 1.0)
    figure, axis = plt.subplots(figsize=(10, 6.5))
    image = axis.imshow(
        group_matrix,
        cmap="RdBu_r",
        vmin=-group_limit,
        vmax=group_limit,
        aspect="auto",
    )
    axis.set_xticks(range(len(SENSORS)), [config["label"] for config in SENSORS.values()])
    axis.set_yticks(
        range(len(group_labels)),
        [f"{label} (n={grouped[label]['count']})" for label in group_labels],
    )
    axis.set_title("Đáp ứng EXPOSURE trung bình theo nhóm mẫu")
    annotate_heatmap(axis, group_matrix, group_limit * 0.55)
    colorbar = figure.colorbar(image, ax=axis, fraction=0.04, pad=0.02)
    colorbar.set_label("Thay đổi so với median BASELINE (%)")
    figure.tight_layout()
    save_figure("03_heatmap_trung_binh_nhom.png")

    minimum_valid = [
        min(
            run["valid_fractions"][sensor][phase]
            for sensor in SENSORS
            for phase in PHASES
        )
        * 100
        for run in runs
    ]
    read_errors = [sum(run["read_errors"].values()) for run in runs]
    positions = np.arange(1, len(runs) + 1)
    figure, axes = plt.subplots(2, 1, figsize=(12, 7), sharex=True)
    axes[0].bar(positions, minimum_valid, color="#4c78a8")
    axes[0].axhline(MIN_VALID_FRACTION * 100, color="#c83e4d", linestyle="--", label="Ngưỡng QC 90%")
    axes[0].set_ylim(88, 101)
    axes[0].set_ylabel("Tỷ lệ hợp lệ nhỏ nhất (%)")
    axes[0].legend(loc="lower left")
    axes[0].grid(axis="y", alpha=0.25)
    axes[1].bar(positions, read_errors, color="#f28e2b")
    axes[1].set_ylabel("Số lỗi đọc")
    axes[1].set_xlabel("Thứ tự phiên trong ngày")
    axes[1].set_xticks(positions)
    axes[1].grid(axis="y", alpha=0.25)
    figure.suptitle("Chất lượng dữ liệu và lỗi đọc theo phiên", fontsize=14)
    figure.tight_layout()
    save_figure("04_chat_luong_va_loi_doc.png")

    times = np.array(
        [run["started_at"].hour + run["started_at"].minute / 60 for run in runs]
    )
    environment_series = (
        ("Nhiệt độ", "baseline_temperature_c", "°C", "#d62728"),
        ("Độ ẩm", "baseline_humidity_pct", "%", "#1f77b4"),
        ("Áp suất", "baseline_pressure_hpa", "hPa", "#2ca02c"),
    )
    figure, axes = plt.subplots(3, 1, figsize=(12, 8), sharex=True)
    for axis, (title, key, unit, color) in zip(axes, environment_series):
        values = [float(run["environmental"][key]) for run in runs]
        axis.plot(times, values, marker="o", color=color, linewidth=1.6)
        axis.axvspan(15, 21, color="#eeeeee", alpha=0.8)
        axis.set_ylabel(unit)
        axis.set_title(title, loc="left")
        axis.grid(alpha=0.25)
    axes[-1].set_xlabel("Giờ bắt đầu phiên")
    axes[-1].set_xticks([13, 14, 22, 23], ["13h", "14h", "22h", "23h"])
    figure.suptitle("Biến đổi điều kiện môi trường giữa hai khối đo", fontsize=14)
    figure.tight_layout()
    save_figure("05_moi_truong_theo_thoi_gian.png")


def svg_text(
    x: float,
    y: float,
    value: object,
    size: int = 14,
    anchor: str = "start",
    weight: str = "normal",
    color: str = "#222222",
) -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" text-anchor="{anchor}" '
        f'font-weight="{weight}" fill="{color}" font-family="DejaVu Sans, Arial, sans-serif">'
        f"{escape(str(value))}</text>"
    )


def write_svg(filename: str, width: int, height: int, elements: list[str]) -> None:
    document = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        *elements,
        "</svg>",
    ]
    (ASSET_ROOT / filename).write_text("\n".join(document), encoding="utf-8")


def diverging_color(value: float, limit: float) -> str:
    normalized = max(-1.0, min(1.0, value / max(limit, 1e-9)))
    target = (48, 105, 181) if normalized < 0 else (204, 65, 68)
    strength = abs(normalized)
    channels = [round(247 + (channel - 247) * strength) for channel in target]
    return "#" + "".join(f"{channel:02x}" for channel in channels)


def quantile_limit(values: list[list[float]]) -> float:
    ordered = sorted(abs(value) for row in values for value in row)
    index = min(max(math.ceil(len(ordered) * 0.95) - 1, 0), len(ordered) - 1)
    return max(ordered[index], 1.0)


def heatmap_svg(
    filename: str,
    title: str,
    row_labels: list[str],
    values: list[list[float]],
) -> None:
    width = 1180
    left = 330
    top = 90
    cell_width = 150
    cell_height = 36
    height = top + len(row_labels) * cell_height + 85
    limit = quantile_limit(values)
    elements = [svg_text(width / 2, 38, title, 22, "middle", "bold")]
    for column_index, config in enumerate(SENSORS.values()):
        x = left + column_index * cell_width + cell_width / 2
        elements.append(svg_text(x, top - 18, config["label"], 14, "middle", "bold"))
    for row_index, (label, row) in enumerate(zip(row_labels, values)):
        y = top + row_index * cell_height
        elements.append(svg_text(left - 12, y + 23, label, 13, "end"))
        for column_index, value in enumerate(row):
            x = left + column_index * cell_width
            color = diverging_color(value, limit)
            text_color = "white" if abs(value) > limit * 0.58 else "#222222"
            elements.append(
                f'<rect x="{x}" y="{y}" width="{cell_width}" height="{cell_height}" fill="{color}" stroke="white"/>'
            )
            elements.append(
                svg_text(x + cell_width / 2, y + 23, f"{value:.1f}", 13, "middle", "bold", text_color)
            )
    legend_y = top + len(row_labels) * cell_height + 28
    for index in range(101):
        value = -limit + 2 * limit * index / 100
        elements.append(
            f'<rect x="{left + index * 4.5:.1f}" y="{legend_y}" width="4.7" height="14" fill="{diverging_color(value, limit)}"/>'
        )
    elements.extend(
        [
            svg_text(left, legend_y + 34, f"−{limit:.1f}%", 12),
            svg_text(left + 225, legend_y + 34, "0%", 12, "middle"),
            svg_text(left + 450, legend_y + 34, f"+{limit:.1f}%", 12, "end"),
        ]
    )
    write_svg(filename, width, height, elements)


def generate_figures(runs: list[dict[str, object]]) -> None:
    runs = sorted(runs, key=lambda run: run["started_at"])
    exposure_values = [
        [float(run["features"][sensor]["exposure_mean"]) for sensor in SENSORS]
        for run in runs
    ]
    heatmap_svg(
        "01_heatmap_dap_ung_toan_bo.svg",
        "Đáp ứng trung bình trong EXPOSURE của toàn bộ phiên",
        [f"{run['started_at'].strftime('%H:%M')} · {run['label']}" for run in runs],
        exposure_values,
    )

    comparison = coffee_status_summary(runs)
    width = 1500
    height = 530
    elements = [
        svg_text(width / 2, 40, "So sánh trực tiếp: Tài không cà phê và Tài có cà phê", 23, "middle", "bold"),
        svg_text(22, 270, "Đáp ứng EXPOSURE (%)", 14, "middle", "bold"),
    ]
    offsets = (-22, -11, 0, 11, 22)
    for panel_index, item in enumerate(comparison):
        x0 = 80 + panel_index * 280
        top = 100
        bottom = 425
        all_values = [*item["pure_values"], *item["coffee_values"]]
        padding = max((max(all_values) - min(all_values)) * 0.15, 0.25)
        low = min(all_values) - padding
        high = max(all_values) + padding

        def map_y(value: float) -> float:
            return bottom - (value - low) / (high - low) * (bottom - top)

        elements.extend(
            [
                svg_text(x0 + 105, 78, item["label"], 16, "middle", "bold"),
                f'<line x1="{x0}" y1="{top}" x2="{x0}" y2="{bottom}" stroke="#777"/>',
                f'<line x1="{x0}" y1="{bottom}" x2="{x0 + 210}" y2="{bottom}" stroke="#777"/>',
                svg_text(x0 - 8, top + 4, f"{high:.1f}", 11, "end"),
                svg_text(x0 - 8, bottom, f"{low:.1f}", 11, "end"),
            ]
        )
        if low <= 0 <= high:
            zero_y = map_y(0)
            elements.append(
                f'<line x1="{x0}" y1="{zero_y:.1f}" x2="{x0 + 210}" y2="{zero_y:.1f}" stroke="#aaaaaa" stroke-dasharray="4 4"/>'
            )
        groups = (
            (item["pure_values"], "#2f69b1", "Không CF"),
            (item["coffee_values"], "#cc4144", "Có CF"),
        )
        for group_index, (group_values, color, label) in enumerate(groups):
            center_x = x0 + 65 + group_index * 100
            for offset, value in zip(offsets, group_values):
                elements.append(
                    f'<circle cx="{center_x + offset:.1f}" cy="{map_y(value):.1f}" r="5" fill="{color}" fill-opacity="0.82"/>'
                )
            group_mean = statistics.fmean(group_values)
            mean_y = map_y(group_mean)
            elements.extend(
                [
                    f'<line x1="{center_x - 30}" y1="{mean_y:.1f}" x2="{center_x + 30}" y2="{mean_y:.1f}" stroke="{color}" stroke-width="4"/>',
                    svg_text(center_x, bottom + 25, label, 12, "middle", "bold", color),
                    svg_text(center_x, bottom + 44, f"mean {group_mean:.2f}%", 11, "middle", "normal", color),
                ]
            )
    elements.append(svg_text(width / 2, 505, "Mỗi chấm là một phiên; đường ngang đậm là trung bình nhóm", 13, "middle"))
    write_svg("02_tai_co_khong_ca_phe.svg", width, height, elements)

    grouped = group_feature_summary(runs)
    labels = sorted(grouped)
    heatmap_svg(
        "03_heatmap_trung_binh_nhom.svg",
        "Đáp ứng EXPOSURE trung bình theo nhóm mẫu",
        [f"{label} (n={grouped[label]['count']})" for label in labels],
        [
            [float(grouped[label]["sensors"][sensor]["mean"]) for sensor in SENSORS]
            for label in labels
        ],
    )

    width = 1250
    height = 670
    left = 80
    right = 1215
    chart_width = right - left
    bar_width = chart_width / len(runs) * 0.68
    minimum_valid = [
        min(run["valid_fractions"][sensor][phase] for sensor in SENSORS for phase in PHASES) * 100
        for run in runs
    ]
    read_errors = [sum(run["read_errors"].values()) for run in runs]
    elements = [svg_text(width / 2, 38, "Chất lượng dữ liệu và lỗi đọc theo phiên", 22, "middle", "bold")]
    for index, value in enumerate(minimum_valid):
        x = left + (index + 0.5) * chart_width / len(runs)
        y = 305 - (value - 88) / 13 * 220
        elements.extend(
            [
                f'<rect x="{x - bar_width / 2:.1f}" y="{y:.1f}" width="{bar_width:.1f}" height="{305 - y:.1f}" fill="#4c78a8"/>',
                svg_text(x, y - 5, f"{value:.1f}", 10, "middle"),
            ]
        )
    threshold_y = 305 - (90 - 88) / 13 * 220
    elements.extend(
        [
            f'<line x1="{left}" y1="{threshold_y:.1f}" x2="{right}" y2="{threshold_y:.1f}" stroke="#cc4144" stroke-width="2" stroke-dasharray="7 5"/>',
            svg_text(left, 68, "Tỷ lệ hợp lệ nhỏ nhất của phiên (%)", 15, "start", "bold"),
            svg_text(right, threshold_y - 6, "Ngưỡng QC 90%", 12, "end", "bold", "#cc4144"),
        ]
    )
    maximum_errors = max(read_errors)
    for index, value in enumerate(read_errors):
        x = left + (index + 0.5) * chart_width / len(runs)
        y = 600 - value / max(maximum_errors, 1) * 225
        elements.extend(
            [
                f'<rect x="{x - bar_width / 2:.1f}" y="{y:.1f}" width="{bar_width:.1f}" height="{600 - y:.1f}" fill="#f28e2b"/>',
                svg_text(x, y - 5, value, 10, "middle"),
                svg_text(x, 620, index + 1, 11, "middle"),
            ]
        )
    elements.extend(
        [
            svg_text(left, 358, "Số lỗi đọc ghi nhận trong events.csv", 15, "start", "bold"),
            svg_text(width / 2, 650, "Thứ tự phiên trong ngày", 13, "middle", "bold"),
        ]
    )
    write_svg("04_chat_luong_va_loi_doc.svg", width, height, elements)

    width = 1250
    height = 790
    left = 90
    right = 1200
    times = [run["started_at"].hour + run["started_at"].minute / 60 for run in runs]
    series = (
        ("Nhiệt độ baseline", "baseline_temperature_c", "°C", "#cc4144"),
        ("Độ ẩm baseline", "baseline_humidity_pct", "%", "#2f69b1"),
        ("Áp suất baseline", "baseline_pressure_hpa", "hPa", "#4f9a52"),
    )
    elements = [svg_text(width / 2, 38, "Điều kiện môi trường theo thời gian", 22, "middle", "bold")]
    for panel_index, (title, key, unit, color) in enumerate(series):
        top = 75 + panel_index * 235
        bottom = top + 175
        values = [float(run["environmental"][key]) for run in runs]
        padding = max((max(values) - min(values)) * 0.12, 0.05)
        low = min(values) - padding
        high = max(values) + padding

        def map_x(value: float) -> float:
            return left + (value - 12.5) / 11 * (right - left)

        def map_y(value: float) -> float:
            return bottom - (value - low) / (high - low) * (bottom - top)

        gap_left = map_x(15)
        gap_right = map_x(21)
        elements.extend(
            [
                f'<rect x="{gap_left:.1f}" y="{top}" width="{gap_right - gap_left:.1f}" height="{bottom - top}" fill="#eeeeee"/>',
                svg_text(left, top - 12, f"{title} ({unit})", 15, "start", "bold"),
                f'<line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" stroke="#777"/>',
                f'<line x1="{left}" y1="{top}" x2="{left}" y2="{bottom}" stroke="#777"/>',
                svg_text(left - 8, top + 5, f"{high:.2f}", 11, "end"),
                svg_text(left - 8, bottom, f"{low:.2f}", 11, "end"),
            ]
        )
        points = " ".join(f"{map_x(time):.1f},{map_y(value):.1f}" for time, value in zip(times, values))
        elements.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2.5"/>')
        for time, value in zip(times, values):
            elements.append(f'<circle cx="{map_x(time):.1f}" cy="{map_y(value):.1f}" r="4.5" fill="{color}"/>')
        if panel_index == 2:
            for hour in (13, 14, 15, 18, 21, 22, 23):
                x = map_x(hour)
                elements.extend(
                    [
                        f'<line x1="{x:.1f}" y1="{bottom}" x2="{x:.1f}" y2="{bottom + 5}" stroke="#777"/>',
                        svg_text(x, bottom + 22, f"{hour}:00", 11, "middle"),
                    ]
                )
    elements.append(svg_text(width / 2, 775, "Giờ trong ngày; vùng xám là khoảng không có phiên đo", 13, "middle"))
    write_svg("05_moi_truong_theo_thoi_gian.svg", width, height, elements)


def generate_detailed_report(runs: list[dict[str, object]]) -> str:
    runs = sorted(runs, key=lambda run: run["started_at"])
    accepted = [run for run in runs if run["accepted"]]
    rejected = [run for run in runs if not run["accepted"]]
    group_counts = Counter(str(run["label"]) for run in runs)
    total_rows = sum(len(run["rows"]) for run in runs)
    total_errors = sum(sum(run["read_errors"].values()) for run in runs)
    error_devices = Counter()
    for run in runs:
        error_devices.update(run["read_errors"])
    group_summary = group_feature_summary(runs)
    duplicate_correlations = duplicate_sensor_correlations(runs)
    repeatability = repeatability_rows(runs)
    coffee_comparison = coffee_status_summary(runs)

    temperatures = [
        value
        for run in runs
        if (value := run["environmental"]["baseline_temperature_c"]) is not None
    ]
    humidities = [
        value
        for run in runs
        if (value := run["environmental"]["baseline_humidity_pct"]) is not None
    ]
    pressures = [
        value
        for run in runs
        if (value := run["environmental"]["baseline_pressure_hpa"]) is not None
    ]

    lines = [
        "# Báo cáo phân tích dữ liệu mùi ngày 2026-10-28",
        "",
        "> Báo cáo được tính trực tiếp từ `raw.csv`, `events.csv`, `metadata.json` và `summary.json` của từng phiên. Các thay đổi phần trăm đều dùng median BASELINE riêng của từng phiên; dấu âm nghĩa là tín hiệu thấp hơn baseline, không phải giá trị vật lý âm.",
        "",
        "## 1. Tóm tắt điều hành",
        "",
        f"- Có **{len(runs)} phiên hoàn tất**, tổng cộng **{total_rows:,} dòng dữ liệu thô**.",
        f"- Theo tiêu chí tối thiểu **{MIN_VALID_FRACTION:.0%} mẫu hợp lệ ở cả BASELINE, EXPOSURE và RECOVERY cho cả 5 kênh**, có **{len(accepted)} phiên đạt** và **{len(rejected)} phiên cần xem lại/loại**.",
        f"- Ghi nhận **{total_errors} lỗi đọc cảm biến** trong `events.csv`; lỗi rải rác không đồng nghĩa phiên hỏng nếu tỷ lệ hợp lệ vẫn đạt ngưỡng.",
        "- Bộ dữ liệu là một **đợt thăm dò hỗn hợp**, gồm mẫu người, không khí, cà phê ít/nhiều và hỗn hợp Tài–cà phê; không nên dùng trực tiếp như một bài toán định danh người thuần túy.",
        "- Tất cả phiên diễn ra trong cùng một ngày nhưng chia thành hai khối thời gian buổi trưa–chiều và buổi tối; khác biệt giữa hai khối có thể chứa drift theo thời gian và thay đổi môi trường.",
        "",
        "### Phân bố nhãn",
        "",
        "| Nhãn diễn giải | Số phiên |",
        "|---|---:|",
    ]
    for label, count in sorted(group_counts.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"| {markdown_escape(label)} | {count} |")

    lines.extend(
        [
            "",
            "## 2. Cấu hình và thiết kế thí nghiệm",
            "",
            "Từ metadata, các phiên dùng backend phần cứng và phương pháp đổi đầu ống thủ công, không dùng van tự động. Pha lõi có cấu hình danh định:",
            "",
            "```text",
            "BASELINE: 60 giây",
            "EXPOSURE: 120 giây",
            "RECOVERY: 60 giây",
            "Tần số lấy mẫu: khoảng 1 Hz",
            "```",
            "",
            "Mảng cảm biến được phân tích gồm BME688 gas resistance, MQ135-1, MQ3-1, MQ135-2 và MQ3-2. Nhiệt độ, độ ẩm và áp suất được dùng để đánh giá môi trường, không coi là dấu vân tay mùi.",
            "",
            "### Trình tự các phiên",
            "",
            "| # | Bắt đầu | Nhãn | Loại | Dòng | Thời lượng (s) | BASE/EXP/REC | Lỗi đọc | QC |",
            "|---:|---:|---|---|---:|---:|---:|---:|---|",
        ]
    )
    for index, run in enumerate(runs, start=1):
        phase_counts = "/".join(str(len(run["phase_rows"][phase])) for phase in PHASES)
        qc = "Đạt" if run["accepted"] else "Xem lại"
        lines.append(
            f"| {index} | {run['started_at'].strftime('%H:%M:%S')} | {markdown_escape(run['label'])} | "
            f"{markdown_escape(run['category'])} | {len(run['rows'])} | {run['duration']:.1f} | "
            f"{phase_counts} | {sum(run['read_errors'].values())} | **{qc}** |"
        )

    lines.extend(
        [
            "",
            "## 3. Kiểm tra chất lượng dữ liệu",
            "",
            "Tiêu chí QC của báo cáo: từng cảm biến phải có ít nhất 90% mẫu hợp lệ trong mỗi pha lõi. Điểm BME chỉ hợp lệ khi `status=OK`, dữ liệu fresh, gas valid, heater stable và new data; MQ phải có `status=OK`, fresh và quality hợp lệ.",
            "",
            "### Phiên cần xem lại",
            "",
        ]
    )
    if rejected:
        for run in rejected:
            lines.append(f"- `{run['folder']}`: {'; '.join(run['quality_reasons'])}.")
    else:
        lines.append("- Không có phiên nào dưới ngưỡng QC đã đặt.")

    lines.extend(
        [
            "",
            "### Lỗi đọc theo thiết bị",
            "",
            "| Thiết bị | Số lỗi |",
            "|---|---:|",
        ]
    )
    for device, count in error_devices.most_common():
        lines.append(f"| `{device}` | {count} |")
    if not error_devices:
        lines.append("| Không ghi nhận | 0 |")

    lines.extend(
        [
            "",
            "![Chất lượng dữ liệu và lỗi đọc](./report_assets/04_chat_luong_va_loi_doc.svg)",
            "",
            "Biểu đồ cho thấy mọi phiên đều vượt ngưỡng 90%, nhưng số lỗi đọc khác nhau rõ giữa các phiên. Vì vậy nên giữ đồng thời hai tiêu chí: tỷ lệ mẫu hợp lệ để quyết định nhận/loại và số lỗi để theo dõi sức khỏe phần cứng.",
        ]
    )

    lines.extend(
        [
            "",
            "### Tỷ lệ hợp lệ tối thiểu theo phiên",
            "",
            "Bảng dưới lấy giá trị thấp nhất trong ba pha lõi cho từng cảm biến. Đây là cách nhìn bảo thủ: một pha kém sẽ kéo tỷ lệ của phiên xuống.",
            "",
            "| Phiên | BME | MQ135-1 | MQ3-1 | MQ135-2 | MQ3-2 |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for run in runs:
        fractions = [
            min(run["valid_fractions"][sensor].values()) * 100 for sensor in SENSORS
        ]
        lines.append(
            f"| `{run['folder']}` | " + " | ".join(f"{value:.1f}%" for value in fractions) + " |"
        )

    lines.extend(
        [
            "",
            "## 4. Điều kiện môi trường",
            "",
            f"- Nhiệt độ baseline: **{min(temperatures):.2f}–{max(temperatures):.2f} °C**.",
            f"- Độ ẩm baseline: **{min(humidities):.2f}–{max(humidities):.2f}%**.",
            f"- Áp suất baseline: **{min(pressures):.2f}–{max(pressures):.2f} hPa**.",
            "",
            "Biên độ môi trường giữa các phiên đủ lớn để có thể ảnh hưởng cảm biến MOS. Khi xây dựng mô hình, nên chia train/test theo khối thời gian hoặc ngày và không đưa trực tiếp nhiệt độ/độ ẩm vào đặc trưng định danh nếu chưa kiểm soát confounding.",
            "",
            "![Điều kiện môi trường theo thời gian](./report_assets/05_moi_truong_theo_thoi_gian.svg)",
            "",
            "Vùng xám biểu diễn khoảng thời gian không có phiên đo. Khối buổi tối bắt đầu với nhiệt độ và áp suất khác rõ khối buổi chiều; đây là một biến gây nhiễu quan trọng khi so sánh các nhãn nằm ở hai khối khác nhau.",
            "",
            "| Phiên | Nhiệt độ nền (°C) | Δ nhiệt độ EXP | Độ ẩm nền (%) | Δ độ ẩm EXP | Áp suất nền (hPa) |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for run in runs:
        environment = run["environmental"]
        lines.append(
            f"| `{run['folder']}` | {fmt(environment['baseline_temperature_c'])} | "
            f"{fmt(environment['delta_temperature_c'])} | {fmt(environment['baseline_humidity_pct'])} | "
            f"{fmt(environment['delta_humidity_pct'])} | {fmt(environment['baseline_pressure_hpa'])} |"
        )

    lines.extend(
        [
            "",
            "## 5. Đáp ứng cảm biến theo phiên",
            "",
            "Giá trị là trung bình EXPOSURE sau khi chuẩn hóa theo median BASELINE của chính phiên:",
            "",
            "```text",
            "response_pct = 100 × (signal - baseline_median) / |baseline_median|",
            "```",
            "",
            "### Heatmap toàn bộ phiên",
            "",
            "![Heatmap đáp ứng toàn bộ phiên](./report_assets/01_heatmap_dap_ung_toan_bo.svg)",
            "",
            "Heatmap cho thấy BME688 và MQ3-1 tạo tương phản rõ nhất ở nhiều mẫu cà phê/người, trong khi hai kênh MQ135 và MQ3-2 thường có biên độ nhỏ hơn. Phiên không khí có MQ135-1 tăng mạnh, là dấu hiệu cần xem xét carry-over, drift hoặc thao tác đổi ống trước khi dùng làm mẫu nền chuẩn.",
            "",
            "| Phiên | Nhãn | BME (%) | MQ135-1 (%) | MQ3-1 (%) | MQ135-2 (%) | MQ3-2 (%) |",
            "|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for run in runs:
        values = [run["features"][sensor]["exposure_mean"] for sensor in SENSORS]
        lines.append(
            f"| `{run['folder']}` | {markdown_escape(run['label'])} | "
            + " | ".join(fmt(value) for value in values)
            + " |"
        )

    lines.extend(
        [
            "",
            "### So sánh trực tiếp: Tài có và không có cà phê",
            "",
            "Nhóm **không cà phê** gồm 5 phiên `Tai_*`. Nhóm **có cà phê** gồm 5 phiên `TaivsCF*` và phiên `BaseTai_ExposeTaivsCF`. Đây là so sánh gần nhất với câu hỏi phát hiện cà phê trên người trong bộ dữ liệu hiện tại.",
            "",
            "![So sánh Tài có và không có cà phê](./report_assets/02_tai_co_khong_ca_phe.svg)",
            "",
            "| Cảm biến | Tài không cà phê, mean (%) | Tài có cà phê, mean (%) | Chênh lệch có − không (% điểm) |",
            "|---|---:|---:|---:|",
        ]
    )
    for item in coffee_comparison:
        lines.append(
            f"| {item['label']} | {fmt(item['pure_mean'])} | {fmt(item['coffee_mean'])} | {fmt(item['difference'])} |"
        )
    lines.extend(
        [
            "",
            "Các điểm dữ liệu còn chồng lấn ở cả năm cảm biến. BME688 và MQ3-1 có dịch chuyển trung bình theo hướng phù hợp với một số phiên cà phê, nhưng không tạo ranh giới sạch; MQ135-1 còn giảm ở nhóm có cà phê do một phiên Tài thuần tăng mạnh. Vì vậy dữ liệu hiện tại chỉ đủ làm proof-of-concept, chưa đủ đặt ngưỡng phát hiện ổn định.",
        ]
    )

    lines.extend(
        [
            "",
            "### Trung bình theo nhóm mẫu",
            "",
            "Các nhóm chỉ có một phiên mang tính mô tả, không phải ước lượng thống kê. Khoảng trong ngoặc là min–max giữa các phiên cùng nhãn.",
            "",
            "| Nhãn | n | BME (%) | MQ135-1 (%) | MQ3-1 (%) | MQ135-2 (%) | MQ3-2 (%) |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for label, values in sorted(group_summary.items()):
        cells = []
        for sensor in SENSORS:
            stats = values["sensors"][sensor]
            if values["count"] == 1:
                cells.append(fmt(stats["mean"]))
            else:
                cells.append(
                    f"{fmt(stats['mean'])} ({fmt(stats['minimum'])}…{fmt(stats['maximum'])})"
                )
        lines.append(
            f"| {markdown_escape(label)} | {values['count']} | " + " | ".join(cells) + " |"
        )

    lines.extend(
        [
            "",
            "![Heatmap trung bình theo nhóm](./report_assets/03_heatmap_trung_binh_nhom.svg)",
            "",
            "Hai mức cà phê riêng đều tác động mạnh lên BME688 và MQ3-1, nhưng thứ tự `ít`–`nhiều` không nhất quán giữa hai khối thời gian. Tương tự, hỗn hợp Tài–cà phê nhiều lúc tạo đáp ứng rõ, lúc gần nền; chưa thể suy ra quan hệ liều–đáp ứng đáng tin cậy.",
        ]
    )

    lines.extend(
        [
            "",
            "## 6. Đặc trưng động học và phục hồi",
            "",
            "Ngoài trung bình EXPOSURE, báo cáo tính slope trong EXPOSURE, AUC và trung bình 10 mẫu cuối RECOVERY. Bảng dưới tập trung vào BME688 để dễ đọc; các đặc trưng tương tự đã được tính cho bốn kênh MQ.",
            "",
            "| Phiên | Nhãn | Q10 EXP (%) | Q90 EXP (%) | Slope (%/s) | AUC (%·s) | Cuối REC (%) |",
            "|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for run in runs:
        feature = run["features"]["bme"]
        lines.append(
            f"| `{run['folder']}` | {markdown_escape(run['label'])} | {fmt(feature['q10'])} | "
            f"{fmt(feature['q90'])} | {fmt(feature['slope_pct_per_s'], 4)} | "
            f"{fmt(feature['auc_pct_s'])} | {fmt(feature['recovery_end'])} |"
        )

    lines.extend(
        [
            "",
            "## 7. Độ lặp lại và quan hệ giữa cảm biến",
            "",
            "Cosine dưới đây được tính trên vector 5 chiều gồm trung bình EXPOSURE của năm kênh. Giá trị gần 1 nghĩa là hướng đáp ứng tương tự; giá trị âm nghĩa là hai phiên có hướng đáp ứng đối lập. Với số phiên ít, đây chỉ là chỉ báo thăm dò.",
            "",
            "| Nhãn có lặp | Số phiên | Số cặp | Cosine trung vị | Cosine nhỏ nhất |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for row in repeatability:
        lines.append(
            f"| {markdown_escape(row['label'])} | {row['count']} | {row['pair_count']} | "
            f"{fmt(row['median_cosine'], 3)} | {fmt(row['minimum_cosine'], 3)} |"
        )

    lines.extend(
        [
            "",
            "### Tương quan hai cảm biến cùng loại",
            "",
        ]
    )
    for label, value in duplicate_correlations.items():
        lines.append(f"- {label}: **r = {fmt(value, 3)}** trên các pha lõi của toàn bộ phiên.")
    lines.extend(
        [
            "",
            "Hai cảm biến cùng loại không bắt buộc phải trùng tuyệt đối vì sai số phần cứng, vị trí và độ nhạy khác nhau. Tuy nhiên, tương quan thấp hoặc đổi dấu kéo dài là dấu hiệu cần kiểm tra đấu nối, hiệu chuẩn và độ ổn định kênh.",
            "",
            "## 8. Diễn giải theo nhóm thí nghiệm",
            "",
            "### Mẫu không khí",
            "",
            "Phiên không khí là mốc kiểm tra nền/carry-over. Vì vẫn chạy quy trình BASELINE–EXPOSURE–RECOVERY, đáp ứng khác 0 phản ánh drift môi trường, thao tác đổi ống hoặc tồn dư trong đường khí chứ không nên được diễn giải là một mùi đích.",
            "",
            "### Mẫu cà phê ít và cà phê nhiều",
            "",
            "Hai mức cà phê có hai lần đo ở hai khối thời gian khác nhau. Đây là nhóm phù hợp để kiểm tra hệ thống có giữ được thứ tự liều lượng và độ lặp lại qua thời gian hay không. Chỉ nên kết luận quan hệ liều–đáp ứng khi đa số cảm biến cùng cho xu hướng nhất quán và có thêm nhiều lần lặp độc lập.",
            "",
            "### Mẫu Tài",
            "",
            "Có năm phiên Tài thuần, nhiều hơn các nhãn người khác. Đây là nhóm tốt nhất trong ngày để ước lượng độ lặp lại nội-người, nhưng các phiên nằm ở hai khối thời gian nên chênh lệch có thể đồng thời chứa drift theo phiên và môi trường.",
            "",
            "### Hỗn hợp Tài–cà phê",
            "",
            "Các phiên `TaivsCF*` kiểm tra ảnh hưởng của nhiễu/mùi che lấp. Không nên gán chúng là mẫu Tài thuần trong bài toán định danh. Có thể dùng chúng sau này như tập stress-test: mô hình nhận dạng Tài có còn giữ đúng khi xuất hiện cà phê hay chuyển sang `UNKNOWN`.",
            "",
            "### Minh và Quy",
            "",
            "Mỗi người chỉ có một phiên trong ngày nên chỉ dùng để mô tả đáp ứng, chưa đủ để đánh giá độ lặp lại hoặc xây prototype cá nhân đáng tin cậy.",
            "",
            "## 9. Hạn chế của bộ dữ liệu",
            "",
            "1. Tên/nhãn mẫu chủ yếu nằm trong tên thư mục; `person_code`, `source` và thông tin vị trí cơ thể trong metadata còn trống.",
            "2. Đổi đầu ống và purge thủ công làm thời gian chờ thay đổi giữa các phiên.",
            "3. Một số nhãn chỉ có một phiên; không đủ để ước lượng phân bố hoặc kiểm định thống kê.",
            "4. Tất cả dữ liệu nằm trong một ngày; chưa đánh giá được độ ổn định khác ngày.",
            "5. Hai khối thời gian có điều kiện môi trường khác nhau, dễ tạo confounding giữa nhãn và thời điểm đo.",
            "6. Có lỗi đọc ADS1115/BME rải rác; cần theo dõi lỗi theo kênh thay vì chỉ nhìn đồ thị đã nội suy.",
            "7. Mẫu hỗn hợp và mẫu người thuần không nên gộp chung khi huấn luyện định danh.",
            "",
            "## 10. Khuyến nghị sử dụng dữ liệu",
            "",
            "- Dùng ngày này cho **phân tích thăm dò, kiểm tra pipeline, đánh giá sensor và carry-over**.",
            "- Chưa dùng ngày này làm bộ huấn luyện định danh hoàn chỉnh vì Minh và Quy chỉ có một phiên và thiết kế có nhiều mẫu cà phê/hỗn hợp.",
            "- Khi huấn luyện, tách rõ `air`, `coffee_low`, `coffee_high`, `Tai`, `Tai+coffee`, `Minh`, `Quy`; không suy nhãn từ chuỗi con mơ hồ.",
            "- Chỉ dùng các phiên đạt QC; các phiên cần xem lại phải được kiểm tra biểu đồ và `events.csv` trước khi giữ.",
            "- Fit scaler và chọn đặc trưng trên tập train; không dùng dữ liệu augmented hoặc cùng source run ở cả train và test.",
            "- Bổ sung tối thiểu 10–15 phiên thật/người trên nhiều ngày, cùng vị trí cơ thể và quy trình lấy mẫu.",
            "- Thu mẫu reference/không khí sạch xen kẽ để định lượng drift và tồn dư trong đường khí.",
            "",
            "## 11. Biểu đồ từng phiên",
            "",
            "Mỗi mục liên kết trực tiếp tới hai biểu đồ có sẵn trong thư mục phiên.",
            "",
        ]
    )
    for run in runs:
        folder = run["folder"]
        lines.extend(
            [
                "<details>",
                f"<summary><strong>{markdown_escape(run['label'])}</strong> — {run['started_at'].strftime('%H:%M:%S')} — {'Đạt QC' if run['accepted'] else 'Cần xem lại'}</summary>",
                "",
                f"![Tín hiệu gốc {markdown_escape(run['label'])}](./{folder}/signals.png)",
                "",
                f"![Tín hiệu chuẩn hóa {markdown_escape(run['label'])}](./{folder}/normalized.png)",
                "",
                "</details>",
                "",
            ]
        )

    lines.extend(
        [
            "## 12. Kết luận",
            "",
            "Bộ dữ liệu ngày 2026-10-28 có giá trị nhất như một **bộ thử nghiệm đáp ứng cảm biến và khả năng chống nhiễu mùi cà phê**. Dữ liệu có nhiều phiên Tài và các cặp cà phê/hỗn hợp, giúp quan sát độ lặp lại, drift và ảnh hưởng của mùi che lấp. Tuy nhiên, số lần lặp giữa các người chưa cân bằng và metadata mẫu chưa đầy đủ, vì vậy chưa nên dùng riêng ngày này để kết luận khả năng nhận dạng từng người.",
            "",
            "---",
            "",
            f"Báo cáo được sinh bởi `analysis/generate_2026_10_28_report.py` từ dữ liệu hiện có trong `{DATA_ROOT.relative_to(ROOT).as_posix()}`.",
        ]
    )
    return "\n".join(lines) + "\n"


def generate_report(runs: list[dict[str, object]]) -> str:
    runs = sorted(runs, key=lambda run: run["started_at"])
    accepted = [run for run in runs if run["accepted"]]
    rejected = [run for run in runs if not run["accepted"]]
    total_rows = sum(len(run["rows"]) for run in runs)
    total_errors = sum(sum(run["read_errors"].values()) for run in runs)
    error_devices = Counter()
    for run in runs:
        error_devices.update(run["read_errors"])
    comparison = coffee_status_summary(runs)
    grouped = group_feature_summary(runs)
    repeatability = {row["label"]: row for row in repeatability_rows(runs)}
    duplicate_correlations = duplicate_sensor_correlations(runs)
    temperatures = [float(run["environmental"]["baseline_temperature_c"]) for run in runs]
    humidities = [float(run["environmental"]["baseline_humidity_pct"]) for run in runs]
    pressures = [float(run["environmental"]["baseline_pressure_hpa"]) for run in runs]
    human_only = [run for run in runs if run["label"] in {"Tài", "Minh", "Quy"}]
    human_coffee = [run for run in runs if run["label"] in COFFEE_ON_TAI_LABELS]
    coffee_only = [run for run in runs if run["label"] in {"Cà phê ít", "Cà phê nhiều"}]
    air_runs = [run for run in runs if run["label"] == "Không khí"]
    paired_runs = [run for run in runs if run["label"] == "Tài nền → Tài + cà phê"]

    lines = [
        "# Phân tích dữ liệu phát hiện mùi cà phê trên người",
        "",
        "README này tổng hợp trực tiếp phạm vi dữ liệu, pipeline phân tích, biểu đồ và kết quả của bộ dữ liệu ngày **2026-10-28**. Mục tiêu chính là đánh giá tín hiệu e-nose có đủ thông tin để phân biệt **người không mang cà phê** và **người có mùi cà phê** hay không.",
        "",
        "## 1. Kết luận nhanh",
        "",
        f"Bộ dữ liệu có **{len(runs)} phiên hoàn tất** và **{total_rows:,} dòng dữ liệu thô**:",
        "",
        "| Nhóm dữ liệu | Số phiên | Vai trò |",
        "|---|---:|---|",
        f"| Người không cà phê | {len(human_only)} | Nhãn 0; gồm 5 Tài, 1 Minh, 1 Quy |",
        f"| Người có cà phê | {len(human_coffee)} | Nhãn 1; hiện chỉ có Tài |",
        f"| Cà phê riêng | {len(coffee_only)} | Đối chứng cà phê ít/nhiều |",
        f"| Không khí | {len(air_runs)} | Mẫu trắng môi trường |",
        f"| Phiên paired đặc biệt | {len(paired_runs)} | Baseline Tài → Exposure Tài+cà phê |",
        "",
        "Các kết quả chính:",
        "",
        f"- **{len(accepted)}/{len(runs)} phiên đạt QC**; hai phiên `CF_nhieu` cần xem lại vì baseline không ổn định.",
        f"- Có **{total_errors} lỗi đọc rải rác**, nhưng tỷ lệ dữ liệu hợp lệ của các pha lõi vẫn trên 90% ở tất cả phiên.",
        f"- Nhiệt độ baseline thay đổi **{min(temperatures):.2f}–{max(temperatures):.2f} °C**, độ ẩm **{min(humidities):.2f}–{max(humidities):.2f}%** và áp suất **{min(pressures):.2f}–{max(pressures):.2f} hPa**.",
        f"- Hai lần đo cà phê ít có cosine **{fmt(repeatability['Cà phê ít']['median_cosine'], 3)}**; cà phê nhiều **{fmt(repeatability['Cà phê nhiều']['median_cosine'], 3)}**; hai phiên `TaivsCF` **{fmt(repeatability['Tài + cà phê']['median_cosine'], 3)}**.",
        f"- Năm phiên Tài không cà phê có cosine trung vị chỉ **{fmt(repeatability['Tài']['median_cosine'], 3)}**, cho thấy độ lặp lại nội-người còn thấp.",
        "- BME688 và MQ3-1 có thay đổi trung bình giữa hai trạng thái Tài, nhưng các điểm vẫn chồng lấn; chưa có cảm biến đơn lẻ tạo ranh giới phát hiện sạch.",
        "- Kết luận hiện tại: **có tín hiệu để tiếp tục nghiên cứu**, nhưng chưa đủ dữ liệu để xây bộ phát hiện cà phê trên người có khả năng tổng quát hóa.",
        "",
        "## 2. Phạm vi dữ liệu được sử dụng",
        "",
        "Mỗi thư mục có `raw.csv`, `events.csv`, `metadata.json` và `summary.json` được xem là một phiên độc lập. `report_assets/` chỉ chứa biểu đồ đầu ra và không được tính là dữ liệu.",
        "",
        "Hai khối đo trong ngày:",
        "",
        "```text",
        "Khối 1 (12:58–14:13): Không khí → CF ít → Tài → Tài → paired Tài/CF → CF nhiều → Tài+CF → Tài+CF",
        "Khối 2 (22:00–23:18): Minh → Tài → Tài → Tài → Quy → CF nhiều → Tài+CF nhiều → Tài+CF ít → CF ít",
        "```",
        "",
        "Ba pha dùng để phân tích:",
        "",
        "| Pha | Thời gian danh định | Vai trò |",
        "|---|---:|---|",
        "| Baseline | 60 giây | Ước lượng mức nền riêng của từng cảm biến |",
        "| Exposure | 120 giây | Quan sát đáp ứng khi tiếp xúc mẫu |",
        "| Recovery | 60 giây | Kiểm tra khả năng quay lại baseline |",
        "",
        "Các pha `MONITOR` và `WAIT_*` được giữ để kiểm tra quy trình, nhưng không dùng làm đặc trưng nhận dạng. Phiên `BaseTai_ExposeTaivsCF` được giữ như phép đo paired và **không tính là một mẫu nhãn 1 độc lập** trong so sánh nhị phân chính.",
        "",
        "## 3. Pipeline phân tích",
        "",
        "### 3.1. Gán nhãn",
        "",
        "| Nhãn thư mục | `sample_type` | `coffee_present` | `subject_id` |",
        "|---|---|:---:|---|",
        "| `Tai`, `aMinh`, `aQuy` | `HUMAN_ONLY` | 0 | Tài / Minh / Quy |",
        "| `TaivsCF*` | `HUMAN_COFFEE` | 1 | Tài |",
        "| `CF_it`, `CF_nhieu` | `COFFEE_ONLY` | NA | NA |",
        "| `khongkhi` | `AIR` | NA | NA |",
        "| `BaseTai_ExposeTaivsCF` | `PAIRED` | Theo pha | Tài |",
        "",
        "Không tự động gán BASELINE của mọi phiên thành nhãn 0. Baseline thông thường chỉ là mức nền dùng để hiệu chỉnh tín hiệu.",
        "",
        "### 3.2. Lọc dữ liệu hợp lệ",
        "",
        "BME688 chỉ được giữ khi:",
        "",
        "```text",
        "bme_status == \"OK\"",
        "bme_fresh == True",
        "gas_valid == True",
        "heater_stable == True",
        "new_data == True",
        "```",
        "",
        "MQ chỉ được giữ khi `status=OK`, dữ liệu `fresh` và `quality=OK`. Hai giá trị MQ3 âm được đánh dấu `NEGATIVE` nên không được dùng khi tính đặc trưng.",
        "",
        "### 3.3. Chuẩn hóa theo baseline",
        "",
        "Mỗi phiên và mỗi cảm biến được chuẩn hóa độc lập bằng median BASELINE:",
        "",
        "```text",
        "response_pct = 100 × (signal - median_baseline) / |median_baseline|",
        "```",
        "",
        "Số âm nghĩa là tín hiệu thấp hơn baseline; số dương nghĩa là tín hiệu cao hơn baseline. Dấu âm không phải giá trị vật lý âm.",
        "",
        "### 3.4. Đặc trưng được trích xuất",
        "",
        "| Nhóm | Đặc trưng |",
        "|---|---|",
        "| Cường độ | Mean, middle mean, Q10, Q90, min, max |",
        "| Động học | Slope trong exposure |",
        "| Tích phân | AUC của exposure |",
        "| Phục hồi | Trung bình 10 mẫu cuối recovery |",
        "| Chất lượng | Tỷ lệ hợp lệ từng cảm biến/từng pha, baseline stability |",
        "",
        "### 3.5. Nguyên tắc đánh giá",
        "",
        "Một phiên hoàn chỉnh là một mẫu độc lập. Không chia ngẫu nhiên từng dòng 1 Hz vào train/test và không tách phiên paired thành hai mẫu độc lập. Với dữ liệu hiện tại chỉ có một ngày và nhóm dương chỉ có Tài, PCA/classification nếu có chỉ mang tính thăm dò, không phải bằng chứng hiệu năng triển khai.",
        "",
        "## 4. Kiểm tra chất lượng dữ liệu",
        "",
        "**Phương pháp:** tính tỷ lệ hợp lệ cho từng cảm biến trong BASELINE, EXPOSURE và RECOVERY; lấy tỷ lệ nhỏ nhất làm chỉ báo bảo thủ của phiên. Đồng thời đếm `read_error` trong `events.csv` và đọc cờ baseline stability từ `summary.json`.",
        "",
        "![Chất lượng dữ liệu và lỗi đọc](./report_assets/04_chat_luong_va_loi_doc.svg)",
        "",
        "**Kết quả:**",
        "",
        f"- Cả 17 phiên đều có tỷ lệ hợp lệ tối thiểu trên 90%, nhưng chỉ **{len(accepted)} phiên đạt đầy đủ** khi xét thêm baseline stability.",
    ]
    for run in rejected:
        lines.append(f"- `{run['folder']}`: {'; '.join(run['quality_reasons'])}.")
    lines.extend(
        [
            f"- Tổng số lỗi đọc: **{total_errors}**; nhiều nhất là MQ135-1 ({error_devices['mq135_1']}), MQ3-1 ({error_devices['mq3_1']}) và MQ135-2 ({error_devices['mq135_2']}).",
            "- Hai giá trị âm chỉ xuất hiện đơn lẻ ở MQ3 và đều có `quality=NEGATIVE`; đây là lỗi điểm, không phải toàn bộ kênh bị âm.",
            "- Phiên `CF_nhieu` buổi chiều bất ổn ở BME gas; phiên `CF_nhieu` buổi tối bất ổn ở độ ẩm. Không nên dùng hai phiên này làm bằng chứng chính cho đáp ứng đã hiệu chỉnh nền.",
            "",
            "## 5. Điều kiện môi trường và drift theo thời gian",
            "",
            "**Phương pháp:** lấy median nhiệt độ, độ ẩm và áp suất trong BASELINE của từng phiên, sau đó sắp theo giờ bắt đầu.",
            "",
            "![Điều kiện môi trường theo thời gian](./report_assets/05_moi_truong_theo_thoi_gian.svg)",
            "",
            "**Kết quả:**",
            "",
            f"- Nhiệt độ baseline biến thiên **{min(temperatures):.2f}–{max(temperatures):.2f} °C**.",
            f"- Độ ẩm baseline biến thiên **{min(humidities):.2f}–{max(humidities):.2f}%**.",
            f"- Áp suất baseline biến thiên **{min(pressures):.2f}–{max(pressures):.2f} hPa**.",
            "- Khối buổi tối bắt đầu ở điều kiện khác rõ khối buổi chiều. Vì nhãn và thời điểm đo chưa cân bằng, mô hình có thể học môi trường thay vì mùi cà phê.",
            "",
            "## 6. Heatmap đáp ứng của toàn bộ phiên",
            "",
            "**Phương pháp:** tính đáp ứng trung bình trong 120 giây EXPOSURE cho năm cảm biến, sau đó đặt các phiên theo đúng thứ tự thời gian.",
            "",
            "![Heatmap đáp ứng toàn bộ phiên](./report_assets/01_heatmap_dap_ung_toan_bo.svg)",
            "",
            "**Kết quả:**",
            "",
            "- BME688 thường giảm khi gặp cà phê; MQ3-1 thường tăng, nhưng biên độ thay đổi mạnh giữa các lần đo.",
            "- Phiên không khí vẫn có MQ135-1 tăng rõ, cho thấy carry-over, thao tác đổi ống hoặc drift chưa được kiểm soát hoàn toàn.",
            "- Hai kênh MQ135 và hai kênh MQ3 cùng loại không tạo đáp ứng tương đồng ổn định.",
            "- Không có một mẫu màu duy nhất tách sạch toàn bộ Tài+cà phê khỏi Tài không cà phê.",
            "",
            "## 7. So sánh Tài có và không có cà phê",
            "",
            "**Phương pháp:** dùng 5 phiên Tài thuần làm nhóm không cà phê và 4 phiên `TaivsCF*` làm nhóm có cà phê. Phiên paired đặc biệt không được tính như mẫu độc lập. Mỗi điểm là trung bình EXPOSURE của một phiên.",
            "",
            "![So sánh Tài có và không có cà phê](./report_assets/02_tai_co_khong_ca_phe.svg)",
            "",
            "Giá trị trung bình:",
            "",
            "| Cảm biến | Tài không CF | Tài có CF | Chênh lệch có − không |",
            "|---|---:|---:|---:|",
        ]
    )
    for item in comparison:
        lines.append(
            f"| {item['label']} | {fmt(item['pure_mean'])}% | {fmt(item['coffee_mean'])}% | {fmt(item['difference'])} điểm % |"
        )
    lines.extend(
        [
            "",
            "**Kết quả:**",
            "",
            "- BME688 giảm mạnh hơn và MQ3-1 tăng hơn ở nhóm Tài+cà phê về trung bình.",
            "- Tuy nhiên, điểm của hai nhóm vẫn chồng lấn trên cả năm cảm biến.",
            "- MQ135-1 bị chi phối bởi một phiên Tài thuần tăng mạnh, nên trung bình nhóm không cà phê cao hơn nhóm có cà phê.",
            "- Chưa thể đặt một threshold đơn cảm biến đáng tin cậy. Cần kết hợp nhiều đặc trưng và thu thêm dữ liệu paired khác ngày.",
            "",
            "## 8. So sánh các nhóm mẫu",
            "",
            "**Phương pháp:** gộp các phiên cùng nhãn và tính trung bình đáp ứng EXPOSURE. Các nhóm chỉ có một phiên được xem là mô tả, không phải ước lượng thống kê.",
            "",
            "![Heatmap trung bình theo nhóm](./report_assets/03_heatmap_trung_binh_nhom.svg)",
            "",
            "**Kết quả:**",
            "",
            "- Cà phê riêng tác động rõ nhất lên BME688 và MQ3-1.",
            "- Thứ tự cà phê ít–nhiều không ổn định giữa hai khối thời gian, nên chưa chứng minh được quan hệ liều–đáp ứng.",
            "- Hai phiên `TaivsCF` không ghi mức cà phê khá giống nhau, nhưng `TaivsCF_it` và `TaivsCF_nhieu` không giữ cùng hướng trên mọi cảm biến.",
            "- Phiên paired cho thấy thay đổi khi chuyển từ Tài sang Tài+cà phê, nhưng vẫn đồng thời chứa ảnh hưởng thứ tự pha và thời gian.",
            "",
            "## 9. Động học BME688 và recovery",
            "",
            "**Phương pháp:** với mỗi phiên, tính Q10, Q90, slope, AUC trong EXPOSURE và trung bình 10 mẫu cuối RECOVERY của BME688.",
            "",
            "| Phiên | Nhãn | Q10 EXP | Q90 EXP | Slope (%/s) | AUC (%·s) | Cuối recovery |",
            "|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for run in runs:
        feature = run["features"]["bme"]
        lines.append(
            f"| `{run['folder']}` | {markdown_escape(run['label'])} | {fmt(feature['q10'])}% | {fmt(feature['q90'])}% | {fmt(feature['slope_pct_per_s'], 4)} | {fmt(feature['auc_pct_s'])} | {fmt(feature['recovery_end'])}% |"
        )
    lines.extend(
        [
            "",
            "**Kết quả:**",
            "",
            "- Cùng một nhãn có thể khác nhau về slope và mức recovery, cho thấy chỉ dùng exposure mean sẽ làm mất thông tin động học.",
            "- Một số phiên cuối recovery vẫn lệch khỏi baseline; purge và thời gian hồi phục cần được chuẩn hóa trước khi thu bộ dữ liệu chính thức.",
            "- Phiên paired nên được phân tích riêng theo chênh lệch đặc trưng giữa trạng thái Tài nền và Tài+cà phê, không đưa trực tiếp vào tập phân loại như một run bình thường.",
            "",
            "## 10. Độ lặp lại và tính nhất quán của cảm biến",
            "",
            "**Phương pháp:** mỗi phiên được nén thành vector 5 chiều gồm đáp ứng EXPOSURE trung bình của năm kênh; cosine được tính giữa các phiên cùng nhãn.",
            "",
            "| Nhãn có lặp | Số phiên | Cosine trung vị | Cosine nhỏ nhất |",
            "|---|---:|---:|---:|",
        ]
    )
    for label in ("Cà phê ít", "Cà phê nhiều", "Tài", "Tài + cà phê"):
        row = repeatability[label]
        lines.append(
            f"| {label} | {row['count']} | {fmt(row['median_cosine'], 3)} | {fmt(row['minimum_cosine'], 3)} |"
        )
    lines.extend(
        [
            "",
            "**Kết quả:**",
            "",
            f"- MQ135-1 ↔ MQ135-2 có tương quan **r={fmt(duplicate_correlations['MQ135-1 ↔ MQ135-2'], 3)}**; MQ3-1 ↔ MQ3-2 có **r={fmt(duplicate_correlations['MQ3-1 ↔ MQ3-2'], 3)}**.",
            "- Tương quan gần 0 cho thấy hai cảm biến cùng loại chưa hoạt động như các bản sao tương đương; cần kiểm tra đấu nối, vị trí, hiệu chuẩn và độ ổn định từng kênh.",
            "- Độ lặp lại cao của cặp cà phê không đủ bù cho độ lặp lại thấp của Tài thuần và số phiên quá ít.",
            "",
            "## 11. Trả lời câu hỏi nghiên cứu",
            "",
            "### Tín hiệu có phát hiện được cà phê riêng không?",
            "",
            "**Có dấu hiệu rõ.** Cà phê riêng thường làm BME688 giảm và MQ3-1 tăng, hai lần lặp cùng mức có hướng fingerprint tương đối giống nhau. Tuy nhiên, hai phiên cà phê nhiều có baseline không ổn định nên chưa thể dùng làm bằng chứng định lượng mạnh.",
            "",
            "### Có phân biệt được người có cà phê và không có cà phê không?",
            "",
            "**Chưa đủ để kết luận.** Trung bình hai nhóm khác nhau trên BME688 và MQ3-1, nhưng phân bố vẫn chồng lấn. Dữ liệu chỉ có một ngày và nhóm dương chỉ có Tài.",
            "",
            "### Có thể huấn luyện mô hình ngay không?",
            "",
            "Có thể chạy Logistic Regression hoặc SVM tuyến tính như một kiểm tra kỹ thuật, nhưng kết quả không đại diện hiệu năng thực tế. Không nên dùng Random Forest/UMAP hoặc ROC-AUC làm bằng chứng chính với 9 phiên Tài nhị phân và chưa có test khác ngày.",
            "",
            "## 12. Hạn chế của kết quả",
            "",
            "1. Nhóm có cà phê chỉ có Tài; chưa đánh giá được cà phê trên người khác.",
            "2. Minh và Quy chỉ có phiên âm tính, tạo nguy cơ subject leakage nếu gộp vào mô hình nhị phân.",
            "3. Dữ liệu chỉ có một ngày và hai khối môi trường khác nhau.",
            "4. Hai phiên cà phê nhiều có baseline không ổn định.",
            "5. Đổi đầu ống và purge thủ công làm thời gian chờ không đồng nhất.",
            "6. Hai cặp cảm biến cùng loại có tương quan rất thấp.",
            "7. Số phiên ít hơn nhiều so với số đặc trưng ứng viên, nên feature selection và mô hình phức tạp dễ overfit.",
            "",
            "## 13. Thiết kế thu thập tiếp theo",
            "",
            "Mỗi người cần được đo paired ở cả hai trạng thái:",
            "",
            "| Người | Không cà phê | Có cà phê ít | Có cà phê nhiều |",
            "|---|:---:|:---:|:---:|",
            "| Tài | Có | Có | Có |",
            "| Minh | Có | Có | Có |",
            "| Quy | Có | Có | Có |",
            "| Người mới | Có | Có | Có |",
            "",
            "Nên thu tối thiểu 10–15 phiên thật mỗi trạng thái/người trên nhiều ngày, cố định vị trí cơ thể, lượng cà phê, thời gian sau tiếp xúc, khoảng cách đầu hút, lưu lượng khí và quy trình purge. Đánh giá cuối cùng phải tách theo ngày và theo người.",
            "",
            "## 14. Biểu đồ chi tiết từng phiên",
            "",
            "Các biểu đồ dưới đây được thu gọn để README chính dễ đọc.",
            "",
        ]
    )
    for run in runs:
        folder = run["folder"]
        lines.extend(
            [
                "<details>",
                f"<summary><strong>{markdown_escape(run['label'])}</strong> — {run['started_at'].strftime('%H:%M:%S')} — {'Đạt QC' if run['accepted'] else 'Cần xem lại'}</summary>",
                "",
                f"![Tín hiệu gốc {markdown_escape(run['label'])}](./{folder}/signals.png)",
                "",
                f"![Tín hiệu chuẩn hóa {markdown_escape(run['label'])}](./{folder}/normalized.png)",
                "",
                "</details>",
                "",
            ]
        )
    lines.extend(
        [
            "## 15. File tái lập phân tích",
            "",
            "Báo cáo và toàn bộ SVG tổng hợp được sinh bởi:",
            "",
            "- `analysis/generate_2026_10_28_report.py`",
            "",
            "Chạy lại từ thư mục gốc repository:",
            "",
            "```powershell",
            "python analysis/generate_2026_10_28_report.py",
            "```",
            "",
            "Các đầu ra chính:",
            "",
            "- `data/2026-10-28/README_PHAN_TICH.md`",
            "- `data/2026-10-28/report_assets/*.svg`",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    directories = sorted(
        path
        for path in DATA_ROOT.iterdir()
        if path.is_dir() and (path / "raw.csv").exists()
    )
    runs = [load_run(directory) for directory in directories]
    ASSET_ROOT.mkdir(parents=True, exist_ok=True)
    generate_figures(sorted(runs, key=lambda run: run["started_at"]))
    OUTPUT.write_text(generate_report(runs), encoding="utf-8")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
