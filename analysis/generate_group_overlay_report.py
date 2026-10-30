from __future__ import annotations

import csv
import html
import math
import statistics
from bisect import bisect_left
from collections import OrderedDict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "2026-10-28"
MANIFEST_PATH = DATA_DIR / "label_manifest.csv"
OUTPUT_DIR = DATA_DIR / "group_overlays"
REPORT_PATH = DATA_DIR / "GROUP_OVERLAY_REPORT.md"
SUMMARY_PATH = DATA_DIR / "group_overlay_summary.csv"

PHASES = OrderedDict(
    (
        ("BASELINE", 60),
        ("EXPOSURE", 120),
        ("RECOVERY", 60),
    )
)
PHASE_OFFSETS = {"BASELINE": 0, "EXPOSURE": 60, "RECOVERY": 180}
PHASE_COLORS = {
    "BASELINE": "#eef5ff",
    "EXPOSURE": "#fff3df",
    "RECOVERY": "#edf9ef",
}
PHASE_LABELS = {
    "BASELINE": "Baseline · 60 s",
    "EXPOSURE": "Exposure · 120 s",
    "RECOVERY": "Recovery · 60 s",
}

SENSORS = OrderedDict(
    (
        (
            "gas_resistance_ohm",
            {"label": "BME688 gas", "unit": "Ω", "prefix": "bme"},
        ),
        (
            "mq135_1_voltage_v",
            {"label": "MQ135-1", "unit": "V", "prefix": "mq135_1"},
        ),
        (
            "mq3_1_voltage_v",
            {"label": "MQ3-1", "unit": "V", "prefix": "mq3_1"},
        ),
        (
            "mq135_2_voltage_v",
            {"label": "MQ135-2", "unit": "V", "prefix": "mq135_2"},
        ),
        (
            "mq3_2_voltage_v",
            {"label": "MQ3-2", "unit": "V", "prefix": "mq3_2"},
        ),
    )
)

GROUPS = OrderedDict(
    (
        (
            "A_human_only",
            {
                "manifest_group": "HUMAN_ONLY",
                "title": "Nhóm A – Human Only",
                "purpose": "Xác định tín hiệu nền của người",
            },
        ),
        (
            "B_human_coffee",
            {
                "manifest_group": "HUMAN_COFFEE",
                "title": "Nhóm B – Human + Coffee",
                "purpose": "Kiểm tra chiều đáp ứng và độ lặp lại khi Tài mang cà phê",
            },
        ),
        (
            "C_coffee_only",
            {
                "manifest_group": "COFFEE_ONLY",
                "title": "Nhóm C – Coffee Only",
                "purpose": "Khảo sát fingerprint của cà phê riêng",
            },
        ),
        (
            "D_air",
            {
                "manifest_group": "AIR",
                "title": "Nhóm D – Air",
                "purpose": "Kiểm tra tín hiệu nền và carry-over",
            },
        ),
    )
)

LINE_COLORS = (
    "#1f77b4",
    "#d62728",
    "#2ca02c",
    "#9467bd",
    "#ff7f0e",
    "#17becf",
    "#8c564b",
)


def parse_bool(value: str | None) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def parse_float(value: str | None) -> float | None:
    try:
        result = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def valid_sensor_row(row: dict[str, str], sensor: str) -> bool:
    config = SENSORS[sensor]
    prefix = str(config["prefix"])
    if prefix == "bme":
        return (
            row.get("bme_status") == "OK"
            and parse_bool(row.get("bme_fresh"))
            and parse_bool(row.get("gas_valid"))
            and parse_bool(row.get("heater_stable"))
            and parse_bool(row.get("new_data"))
        )
    return (
        row.get(f"{prefix}_status") == "OK"
        and parse_bool(row.get(f"{prefix}_fresh"))
        and row.get(f"{prefix}_quality", "") in {"", "OK"}
    )


