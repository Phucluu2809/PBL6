"""Generate detailed SVG analysis for the 2026-10-28 coffee dataset."""

from __future__ import annotations

import csv
from html import escape
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data" / "2026-10-28"
OUTPUT_ROOT = DATA_ROOT / "coffee_visual_analysis"
BATCH_JSON = DATA_ROOT / "coffee_odor_batch_test" / "coffee_odor_batch_results.json"


def ensure_dependencies() -> None:
    try:
        import sklearn  # noqa: F401
        return
    except ModuleNotFoundError:
        pass
    candidate = ROOT / ".venv" / "Scripts" / "python.exe"
    if candidate.is_file() and candidate.resolve() != Path(sys.executable).resolve():
        completed = subprocess.run(
            [str(candidate), str(Path(__file__).resolve()), *sys.argv[1:]],
            check=False,
        )
        raise SystemExit(completed.returncode)
    raise ModuleNotFoundError("Thiếu scikit-learn và không tìm thấy .venv")


ensure_dependencies()

import check_coffee_odor as detector


SENSORS = tuple(detector.SENSORS)
SENSOR_LABELS = {
    "bme": "BME688 gas",
    "mq135_1": "MQ135-1",
    "mq3_1": "MQ3-1",
    "mq135_2": "MQ135-2",
    "mq3_2": "MQ3-2",
}
FEATURE_SHORT = {
    "exposure_mean": "mean",
    "exposure_middle_mean": "mid",
    "q10": "Q10",
    "q90": "Q90",
    "slope_pct_per_min": "slope",
}
BLUE = "#2878b5"
RED = "#d1495b"
ORANGE = "#e58e26"
GREEN = "#2a9d6f"
GRAY = "#6b7280"
GRID = "#d9dee7"


def svg_text(
    x: float,
    y: float,
    value: object,
    size: int = 13,
    anchor: str = "start",
    weight: str = "normal",
    color: str = "#1f2937",
    rotate: float | None = None,
) -> str:
    transform = f' transform="rotate({rotate:.1f} {x:.1f} {y:.1f})"' if rotate else ""
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" text-anchor="{anchor}" '
        f'font-weight="{weight}" fill="{color}" font-family="DejaVu Sans, Arial, sans-serif"'
        f'{transform}>{escape(str(value))}</text>'
    )


def write_svg(name: str, width: int, height: int, elements: list[str]) -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    document = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        *elements,
        "</svg>",
    ]
    (OUTPUT_ROOT / name).write_text("\n".join(document), encoding="utf-8")


def linear_map(value: float, low: float, high: float, start: float, end: float) -> float:
    if high == low:
        return (start + end) / 2
    return start + (value - low) / (high - low) * (end - start)


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def polyline(points: list[tuple[float, float]], color: str, width: float = 2.2) -> str:
    coordinates = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    return (
        f'<polyline points="{coordinates}" fill="none" stroke="{color}" '
        f'stroke-width="{width}" stroke-linejoin="round" stroke-linecap="round"/>'
    )


def polygon(points: list[tuple[float, float]], color: str, opacity: float = 0.14) -> str:
    coordinates = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    return f'<polygon points="{coordinates}" fill="{color}" fill-opacity="{opacity}" stroke="none"/>'


def load_inputs() -> tuple[list[dict[str, str]], list[dict[str, object]]]:
    with (DATA_ROOT / "label_manifest.csv").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        manifest = list(csv.DictReader(handle))
    batch = json.loads(BATCH_JSON.read_text(encoding="utf-8"))
    return manifest, batch["rows"]


def eligible_sessions(
    manifest: list[dict[str, str]], batch_rows: list[dict[str, object]]
) -> list[dict[str, object]]:
    result_by_folder = {str(row["folder"]): row for row in batch_rows}
    sessions = []
    for row in manifest:
        if row.get("binary_use") != "ELIGIBLE" or row.get("coffee_on_person_label") not in {"0", "1"}:
            continue
        folder = row["folder"]
        extracted = detector.extract_features(DATA_ROOT / folder / "raw.csv")
        sessions.append(
            {
                "session_no": int(row["session_no"]),
                "folder": folder,
                "label": int(row["coffee_on_person_label"]),
                "group": row["experiment_group"],
                "started_at": row["started_at"],
                "features": extracted["features"],
                "prediction": result_by_folder[folder]["prediction"],
                "main_score": float(result_by_folder[folder]["decision_score"]),
                "mq_score": float(result_by_folder[folder]["focused_score"]),
            }
        )
    return sessions