def load_manifest() -> list[dict[str, str]]:
    with MANIFEST_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_run(manifest_row: dict[str, str]) -> dict[str, object]:
    phase_data = {
        sensor: {phase: [] for phase in PHASES}
        for sensor in SENSORS
    }
    raw_path = DATA_DIR / manifest_row["folder"] / "raw.csv"
    with raw_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            phase = row.get("phase", "")
            if phase not in PHASES:
                continue
            phase_time = parse_float(row.get("phase_elapsed_s"))
            if phase_time is None:
                continue
            for sensor in SENSORS:
                if not valid_sensor_row(row, sensor):
                    continue
                value = parse_float(row.get(sensor))
                if value is not None:
                    phase_data[sensor][phase].append((phase_time, value))

    baselines: dict[str, float] = {}
    normalized = {
        sensor: {phase: [] for phase in PHASES}
        for sensor in SENSORS
    }
    for sensor in SENSORS:
        baseline_values = [value for _, value in phase_data[sensor]["BASELINE"]]
        if not baseline_values:
            continue
        baseline = statistics.median(baseline_values)
        baselines[sensor] = baseline
        if abs(baseline) <= 1e-12:
            continue
        for phase in PHASES:
            normalized[sensor][phase] = [
                (time_value, 100.0 * (value - baseline) / abs(baseline))
                for time_value, value in phase_data[sensor][phase]
            ]

    display_name = (
        f"{manifest_row['started_at'][11:19]} · {manifest_row['original_name']}"
    )
    return {
        "manifest": manifest_row,
        "display_name": display_name,
        "raw": phase_data,
        "normalized": normalized,
        "baselines": baselines,
    }


def svg_text(
    x: float,
    y: float,
    value: object,
    size: int = 13,
    anchor: str = "start",
    weight: str = "normal",
    color: str = "#253047",
) -> str:
    escaped = html.escape(str(value))
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-family="Arial, sans-serif" '
        f'font-size="{size}" text-anchor="{anchor}" font-weight="{weight}" '
        f'fill="{color}">{escaped}</text>'
    )


def svg_rotated_text(
    x: float,
    y: float,
    value: object,
    size: int = 13,
    weight: str = "normal",
    color: str = "#253047",
) -> str:
    escaped = html.escape(str(value))
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-family="Arial, sans-serif" '
        f'font-size="{size}" text-anchor="middle" font-weight="{weight}" '
        f'fill="{color}" transform="rotate(-90 {x:.1f} {y:.1f})">'
        f"{escaped}</text>"
    )


def svg_polyline(
    points: list[tuple[float, float]],
    color: str,
    width: float = 1.5,
    opacity: float = 0.82,
) -> str:
    encoded = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
    return (
        f'<polyline points="{encoded}" fill="none" stroke="{color}" '
        f'stroke-width="{width}" stroke-opacity="{opacity}" '
        'stroke-linejoin="round" stroke-linecap="round"/>'
    )


def finite_range(values: list[float], include_zero: bool = False) -> tuple[float, float]:
    usable = [value for value in values if math.isfinite(value)]
    if include_zero:
        usable.append(0.0)
    if not usable:
        return -1.0, 1.0
    minimum = min(usable)
    maximum = max(usable)
    if math.isclose(minimum, maximum):
        padding = max(abs(minimum) * 0.05, 1.0)
    else:
        padding = (maximum - minimum) * 0.08
    return minimum - padding, maximum + padding


def format_tick(value: float, sensor: str, normalized: bool) -> str:
    if normalized:
        return f"{value:.1f}%"
    if sensor == "gas_resistance_ohm":
        return f"{value / 1000:.1f}k"
    return f"{value:.3f}"


def map_x(total_time: float, left: float, plot_width: float) -> float:
    return left + total_time / 240.0 * plot_width