def normalized_exposure(folder: str, sensor: str) -> list[tuple[float, float]]:
    rows = detector.read_raw(DATA_ROOT / folder / "raw.csv")
    config = detector.SENSORS[sensor]
    baseline = [
        float(value)
        for row in rows
        if row.get("phase") == "BASELINE"
        and detector.sensor_valid(row, sensor)
        and (value := detector.parse_float(row.get(config["value"]))) is not None
    ]
    reference = statistics.median(baseline)
    points = []
    for row in rows:
        if row.get("phase") != "EXPOSURE" or not detector.sensor_valid(row, sensor):
            continue
        elapsed = detector.parse_float(row.get("phase_elapsed_s"))
        value = detector.parse_float(row.get(config["value"]))
        if elapsed is not None and value is not None:
            points.append((elapsed, 100 * (value - reference) / abs(reference)))
    return sorted(points)


def interpolate(points: list[tuple[float, float]], target: float) -> float:
    if target <= points[0][0]:
        return points[0][1]
    if target >= points[-1][0]:
        return points[-1][1]
    for (left_x, left_y), (right_x, right_y) in zip(points, points[1:]):
        if left_x <= target <= right_x:
            if right_x == left_x:
                return left_y
            fraction = (target - left_x) / (right_x - left_x)
            return left_y + fraction * (right_y - left_y)
    return points[-1][1]


def time_series_matrix(
    sessions: list[dict[str, object]], sensor: str
) -> dict[int, list[list[float]]]:
    grouped: dict[int, list[list[float]]] = {0: [], 1: []}
    for session in sessions:
        points = normalized_exposure(str(session["folder"]), sensor)
        grouped[int(session["label"])].append(
            [interpolate(points, float(second)) for second in range(120)]
        )
    return grouped


def draw_score_map(sessions: list[dict[str, object]]) -> None:
    width, height = 1050, 720
    left, right, top, bottom = 105, 980, 75, 630
    x_low, x_high = -2.0, 1.0
    y_low, y_high = -2.6, 1.5
    mx = lambda value: linear_map(value, x_low, x_high, left, right)
    my = lambda value: linear_map(value, y_low, y_high, bottom, top)
    elements = [svg_text(width / 2, 38, "Bản đồ điểm hai mô hình – 11 mẫu eligible", 23, "middle", "bold")]
    elements.append(
        f'<rect x="{mx(.25):.1f}" y="{top}" width="{right-mx(.25):.1f}" height="{my(.6)-top:.1f}" fill="#e7f6ee"/>'
    )
    elements.append(
        f'<rect x="{left}" y="{my(0):.1f}" width="{mx(0)-left:.1f}" height="{bottom-my(0):.1f}" fill="#edf4fb"/>'
    )
    for value in (-2, -1.5, -1, -.5, 0, .5, 1):
        x = mx(value)
        elements.extend(
            [
                f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{bottom}" stroke="{GRID}"/>',
                svg_text(x, bottom + 24, f"{value:g}", 12, "middle"),
            ]
        )
    for value in (-2.5, -2, -1.5, -1, -.5, 0, .5, 1, 1.5):
        y = my(value)
        elements.extend(
            [
                f'<line x1="{left}" y1="{y:.1f}" x2="{right}" y2="{y:.1f}" stroke="{GRID}"/>',
                svg_text(left - 12, y + 4, f"{value:g}", 12, "end"),
            ]
        )
    elements.extend(
        [
            f'<line x1="{mx(0):.1f}" y1="{top}" x2="{mx(0):.1f}" y2="{bottom}" stroke="#555" stroke-width="1.8"/>',
            f'<line x1="{left}" y1="{my(0):.1f}" x2="{right}" y2="{my(0):.1f}" stroke="#555" stroke-width="1.8"/>',
            f'<line x1="{mx(.25):.1f}" y1="{top}" x2="{mx(.25):.1f}" y2="{bottom}" stroke="{RED}" stroke-dasharray="7 5"/>',
            f'<line x1="{left}" y1="{my(.6):.1f}" x2="{right}" y2="{my(.6):.1f}" stroke="{RED}" stroke-dasharray="7 5"/>',
            svg_text((left + right) / 2, 690, "Main RBF-SVM score", 15, "middle", "bold"),
            svg_text(28, (top + bottom) / 2, "MQ135/MQ3 score", 15, "middle", "bold", rotate=-90),
            svg_text(right - 8, top + 20, "Vùng kết luận CÓ", 13, "end", "bold", GREEN),
            svg_text(left + 8, bottom - 12, "Vùng đồng thuận KHÔNG", 13, "start", "bold", BLUE),
        ]
    )
    for session in sessions:
        x = mx(float(session["main_score"]))
        y = my(float(session["mq_score"]))
        color = RED if session["label"] == 1 else BLUE
        elements.extend(
            [
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="8" fill="{color}" stroke="white" stroke-width="2"/>',
                svg_text(x + 11, y - 9, f"#{session['session_no']}", 12, "start", "bold", color),
            ]
        )
    elements.extend(
        [
            f'<circle cx="{left+20}" cy="{top+22}" r="6" fill="{BLUE}"/>',
            svg_text(left + 34, top + 27, "Nhãn 0 – không cà phê", 12),
            f'<circle cx="{left+190}" cy="{top+22}" r="6" fill="{RED}"/>',
            svg_text(left + 204, top + 27, "Nhãn 1 – có cà phê", 12),
        ]
    )
    write_svg("01_ban_do_score.svg", width, height, elements)


def heat_color(value: float, limit: float = 2.5) -> str:
    normalized = max(-1.0, min(1.0, value / limit))
    target = (41, 120, 181) if normalized < 0 else (213, 70, 76)
    strength = abs(normalized)
    channels = [round(247 + (channel - 247) * strength) for channel in target]
    return "#" + "".join(f"{channel:02x}" for channel in channels)


def draw_feature_heatmap(sessions: list[dict[str, object]]) -> None:
    names = list(detector.FEATURE_NAMES)
    matrix = [[float(session["features"][name]) for name in names] for session in sessions]
    columns = list(zip(*matrix))
    centers = [statistics.fmean(column) for column in columns]
    scales = [statistics.stdev(column) or 1.0 for column in columns]
    z_matrix = [
        [(value - centers[index]) / scales[index] for index, value in enumerate(row)]
        for row in matrix
    ]
    cell_w, cell_h = 38, 37
    left, top = 290, 130
    width = left + len(names) * cell_w + 60
    height = top + len(sessions) * cell_h + 90
    elements = [svg_text(width / 2, 36, "Heatmap z-score của 25 đặc trưng", 23, "middle", "bold")]
    for sensor_index, sensor in enumerate(SENSORS):
        x = left + sensor_index * 5 * cell_w
        elements.extend(
            [
                f'<rect x="{x}" y="58" width="{5*cell_w}" height="25" fill="#eef2f7" stroke="white"/>',
                svg_text(x + 2.5 * cell_w, 76, SENSOR_LABELS[sensor], 13, "middle", "bold"),
            ]
        )
    for index, name in enumerate(names):
        feature = name.split("__", 1)[1]
        x = left + index * cell_w + cell_w / 2
        elements.append(svg_text(x, top - 8, FEATURE_SHORT[feature], 11, "start", rotate=-55))
    for row_index, (session, row) in enumerate(zip(sessions, z_matrix)):
        y = top + row_index * cell_h
        label = f"#{session['session_no']} · {'CÓ CF' if session['label'] else 'KHÔNG CF'}"
        elements.append(
            svg_text(left - 12, y + 24, label, 12, "end", "bold", RED if session["label"] else BLUE)
        )
        for column_index, value in enumerate(row):
            x = left + column_index * cell_w
            elements.append(
                f'<rect x="{x}" y="{y}" width="{cell_w}" height="{cell_h}" fill="{heat_color(value)}" stroke="white"/>'
            )
            if abs(value) >= 1.0:
                elements.append(
                    svg_text(x + cell_w / 2, y + 24, f"{value:+.1f}", 10, "middle", "bold", "white" if abs(value) > 1.55 else "#222")
                )
    legend_y = top + len(sessions) * cell_h + 28
    for index in range(101):
        value = -2.5 + 5 * index / 100
        elements.append(
            f'<rect x="{left + index*4.5:.1f}" y="{legend_y}" width="4.7" height="14" fill="{heat_color(value)}"/>'
        )
    elements.extend(
        [
            svg_text(left, legend_y + 34, "−2,5 SD", 11),
            svg_text(left + 225, legend_y + 34, "median/mean nhóm", 11, "middle"),
            svg_text(left + 450, legend_y + 34, "+2,5 SD", 11, "end"),
        ]
    )
    write_svg("02_heatmap_25_feature.svg", width, height, elements)