def chart_base(
    title: str,
    subtitle: str,
    runs: list[dict[str, object]],
) -> tuple[int, int, float, float, float, float, list[str]]:
    width = 1600
    height = 1430
    left = 120.0
    right = 45.0
    top = 180.0
    panel_height = 220.0
    plot_width = width - left - right
    elements = [
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        svg_text(width / 2, 38, title, 24, "middle", "bold"),
        svg_text(width / 2, 66, subtitle, 14, "middle", "normal", "#526078"),
    ]

    legend_y = 98.0
    columns = 4
    column_width = 360.0
    for index, run in enumerate(runs):
        row_index = index // columns
        column_index = index % columns
        x = left + column_index * column_width
        y = legend_y + row_index * 25
        color = LINE_COLORS[index % len(LINE_COLORS)]
        elements.append(
            f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{x + 25:.1f}" y2="{y:.1f}" '
            f'stroke="{color}" stroke-width="3"/>'
        )
        elements.append(svg_text(x + 32, y + 5, run["display_name"], 12))
    return width, height, left, top, plot_width, panel_height, elements


def add_panel_background(
    elements: list[str],
    left: float,
    panel_top: float,
    plot_width: float,
    panel_height: float,
) -> None:
    for phase, duration in PHASES.items():
        x_start = map_x(PHASE_OFFSETS[phase], left, plot_width)
        x_end = map_x(PHASE_OFFSETS[phase] + duration, left, plot_width)
        elements.append(
            f'<rect x="{x_start:.1f}" y="{panel_top:.1f}" '
            f'width="{x_end - x_start:.1f}" height="{panel_height:.1f}" '
            f'fill="{PHASE_COLORS[phase]}"/>'
        )
        elements.append(
            svg_text(
                (x_start + x_end) / 2,
                panel_top + 17,
                PHASE_LABELS[phase],
                11,
                "middle",
                "bold",
                "#526078",
            )
        )
    for boundary in (60, 180):
        x = map_x(boundary, left, plot_width)
        elements.append(
            f'<line x1="{x:.1f}" y1="{panel_top:.1f}" x2="{x:.1f}" '
            f'y2="{panel_top + panel_height:.1f}" stroke="#6b7280" '
            'stroke-width="1.2" stroke-dasharray="6,4"/>'
        )


def add_axes(
    elements: list[str],
    sensor: str,
    normalized: bool,
    left: float,
    panel_top: float,
    plot_width: float,
    panel_height: float,
    y_min: float,
    y_max: float,
) -> None:
    for tick_index in range(5):
        fraction = tick_index / 4
        y = panel_top + panel_height - fraction * panel_height
        value = y_min + fraction * (y_max - y_min)
        elements.append(
            f'<line x1="{left:.1f}" y1="{y:.1f}" x2="{left + plot_width:.1f}" '
            f'y2="{y:.1f}" stroke="#d8dee9" stroke-width="0.8"/>'
        )
        elements.append(
            svg_text(left - 10, y + 4, format_tick(value, sensor, normalized), 11, "end")
        )
    if normalized and y_min <= 0 <= y_max:
        zero_y = panel_top + panel_height - (0 - y_min) / (y_max - y_min) * panel_height
        elements.append(
            f'<line x1="{left:.1f}" y1="{zero_y:.1f}" x2="{left + plot_width:.1f}" '
            f'y2="{zero_y:.1f}" stroke="#334155" stroke-width="1.1"/>'
        )
    elements.append(
        f'<rect x="{left:.1f}" y="{panel_top:.1f}" width="{plot_width:.1f}" '
        f'height="{panel_height:.1f}" fill="none" stroke="#7b879c" stroke-width="1"/>'
    )
    config = SENSORS[sensor]
    unit = "% so với median baseline" if normalized else config["unit"]
    elements.append(
        svg_rotated_text(
            22,
            panel_top + panel_height / 2,
            f"{config['label']} · {unit}",
            13,
            "bold",
        )
    )