def draw_sensor_distributions(sessions: list[dict[str, object]]) -> None:
    width, height = 1580, 520
    elements = [svg_text(width / 2, 38, "Phân bố mean EXPOSURE theo nhãn", 23, "middle", "bold")]
    for panel_index, sensor in enumerate(SENSORS):
        x0 = 75 + panel_index * 300
        top, bottom = 95, 420
        groups = {
            label: [
                float(session["features"][f"{sensor}__exposure_mean"])
                for session in sessions
                if session["label"] == label
            ]
            for label in (0, 1)
        }
        all_values = groups[0] + groups[1]
        padding = max((max(all_values) - min(all_values)) * 0.18, 0.25)
        low, high = min(all_values) - padding, max(all_values) + padding
        my = lambda value: linear_map(value, low, high, bottom, top)
        elements.extend(
            [
                svg_text(x0 + 105, 76, SENSOR_LABELS[sensor], 15, "middle", "bold"),
                f'<line x1="{x0}" y1="{top}" x2="{x0}" y2="{bottom}" stroke="#666"/>',
                f'<line x1="{x0}" y1="{bottom}" x2="{x0+210}" y2="{bottom}" stroke="#666"/>',
                svg_text(x0 - 8, top + 4, f"{high:.1f}", 10, "end"),
                svg_text(x0 - 8, bottom, f"{low:.1f}", 10, "end"),
            ]
        )
        if low <= 0 <= high:
            y_zero = my(0)
            elements.append(
                f'<line x1="{x0}" y1="{y_zero:.1f}" x2="{x0+210}" y2="{y_zero:.1f}" stroke="{GRID}" stroke-dasharray="4 4"/>'
            )
        for group_index, label in enumerate((0, 1)):
            center = x0 + 62 + group_index * 100
            color = BLUE if label == 0 else RED
            offsets = (-24, -16, -8, 0, 8, 16, 24)
            for offset, value in zip(offsets, groups[label]):
                elements.append(
                    f'<circle cx="{center+offset:.1f}" cy="{my(value):.1f}" r="6" fill="{color}" fill-opacity=".78"/>'
                )
            group_mean = statistics.fmean(groups[label])
            elements.extend(
                [
                    f'<line x1="{center-30}" y1="{my(group_mean):.1f}" x2="{center+30}" y2="{my(group_mean):.1f}" stroke="{color}" stroke-width="4"/>',
                    svg_text(center, bottom + 24, "Không" if label == 0 else "Có CF", 11, "middle", "bold", color),
                    svg_text(center, bottom + 42, f"μ={group_mean:+.2f}%", 10, "middle", "normal", color),
                ]
            )
    elements.append(svg_text(width / 2, 500, "Mỗi chấm là một phiên; đường ngang đậm là trung bình lớp", 12, "middle"))
    write_svg("03_phan_bo_cam_bien.svg", width, height, elements)


def draw_time_series(sessions: list[dict[str, object]]) -> None:
    width, height = 1250, 1450
    left, right = 90, 1190
    panel_height = 245
    elements = [svg_text(width / 2, 38, "Đáp ứng EXPOSURE trung bình và khoảng Q25–Q75", 23, "middle", "bold")]
    for panel_index, sensor in enumerate(SENSORS):
        top = 75 + panel_index * 270
        bottom = top + panel_height
        grouped = time_series_matrix(sessions, sensor)
        stats = {}
        all_values = []
        for label in (0, 1):
            mean_line, q25, q75 = [], [], []
            for second in range(120):
                values = [series[second] for series in grouped[label]]
                mean_line.append(statistics.fmean(values))
                q25.append(percentile(values, .25))
                q75.append(percentile(values, .75))
            stats[label] = (mean_line, q25, q75)
            all_values.extend(q25 + q75)
        padding = max((max(all_values) - min(all_values)) * .1, .25)
        low, high = min(all_values) - padding, max(all_values) + padding
        mx = lambda second: linear_map(second, 0, 119, left, right)
        my = lambda value: linear_map(value, low, high, bottom, top)
        elements.extend(
            [
                svg_text(left, top - 12, SENSOR_LABELS[sensor], 15, "start", "bold"),
                f'<rect x="{left}" y="{top}" width="{right-left}" height="{panel_height}" fill="#fbfcfe" stroke="{GRID}"/>',
            ]
        )
        for second in (0, 20, 40, 60, 80, 100, 119):
            x = mx(second)
            elements.extend(
                [
                    f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{bottom}" stroke="{GRID}"/>',
                    svg_text(x, bottom + 18, second, 10, "middle"),
                ]
            )
        if low <= 0 <= high:
            elements.append(
                f'<line x1="{left}" y1="{my(0):.1f}" x2="{right}" y2="{my(0):.1f}" stroke="#777" stroke-dasharray="5 4"/>'
            )
        for label, color in ((0, BLUE), (1, RED)):
            mean_line, q25, q75 = stats[label]
            upper = [(mx(index), my(value)) for index, value in enumerate(q75)]
            lower = [(mx(index), my(value)) for index, value in reversed(list(enumerate(q25)))]
            elements.append(polygon(upper + lower, color))
            elements.append(
                polyline([(mx(index), my(value)) for index, value in enumerate(mean_line)], color, 2.5)
            )
        elements.extend(
            [
                svg_text(left - 9, top + 4, f"{high:+.1f}%", 10, "end"),
                svg_text(left - 9, bottom, f"{low:+.1f}%", 10, "end"),
            ]
        )
    elements.extend(
        [
            f'<line x1="{left}" y1="1415" x2="{left+28}" y2="1415" stroke="{BLUE}" stroke-width="4"/>',
            svg_text(left + 36, 1420, "Không cà phê (n=7)", 12),
            f'<line x1="{left+220}" y1="1415" x2="{left+248}" y2="1415" stroke="{RED}" stroke-width="4"/>',
            svg_text(left + 256, 1420, "Có cà phê (n=4)", 12),
            svg_text(right, 1420, "Trục X: giây trong EXPOSURE", 12, "end"),
        ]
    )
    write_svg("04_chuoi_thoi_gian_theo_lop.svg", width, height, elements)