def y_mapper(
    value: float,
    y_min: float,
    y_max: float,
    panel_top: float,
    panel_height: float,
) -> float:
    return panel_top + panel_height - (value - y_min) / (y_max - y_min) * panel_height


def write_overlay_chart(
    group_key: str,
    group: dict[str, str],
    runs: list[dict[str, object]],
    normalized: bool,
) -> Path:
    data_key = "normalized" if normalized else "raw"
    mode_title = "Tín hiệu chuẩn hóa" if normalized else "Tín hiệu gốc"
    subtitle = (
        "R(t) = 100 × (X(t) − median BASELINE) / |median BASELINE|"
        if normalized
        else "Chỉ giữ mẫu hợp lệ; các pha WAIT và MONITOR không được vẽ"
    )
    width, height, left, top, plot_width, panel_height, elements = chart_base(
        f"{group['title']} · {mode_title}", subtitle, runs
    )

    for sensor_index, sensor in enumerate(SENSORS):
        panel_top = top + sensor_index * 245
        values = [
            value
            for run in runs
            for phase in PHASES
            for _, value in run[data_key][sensor][phase]
        ]
        y_min, y_max = finite_range(values, include_zero=normalized)
        add_panel_background(elements, left, panel_top, plot_width, panel_height)
        add_axes(
            elements,
            sensor,
            normalized,
            left,
            panel_top,
            plot_width,
            panel_height,
            y_min,
            y_max,
        )
        for run_index, run in enumerate(runs):
            color = LINE_COLORS[run_index % len(LINE_COLORS)]
            for phase in PHASES:
                points = [
                    (
                        map_x(PHASE_OFFSETS[phase] + time_value, left, plot_width),
                        y_mapper(value, y_min, y_max, panel_top, panel_height),
                    )
                    for time_value, value in run[data_key][sensor][phase]
                    if 0 <= time_value <= PHASES[phase] + 1
                ]
                if len(points) >= 2:
                    elements.append(svg_polyline(points, color))

    elements.append(
        svg_text(
            left + plot_width / 2,
            height - 20,
            "Trục ngang ghép theo pha: Baseline 0–60 s · Exposure 0–120 s · Recovery 0–60 s",
            13,
            "middle",
        )
    )
    suffix = "normalized" if normalized else "raw"
    output_path = OUTPUT_DIR / f"{group_key}_{suffix}.svg"
    write_svg(output_path, width, height, elements)
    return output_path


def interpolate(points: list[tuple[float, float]], target: float) -> float | None:
    if not points:
        return None
    times = [item[0] for item in points]
    index = bisect_left(times, target)
    if index == 0:
        return points[0][1] if abs(points[0][0] - target) <= 1.5 else None
    if index == len(points):
        return points[-1][1] if abs(points[-1][0] - target) <= 1.5 else None
    left_time, left_value = points[index - 1]
    right_time, right_value = points[index]
    if right_time - left_time > 3.0:
        return None
    if math.isclose(right_time, left_time):
        return left_value
    fraction = (target - left_time) / (right_time - left_time)
    return left_value + fraction * (right_value - left_value)


def normalized_grid(run: dict[str, object], sensor: str) -> list[float | None]:
    output: list[float | None] = []
    for phase, duration in PHASES.items():
        points = run["normalized"][sensor][phase]
        output.extend(interpolate(points, float(second)) for second in range(duration))
    return output


def mean_sd_grid(
    runs: list[dict[str, object]], sensor: str
) -> tuple[list[float | None], list[float | None], list[int]]:
    grids = [normalized_grid(run, sensor) for run in runs]
    means: list[float | None] = []
    deviations: list[float | None] = []
    counts: list[int] = []
    for index in range(240):
        values = [grid[index] for grid in grids if grid[index] is not None]
        counts.append(len(values))
        if not values:
            means.append(None)
            deviations.append(None)
            continue
        means.append(statistics.fmean(values))
        deviations.append(statistics.pstdev(values) if len(values) >= 2 else 0.0)
    return means, deviations, counts