def draw_positive_batches(sessions: list[dict[str, object]]) -> None:
    width, height = 1250, 1450
    left, right = 90, 1190
    panel_height = 245
    groups = {
        "Không CF": [session for session in sessions if session["label"] == 0],
        "Có CF chiều (#7,#8)": [session for session in sessions if session["session_no"] in {7, 8}],
        "Có CF tối (#15,#16)": [session for session in sessions if session["session_no"] in {15, 16}],
    }
    colors = {"Không CF": BLUE, "Có CF chiều (#7,#8)": RED, "Có CF tối (#15,#16)": ORANGE}
    elements = [svg_text(width / 2, 38, "So sánh batch: mẫu dương buổi chiều và buổi tối", 23, "middle", "bold")]
    for panel_index, sensor in enumerate(SENSORS):
        top = 75 + panel_index * 270
        bottom = top + panel_height
        lines = {}
        all_values = []
        for group_name, group_sessions in groups.items():
            series_group = []
            for session in group_sessions:
                points = normalized_exposure(str(session["folder"]), sensor)
                series_group.append([interpolate(points, float(second)) for second in range(120)])
            mean_line = [statistics.fmean(series[second] for series in series_group) for second in range(120)]
            lines[group_name] = mean_line
            all_values.extend(mean_line)
        padding = max((max(all_values) - min(all_values)) * .12, .25)
        low, high = min(all_values) - padding, max(all_values) + padding
        mx = lambda second: linear_map(second, 0, 119, left, right)
        my = lambda value: linear_map(value, low, high, bottom, top)
        elements.extend(
            [
                svg_text(left, top - 12, SENSOR_LABELS[sensor], 15, "start", "bold"),
                f'<rect x="{left}" y="{top}" width="{right-left}" height="{panel_height}" fill="#fbfcfe" stroke="{GRID}"/>',
            ]
        )
        for second in (0, 20, 40, 60, 80, 100, 119):
            x = mx(second)
            elements.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{bottom}" stroke="{GRID}"/>')
            elements.append(svg_text(x, bottom + 18, second, 10, "middle"))
        if low <= 0 <= high:
            elements.append(f'<line x1="{left}" y1="{my(0):.1f}" x2="{right}" y2="{my(0):.1f}" stroke="#777" stroke-dasharray="5 4"/>')
        for group_name, mean_line in lines.items():
            elements.append(polyline([(mx(index), my(value)) for index, value in enumerate(mean_line)], colors[group_name], 2.7))
        elements.extend(
            [
                svg_text(left - 9, top + 4, f"{high:+.1f}%", 10, "end"),
                svg_text(left - 9, bottom, f"{low:+.1f}%", 10, "end"),
            ]
        )
    legend_x = left
    for index, group_name in enumerate(groups):
        x = legend_x + index * 310
        elements.append(f'<line x1="{x}" y1="1415" x2="{x+30}" y2="1415" stroke="{colors[group_name]}" stroke-width="4"/>')
        elements.append(svg_text(x + 38, 1420, group_name, 12))
    write_svg("05_duong_chieu_vs_toi.svg", width, height, elements)


def draw_confusion() -> None:
    counts = [[0, 4, 3], [1, 2, 1]]
    row_totals = [7, 4]
    columns = ["Dự đoán CÓ", "Dự đoán KHÔNG", "Từ chối"]
    rows = ["Thật: KHÔNG CF", "Thật: CÓ CF"]
    width, height = 980, 500
    left, top, cell_w, cell_h = 245, 125, 220, 125
    elements = [svg_text(width / 2, 40, "Ma trận kết quả có vùng từ chối", 24, "middle", "bold")]
    for column_index, label in enumerate(columns):
        elements.append(svg_text(left + column_index * cell_w + cell_w / 2, 98, label, 14, "middle", "bold"))
    for row_index, label in enumerate(rows):
        y = top + row_index * cell_h
        elements.append(svg_text(left - 18, y + 68, label, 14, "end", "bold", BLUE if row_index == 0 else RED))
        for column_index, count in enumerate(counts[row_index]):
            x = left + column_index * cell_w
            correct = (row_index == 0 and column_index == 1) or (row_index == 1 and column_index == 0)
            color = "#dff2e7" if correct else "#fde7e9" if column_index != 2 else "#f1f3f6"
            elements.extend(
                [
                    f'<rect x="{x}" y="{y}" width="{cell_w}" height="{cell_h}" fill="{color}" stroke="white" stroke-width="4"/>',
                    svg_text(x + cell_w / 2, y + 58, count, 34, "middle", "bold"),
                    svg_text(x + cell_w / 2, y + 87, f"{count/row_totals[row_index]:.1%} của lớp", 12, "middle"),
                ]
            )
    elements.extend(
        [
            svg_text(width / 2, 420, "Coverage 63,6% · Accuracy khi kết luận 71,4%", 17, "middle", "bold"),
            svg_text(width / 2, 452, "Sensitivity cà phê 25% · False positive 0/7", 15, "middle"),
        ]
    )
    write_svg("06_confusion_co_tu_choi.svg", width, height, elements)