def write_mean_sd_chart(
    group_key: str,
    group: dict[str, str],
    runs: list[dict[str, object]],
) -> Path:
    width, height, left, top, plot_width, panel_height, elements = chart_base(
        f"{group['title']} · Trung bình ± SD",
        "Trung bình và độ lệch chuẩn theo từng giây sau khi chuẩn hóa theo median baseline của mỗi phiên",
        [],
    )
    elements.append(svg_text(left, 105, f"n = {len(runs)} phiên", 12, "start", "bold"))
    elements.append(
        '<rect x="270" y="94" width="25" height="12" fill="#4c78a8" fill-opacity="0.22"/>'
    )
    elements.append(svg_text(302, 105, "±1 SD", 12))
    elements.append(
        '<line x1="375" y1="100" x2="405" y2="100" stroke="#174a7e" stroke-width="3"/>'
    )
    elements.append(svg_text(412, 105, "Trung bình", 12))
    for sensor_index, sensor in enumerate(SENSORS):
        panel_top = top + sensor_index * 245
        means, deviations, _ = mean_sd_grid(runs, sensor)
        bounds = [
            value + sign * deviation
            for value, deviation in zip(means, deviations)
            if value is not None and deviation is not None
            for sign in (-1, 1)
        ]
        y_min, y_max = finite_range(bounds, include_zero=True)
        add_panel_background(elements, left, panel_top, plot_width, panel_height)
        add_axes(
            elements,
            sensor,
            True,
            left,
            panel_top,
            plot_width,
            panel_height,
            y_min,
            y_max,
        )
        upper = [
            (
                index,
                map_x(float(index), left, plot_width),
                y_mapper(value + deviation, y_min, y_max, panel_top, panel_height),
            )
            for index, (value, deviation) in enumerate(zip(means, deviations))
            if value is not None and deviation is not None
        ]
        lower = [
            (
                index,
                map_x(float(index), left, plot_width),
                y_mapper(value - deviation, y_min, y_max, panel_top, panel_height),
            )
            for index, (value, deviation) in enumerate(zip(means, deviations))
            if value is not None and deviation is not None
        ]
        phase_slices = ((0, 60), (60, 180), (180, 240))
        for start_index, end_index in phase_slices:
            phase_upper = [
                (x, y)
                for index, x, y in upper
                if start_index <= index < end_index
            ]
            phase_lower = [
                (x, y)
                for index, x, y in lower
                if start_index <= index < end_index
            ]
            if phase_upper and phase_lower:
                polygon = " ".join(
                    f"{x:.2f},{y:.2f}"
                    for x, y in phase_upper + list(reversed(phase_lower))
                )
                elements.append(
                    f'<polygon points="{polygon}" fill="#4c78a8" fill-opacity="0.22" stroke="none"/>'
                )
            mean_points = [
                (
                    map_x(float(index), left, plot_width),
                    y_mapper(value, y_min, y_max, panel_top, panel_height),
                )
                for index, value in enumerate(means)
                if start_index <= index < end_index and value is not None
            ]
            if len(mean_points) >= 2:
                elements.append(svg_polyline(mean_points, "#174a7e", 2.6, 1.0))

    elements.append(
        svg_text(
            left + plot_width / 2,
            height - 20,
            "Vùng màu là ±1 SD giữa các phiên; nhóm Air có n=1 nên SD bằng 0",
            13,
            "middle",
        )
    )
    output_path = OUTPUT_DIR / f"{group_key}_mean_sd.svg"
    write_svg(output_path, width, height, elements)
    return output_path


def write_svg(path: Path, width: int, height: int, elements: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    document = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">\n'
        + "\n".join(elements)
        + "\n</svg>\n"
    )
    path.write_text(document, encoding="utf-8")


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
    return numerator / denominator if denominator > 1e-12 else None