def draw_score_timeline(
    manifest: list[dict[str, str]], batch_rows: list[dict[str, object]]
) -> None:
    by_folder = {str(row["folder"]): row for row in batch_rows}
    rows = [row for row in manifest if row["folder"] in by_folder]
    width, height = 1450, 760
    left, right = 80, 1385
    top, bottom = 85, 625
    all_scores = [
        float(by_folder[row["folder"]][key])
        for row in rows
        for key in ("decision_score", "focused_score")
        if by_folder[row["folder"]][key] is not None
    ]
    low, high = min(all_scores) - .25, max(all_scores) + .25
    mx = lambda index: linear_map(index, 1, len(rows), left, right)
    my = lambda value: linear_map(value, low, high, bottom, top)
    elements = [svg_text(width / 2, 38, "Diễn biến score theo thứ tự thu mẫu", 23, "middle", "bold")]
    group_colors = {"AIR": "#8d99ae", "COFFEE_ONLY": ORANGE, "HUMAN_ONLY": BLUE, "HUMAN_COFFEE": RED, "PAIRED": "#7b61a8"}
    step = (right - left) / max(len(rows) - 1, 1)
    for index, row in enumerate(rows, start=1):
        x = mx(index)
        color = group_colors.get(row["experiment_group"], GRAY)
        elements.append(f'<rect x="{x-step/2:.1f}" y="{top}" width="{step:.1f}" height="{bottom-top}" fill="{color}" fill-opacity=".055"/>')
        elements.append(svg_text(x, bottom + 24, index, 10, "middle", "bold", color))
    for value in (-2, -1.5, -1, -.5, 0, .5, 1):
        if low <= value <= high:
            y = my(value)
            elements.append(f'<line x1="{left}" y1="{y:.1f}" x2="{right}" y2="{y:.1f}" stroke="{GRID}"/>')
            elements.append(svg_text(left - 10, y + 4, value, 11, "end"))
    main_points, mq_points = [], []
    for index, row in enumerate(rows, start=1):
        result = by_folder[row["folder"]]
        main_points.append((mx(index), my(float(result["decision_score"]))))
        mq_points.append((mx(index), my(float(result["focused_score"]))))
    elements.extend([polyline(main_points, "#222", 2.5), polyline(mq_points, GREEN, 2.5)])
    for index, ((main_x, main_y), (mq_x, mq_y)) in enumerate(zip(main_points, mq_points), start=1):
        elements.append(f'<circle cx="{main_x:.1f}" cy="{main_y:.1f}" r="4.5" fill="#222"/>')
        elements.append(f'<circle cx="{mq_x:.1f}" cy="{mq_y:.1f}" r="4.5" fill="{GREEN}"/>')
    elements.extend(
        [
            f'<line x1="{left}" y1="{my(0):.1f}" x2="{right}" y2="{my(0):.1f}" stroke="#555" stroke-width="1.6"/>',
            f'<line x1="{left}" y1="{my(.25):.1f}" x2="{right}" y2="{my(.25):.1f}" stroke="{RED}" stroke-dasharray="6 5"/>',
            f'<line x1="{left}" y1="{my(.6):.1f}" x2="{right}" y2="{my(.6):.1f}" stroke="{GREEN}" stroke-dasharray="6 5"/>',
            f'<line x1="{left}" y1="685" x2="{left+30}" y2="685" stroke="#222" stroke-width="4"/>',
            svg_text(left + 38, 690, "Main score", 12),
            f'<line x1="{left+150}" y1="685" x2="{left+180}" y2="685" stroke="{GREEN}" stroke-width="4"/>',
            svg_text(left + 188, 690, "MQ score", 12),
            svg_text(right, 690, "Số trên trục X là session_no trong manifest", 12, "end"),
            svg_text(width / 2, 735, "Đáng chú ý: #14 coffee-only high dương mạnh nhưng #15 human-coffee high ngay sau đó lại âm mạnh", 14, "middle", "bold", RED),
        ]
    )
    write_svg("07_score_theo_thu_tu_phien.svg", width, height, elements)


def draw_peak_outliers(sessions: list[dict[str, object]]) -> None:
    values = []
    for session in sessions:
        row = []
        for sensor in SENSORS:
            points = normalized_exposure(str(session["folder"]), sensor)
            row.append(max(abs(value) for _, value in points))
        values.append(row)
    width, height = 980, 650
    left, top, cell_w, cell_h = 290, 100, 125, 39
    maximum_log = max(math.log10(1 + value) for row in values for value in row)
    elements = [
        svg_text(width / 2, 38, "Đỉnh tuyệt đối trong EXPOSURE – phát hiện spike", 23, "middle", "bold"),
        svg_text(width / 2, 66, "Màu dùng log10(1 + |response|); số trong ô là phần trăm tuyệt đối", 12, "middle"),
    ]
    for column_index, sensor in enumerate(SENSORS):
        elements.append(
            svg_text(left + column_index * cell_w + cell_w / 2, top - 15, SENSOR_LABELS[sensor], 12, "middle", "bold")
        )
    for row_index, (session, row) in enumerate(zip(sessions, values)):
        y = top + row_index * cell_h
        elements.append(
            svg_text(
                left - 12,
                y + 25,
                f"#{session['session_no']} · {'CÓ CF' if session['label'] else 'KHÔNG CF'}",
                12,
                "end",
                "bold",
                RED if session["label"] else BLUE,
            )
        )
        for column_index, value in enumerate(row):
            strength = math.log10(1 + value) / maximum_log
            target = (198, 52, 60)
            channels = [round(250 + (channel - 250) * strength) for channel in target]
            color = "#" + "".join(f"{channel:02x}" for channel in channels)
            text_color = "white" if strength > .62 else "#222"
            x = left + column_index * cell_w
            elements.extend(
                [
                    f'<rect x="{x}" y="{y}" width="{cell_w}" height="{cell_h}" fill="{color}" stroke="white"/>',
                    svg_text(x + cell_w / 2, y + 25, f"{value:.1f}%", 12, "middle", "bold", text_color),
                ]
            )
    elements.extend(
        [
            svg_text(left, 570, "Các ô >10% cần kiểm tra tín hiệu gốc và cờ phần cứng.", 13, "start", "bold", RED),
            svg_text(left, 598, "Spike status=OK vẫn có thể làm lệch mean và slope; nên thử Hampel/median filter trong từng fold.", 12),
        ]
    )
    write_svg("08_heatmap_spike_outlier.svg", width, height, elements)