def exposure_curve(run: dict[str, object], sensor: str) -> list[float | None]:
    points = run["normalized"][sensor]["EXPOSURE"]
    return [interpolate(points, float(second)) for second in range(120)]


def pairwise_curve_correlations(
    runs: list[dict[str, object]], sensor: str
) -> list[float]:
    curves = [exposure_curve(run, sensor) for run in runs]
    correlations: list[float] = []
    for left_index in range(len(curves)):
        for right_index in range(left_index + 1, len(curves)):
            paired = [
                (left_value, right_value)
                for left_value, right_value in zip(
                    curves[left_index], curves[right_index]
                )
                if left_value is not None and right_value is not None
            ]
            if len(paired) < 30:
                continue
            correlation = pearson(
                [item[0] for item in paired], [item[1] for item in paired]
            )
            if correlation is not None:
                correlations.append(correlation)
    return correlations


def evaluate_response(
    median_response: float,
    agreement: float,
    median_correlation: float | None,
) -> str:
    magnitude = abs(median_response)
    if magnitude >= 2.0 and agreement >= 0.75:
        amplitude = "rõ"
    elif magnitude >= 0.5 and agreement >= 0.75:
        amplitude = "vừa"
    elif agreement < 0.75:
        amplitude = "không cùng chiều"
    else:
        amplitude = "yếu"
    if median_correlation is None:
        shape = "chưa đo lặp"
    elif median_correlation >= 0.7:
        shape = "hình dạng giống"
    elif median_correlation >= 0.3:
        shape = "hình dạng giống một phần"
    else:
        shape = "hình dạng kém ổn định"
    return f"{amplitude}; {shape}"