def write_report(sessions: list[dict[str, object]]) -> None:
    lines = [
        "# Phân tích trực quan chi tiết dữ liệu cà phê ngày 2026-10-28",
        "",
        "Bộ hình này tập trung vào 11 phiên `ELIGIBLE` có nhãn nhị phân và liên kết thêm các biểu đồ chất lượng/môi trường của toàn bộ 17 phiên.",
        "",
        "## 1. Bản đồ điểm mô hình",
        "",
        "![Bản đồ score](./01_ban_do_score.svg)",
        "",
        "Vùng trái-dưới là nơi cả hai mô hình cùng âm và được kết luận KHÔNG. Vùng phải-trên sau hai ngưỡng 0,25 và 0,60 được kết luận CÓ. Bốn mẫu còn từ chối nằm ở hai góc bất đồng. Mẫu dương #7 nằm cùng kiểu bất đồng với hai mẫu âm #9 và #10, nên không thể giải quyết an toàn chỉ bằng một ngưỡng score.",
        "",
        "## 2. Heatmap 25 đặc trưng",
        "",
        "![Heatmap feature](./02_heatmap_25_feature.svg)",
        "",
        "Màu biểu diễn z-score theo từng cột feature. Hai mẫu dương buổi chiều (#7, #8) có cụm BME688 và MQ3-1 khác rõ hơn, trong khi hai mẫu dương buổi tối (#15, #16) không lặp lại cùng fingerprint.",
        "",
        "## 3. Phân bố đáp ứng trung bình từng cảm biến",
        "",
        "![Phân bố cảm biến](./03_phan_bo_cam_bien.svg)",
        "",
        "Các lớp chồng lấn ở cả năm kênh. Vì vậy không có một cảm biến đơn lẻ đủ tạo ranh giới ổn định. BME688 và MQ3-1 cung cấp tín hiệu hữu ích nhất ở một số phiên nhưng vẫn chịu batch effect.",
        "",
        "## 4. Chuỗi thời gian theo lớp",
        "",
        "![Chuỗi theo lớp](./04_chuoi_thoi_gian_theo_lop.svg)",
        "",
        "Đường đậm là trung bình lớp; vùng mờ là Q25–Q75. Khoảng chồng lấn lớn cho thấy biến thiên giữa các phiên đang cùng cỡ hoặc lớn hơn khác biệt do cà phê.",
        "",
        "## 5. So sánh mẫu dương chiều và tối",
        "",
        "![Batch dương](./05_duong_chieu_vs_toi.svg)",
        "",
        "Đây là biểu đồ quan trọng nhất. Hai mẫu dương chiều (#7, #8) và hai mẫu dương tối (#15, #16) có hướng đáp ứng khác nhau trên nhiều kênh. Điều này giải thích vì sao mô hình nhận được #8 nhưng phân loại sai #15 và #16.",
        "",
        "## 6. Ma trận kết quả có vùng từ chối",
        "",
        "![Confusion](./06_confusion_co_tu_choi.svg)",
        "",
        "Mô hình không tạo false positive trên bảy mẫu âm, nhưng sensitivity dương chỉ đạt 25%. Accuracy 71,4% chỉ áp dụng trên bảy mẫu mà hệ thống dám kết luận; coverage là 63,6%.",
        "",
        "## 7. Drift theo thứ tự thu mẫu",
        "",
        "![Score timeline](./07_score_theo_thu_tu_phien.svg)",
        "",
        "Score thay đổi mạnh giữa khối đo chiều và tối. Đặc biệt #14 coffee-only high được nhận dương mạnh, nhưng #15 human-coffee high ngay sau đó lại âm mạnh. Cần kiểm tra thao tác đưa mùi từ cà phê lên người, vị trí đầu hút, thời gian recovery và khả năng baseline còn carry-over.",
        "",
        "## 8. Spike và ngoại lệ trong chuỗi",
        "",
        "![Spike outlier](./08_heatmap_spike_outlier.svg)",
        "",
        "Bốn ngoại lệ nổi bật là BME688 #7 (`−93,9%` tại khoảng giây 27), BME688 #9 (`−76,5%` tại khoảng giây 26), MQ135-2 #16 (`+21,4%` tại khoảng giây 73) và MQ3-2 #12 (`+58,9%` tại khoảng giây 76). Các điểm này vẫn vượt quality gate vì cờ phần cứng hợp lệ, nhưng có thể làm lệch feature mean và slope. Đây là cơ sở để thử lọc Hampel, median filter hoặc winsorization; mọi tham số lọc phải được chọn trong train fold để tránh làm đẹp riêng tập test.",
        "",
        "## 9. Biểu đồ chất lượng và môi trường đã có",
        "",
        "![Chất lượng dữ liệu](../report_assets/04_chat_luong_va_loi_doc.svg)",
        "",
        "![Môi trường theo thời gian](../report_assets/05_moi_truong_theo_thoi_gian.svg)",
        "",
        "![PCA](../coffee_difference_analysis/pca_scatter.svg)",
        "",
        "PCA cũng cho thấy hai mẫu dương buổi tối chồng lên vùng âm. PCA chỉ mô tả phương sai và không chứng minh khả năng phân loại.",
        "",
        "## Kết luận trực quan",
        "",
        "1. Không có một feature hoặc cảm biến đơn lẻ tách sạch hai lớp.",
        "2. Hai mẫu dương buổi chiều tạo tín hiệu BME688/MQ3-1 rõ hơn hai mẫu dương buổi tối.",
        "3. Batch effect theo thời gian thu mẫu là rất mạnh.",
        "4. Các mẫu `UNCERTAIN` thực sự nằm ở vùng hai mô hình bất đồng, không chỉ thiếu một chút ngưỡng.",
        "5. Ưu tiên tiếp theo nên là chuẩn hóa quy trình đo và thu thêm positive độc lập ở nhiều ngày, thay vì tăng độ phức tạp mô hình ngay lập tức.",
        "",
        "## Tái tạo biểu đồ",
        "",
        "```powershell",
        "python analysis\\visualize_2026_10_28_coffee.py",
        "```",
    ]
    (OUTPUT_ROOT / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    manifest, batch_rows = load_inputs()
    sessions = eligible_sessions(manifest, batch_rows)
    draw_score_map(sessions)
    draw_feature_heatmap(sessions)
    draw_sensor_distributions(sessions)
    draw_time_series(sessions)
    draw_positive_batches(sessions)
    draw_confusion()
    draw_score_timeline(manifest, batch_rows)
    draw_peak_outliers(sessions)
    write_report(sessions)
    print(f"Đã tạo 8 biểu đồ SVG và báo cáo tại: {OUTPUT_ROOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