def summarize_group(
    group_key: str,
    group: dict[str, str],
    runs: list[dict[str, object]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for sensor, config in SENSORS.items():
        responses: list[float] = []
        for run in runs:
            exposure_values = [
                value for _, value in run["normalized"][sensor]["EXPOSURE"]
            ]
            if exposure_values:
                responses.append(statistics.fmean(exposure_values))
        median_response = statistics.median(responses) if responses else math.nan
        if not responses or math.isclose(median_response, 0.0, abs_tol=0.05):
            direction = "gần 0"
            agreement = (
                sum(abs(value) <= 0.05 for value in responses) / len(responses)
                if responses
                else math.nan
            )
        elif median_response > 0:
            direction = "tăng"
            agreement = sum(value > 0 for value in responses) / len(responses)
        else:
            direction = "giảm"
            agreement = sum(value < 0 for value in responses) / len(responses)
        correlations = pairwise_curve_correlations(runs, sensor)
        median_correlation = (
            statistics.median(correlations) if correlations else None
        )
        rows.append(
            {
                "group_key": group_key,
                "group": group["manifest_group"],
                "group_title": group["title"],
                "n_runs": len(runs),
                "sensor": sensor,
                "sensor_label": config["label"],
                "median_exposure_response_pct": median_response,
                "minimum_run_response_pct": min(responses) if responses else math.nan,
                "maximum_run_response_pct": max(responses) if responses else math.nan,
                "direction": direction,
                "direction_agreement": agreement,
                "median_exposure_curve_correlation": median_correlation,
                "pair_count": len(correlations),
                "assessment": evaluate_response(
                    median_response, agreement, median_correlation
                ),
            }
        )
    return rows


def format_number(value: object, digits: int = 2) -> str:
    if value is None:
        return "NA"
    numeric = float(value)
    return "NA" if not math.isfinite(numeric) else f"{numeric:.{digits}f}"


def write_summary(rows: list[dict[str, object]]) -> None:
    fieldnames = list(rows[0])
    with SUMMARY_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def report_group_section(
    group_key: str,
    group: dict[str, str],
    runs: list[dict[str, object]],
    summary_rows: list[dict[str, object]],
) -> list[str]:
    file_prefix = f"./group_overlays/{group_key}"
    lines = [
        f"## {group['title']}",
        "",
        f"**Số phiên:** {len(runs)}. **Mục tiêu:** {group['purpose']}.",
        "",
        "### Tín hiệu gốc",
        "",
        f"![{group['title']} – tín hiệu gốc]({file_prefix}_raw.svg)",
        "",
        "### Tín hiệu chuẩn hóa",
        "",
        f"![{group['title']} – tín hiệu chuẩn hóa]({file_prefix}_normalized.svg)",
        "",
        "### Trung bình và độ phân tán",
        "",
        f"![{group['title']} – trung bình và SD]({file_prefix}_mean_sd.svg)",
        "",
        "### Đánh giá định lượng",
        "",
        "| Cảm biến | Median EXPOSURE | Khoảng giữa phiên | Cùng chiều | Median r hình dạng | Nhận xét |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for row in summary_rows:
        response_range = (
            f"{format_number(row['minimum_run_response_pct'])}% → "
            f"{format_number(row['maximum_run_response_pct'])}%"
        )
        lines.append(
            f"| {row['sensor_label']} | {format_number(row['median_exposure_response_pct'])}% "
            f"({row['direction']}) | {response_range} | "
            f"{format_number(100 * float(row['direction_agreement']), 0)}% | "
            f"{format_number(row['median_exposure_curve_correlation'])} | "
            f"{row['assessment']} |"
        )
    lines.append("")
    if group_key == "D_air":
        lines.append(
            "Nhóm Air chỉ có một phiên nên không thể đánh giá độ lặp lại hoặc độ phân tán giữa các lần đo."
        )
        lines.append("")
    return lines


def write_report(
    grouped_runs: dict[str, list[dict[str, object]]],
    summaries: list[dict[str, object]],
) -> None:
    lines = [
        "# Đồ thị chồng tín hiệu theo 4 nhóm",
        "",
        "Báo cáo này thực hiện **Bước 1 – kiểm tra lại đồ thị tín hiệu**. Chưa dùng các feature nâng cao và không huấn luyện mô hình.",
        "",
        "## Phương pháp",
        "",
        "- Nhóm được lấy từ `label_manifest.csv`; phiên paired không nằm trong bốn nhóm này và sẽ được xử lý riêng ở Bước 2.",
        "- Chỉ sử dụng ba pha `BASELINE`, `EXPOSURE`, `RECOVERY`; bỏ `MONITOR` và `WAIT_*`.",
        "- Chỉ giữ dòng cảm biến hợp lệ theo cờ status/fresh/quality; BME688 còn yêu cầu `gas_valid`, `heater_stable` và `new_data`.",
        "- Chuẩn hóa từng cảm biến, từng phiên bằng `R(t) = 100 × (X(t) − B0) / |B0|`, với `B0` là median của BASELINE gốc.",
        "- Trung bình và SD được tính theo từng giây sau khi nội suy riêng từng pha; không nối dữ liệu qua khoảng chờ.",
        "- `Median r hình dạng` là median tương quan Pearson từng cặp đường cong EXPOSURE. Đây là chỉ số thăm dò, không phải kiểm định xác nhận.",
        "",
        "Ngưỡng diễn giải `rõ/vừa/yếu` chỉ là quy ước mô tả: biên độ median lần lượt ≥2%, ≥0,5% hoặc thấp hơn, đồng thời yêu cầu tối thiểu 75% phiên cùng chiều.",
        "",
        "**Cảnh báo khi đọc biểu đồ:** các giá trị đã qua cờ QC vẫn có thể chứa spike đơn lẻ. Script cố ý không làm mượt hoặc cắt ngọn để người đọc nhìn thấy chúng. Một spike không được xem là phản ứng mùi nếu không kéo dài và không lặp lại ở các phiên khác; vùng ±SD cũng sẽ phình lớn tại những thời điểm này.",
        "",
    ]
    for group_key, group in GROUPS.items():
        group_summary = [row for row in summaries if row["group_key"] == group_key]
        lines.extend(
            report_group_section(
                group_key, group, grouped_runs[group_key], group_summary
            )
        )

    human_coffee_rows = [
        row for row in summaries if row["group_key"] == "B_human_coffee"
    ]
    clear_sensors = [
        row["sensor_label"]
        for row in human_coffee_rows
        if abs(float(row["median_exposure_response_pct"])) >= 2.0
        and float(row["direction_agreement"]) >= 0.75
    ]
    consistent_shape = [
        row["sensor_label"]
        for row in human_coffee_rows
        if row["median_exposure_curve_correlation"] is not None
        and float(row["median_exposure_curve_correlation"]) >= 0.7
    ]
    lines.extend(
        [
            "## Trả lời câu hỏi chính",
            "",
            "### Cảm biến nào phản ứng rõ trong nhóm Human + Coffee?",
            "",
            (
                "Theo quy ước mô tả ở trên: **" + ", ".join(clear_sensors) + "**."
                if clear_sensors
                else "Không có cảm biến nào đồng thời đạt ngưỡng biên độ ≥2% và có ít nhất 75% phiên cùng chiều."
            ),
            "Kết quả này chỉ nói về biên độ trung vị và chiều đáp ứng. Với BME688, đồ thị vẫn có spike rất sâu ở một phiên và median tương quan hình dạng thấp, nên chưa thể gọi là fingerprint ổn định.",
            "",
            "### Phản ứng có cùng chiều không?",
            "",
            "Xem cột `Cùng chiều` của Nhóm B. Một cảm biến chỉ được xem là nhất quán sơ bộ khi đạt ít nhất 75%; tỷ lệ thấp hơn cho thấy dấu đáp ứng đổi giữa các phiên.",
            "",
            "### Hình dạng có tương tự giữa các lần đo không?",
            "",
            (
                "Các cảm biến có median tương quan đường cong ≥0,70: **"
                + ", ".join(consistent_shape)
                + "**."
                if consistent_shape
                else "Không cảm biến nào đạt median tương quan đường cong EXPOSURE ≥0,70."
            ),
            "",
            "Độ giống hình dạng không đồng nghĩa với khả năng phân biệt cà phê: đường cong có thể lặp lại nhưng vẫn giống Human Only hoặc Air. Cần so sánh chéo nhóm ở các bước tiếp theo.",
            "",
            "## File đầu ra",
            "",
            "- Dữ liệu định lượng: [`group_overlay_summary.csv`](./group_overlay_summary.csv).",
            "- Bộ 12 SVG: thư mục [`group_overlays`](./group_overlays/).",
            "- Script tái lập: [`../../analysis/generate_group_overlay_report.py`](../../analysis/generate_group_overlay_report.py).",
            "",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    manifest = load_manifest()
    runs = [load_run(row) for row in manifest if row["experiment_group"] != "PAIRED"]
    grouped_runs: dict[str, list[dict[str, object]]] = {}
    summaries: list[dict[str, object]] = []

    for group_key, group in GROUPS.items():
        group_runs = [
            run
            for run in runs
            if run["manifest"]["experiment_group"] == group["manifest_group"]
        ]
        grouped_runs[group_key] = group_runs
        write_overlay_chart(group_key, group, group_runs, normalized=False)
        write_overlay_chart(group_key, group, group_runs, normalized=True)
        write_mean_sd_chart(group_key, group, group_runs)
        summaries.extend(summarize_group(group_key, group, group_runs))

    write_summary(summaries)
    write_report(grouped_runs, summaries)
    print(f"Wrote {REPORT_PATH}")
    print(f"Wrote {SUMMARY_PATH}")
    print(f"Wrote 12 SVG files to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
