"""Generate the Vietnamese README and SVG diagnostics for data/2026-10-25."""

from __future__ import annotations

import csv
import html
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "2026-10-25"
AUGMENTED = ROOT / "data" / "2026-10-25_augmented"
ASSETS = DATA / "report_assets"

SENSORS = [
    "gas_resistance_ohm",
    "mq135_1_voltage_v",
    "mq3_1_voltage_v",
    "mq135_2_voltage_v",
    "mq3_2_voltage_v",
]
SENSOR_LABELS = {
    "gas_resistance_ohm": "BME gas",
    "mq135_1_voltage_v": "MQ135-1",
    "mq3_1_voltage_v": "MQ3-1",
    "mq135_2_voltage_v": "MQ135-2",
    "mq3_2_voltage_v": "MQ3-2",
}
COLORS = {
    "Dung": "#0072B2",
    "Minh": "#009E73",
    "Quy": "#E69F00",
    "Tai": "#CC79A7",
    "rejected": "#D55E00",
    "grid": "#D7DEE8",
    "text": "#172033",
    "muted": "#5D687A",
    "panel": "#F7F9FC",
}


def parse_float(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def mean(values) -> float:
    items = list(values)
    return statistics.fmean(items) if items else math.nan


def standard_deviation(values) -> float:
    items = list(values)
    if len(items) < 2:
        return 0.0
    center = mean(items)
    return math.sqrt(sum((value - center) ** 2 for value in items) / (len(items) - 1))


def percentile(values, fraction: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def slope(values: list[float]) -> float:
    if len(values) < 2:
        return math.nan
    x_center = (len(values) - 1) / 2
    y_center = mean(values)
    denominator = sum((index - x_center) ** 2 for index in range(len(values)))
    return sum(
        (index - x_center) * (value - y_center)
        for index, value in enumerate(values)
    ) / denominator


def person_from_folder(folder: str) -> str:
    raw = folder.split("_", 1)[0]
    return {"adung": "Dung", "aminh": "Minh", "aquy": "Quy", "tai": "Tai"}.get(
        raw.lower(), raw
    )


def short_run(folder: str) -> str:
    parts = folder.split("_")
    person = person_from_folder(folder)
    time_text = parts[2] if len(parts) > 2 else ""
    return f"{person} {time_text[:2]}:{time_text[2:4]}"


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_inventory() -> list[dict[str, object]]:
    quality = {row["source_run"]: row for row in load_csv(AUGMENTED / "run_quality.csv")}
    inventory = []
    for directory in sorted(path for path in DATA.iterdir() if path.is_dir() and path.name != "report_assets"):
        raw = load_csv(directory / "raw.csv")
        metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
        summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
        quality_row = quality[directory.name]
        inventory.append(
            {
                "folder": directory.name,
                "person": person_from_folder(directory.name),
                "short": short_run(directory.name),
                "started_at": metadata.get("started_at", ""),
                "rows": len(raw),
                "warnings": len(summary.get("warnings", [])),
                "accepted": quality_row["accepted"] == "True",
                "reason": quality_row["rejection_reasons"],
                "raw": raw,
                "quality": quality_row,
            }
        )
    return inventory


def normalized_phase(run, sensor: str, phase: str) -> list[float]:
    baseline = [
        value
        for row in run["raw"]
        if row.get("phase") == "BASELINE"
        for value in [parse_float(row.get(sensor))]
        if value is not None
    ]
    values = [
        value
        for row in run["raw"]
        if row.get("phase") == phase
        for value in [parse_float(row.get(sensor))]
        if value is not None
    ]
    if not baseline or not values:
        return []
    center = statistics.median(baseline)
    return [100 * (value - center) / abs(center) for value in values]


def response_features(run, sensor: str) -> dict[str, float]:
    exposure = normalized_phase(run, sensor, "EXPOSURE")
    recovery = normalized_phase(run, sensor, "RECOVERY")
    third = len(exposure) // 3
    return {
        "early": mean(exposure[:third]),
        "middle": mean(exposure[third : 2 * third]),
        "late": mean(exposure[2 * third :]),
        "q10": percentile(exposure, 0.10),
        "q90": percentile(exposure, 0.90),
        "slope": slope(exposure),
        "recovery_end": mean(recovery[-10:]),
        "recovery_slope": slope(recovery),
    }


def standardized_vectors(rows: list[dict[str, float]]) -> list[list[float]]:
    names = list(rows[0])
    centers = {name: mean(row[name] for row in rows) for name in names}
    scales = {name: standard_deviation(row[name] for row in rows) or 1.0 for name in names}
    return [
        [(row[name] - centers[name]) / scales[name] for name in names]
        for row in rows
    ]


def euclidean(left: list[float], right: list[float]) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right)) / len(left))


def sensor_scores(inventory: list[dict[str, object]]) -> list[dict[str, object]]:
    clean = [run for run in inventory if run["accepted"]]
    tai_indexes = [index for index, run in enumerate(clean) if run["person"] == "Tai"]
    other_indexes = [index for index, run in enumerate(clean) if run["person"] != "Tai"]
    scores = []
    for sensor in SENSORS:
        vectors = standardized_vectors([response_features(run, sensor) for run in clean])
        within = [
            euclidean(vectors[left], vectors[right])
            for position, left in enumerate(tai_indexes)
            for right in tai_indexes[position + 1 :]
        ]
        between = [
            euclidean(vectors[left], vectors[right])
            for left in tai_indexes
            for right in other_indexes
        ]
        nearest_correct = 0
        for index in tai_indexes:
            nearest = min(
                (euclidean(vectors[index], vectors[other]), other)
                for other in range(len(clean))
                if other != index
            )[1]
            nearest_correct += clean[nearest]["person"] == "Tai"
        scores.append(
            {
                "sensor": sensor,
                "ratio": mean(between) / mean(within),
                "tai_nn": nearest_correct,
            }
        )
    return scores


def svg_document(width: int, height: int, body: str, title: str) -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<title>{html.escape(title)}</title>
<rect width="100%" height="100%" fill="#FFFFFF"/>
<style>
text {{ font-family: "Segoe UI", Arial, sans-serif; fill: {COLORS['text']}; }}
.title {{ font-size: 28px; font-weight: 700; }}
.subtitle {{ font-size: 15px; fill: {COLORS['muted']}; }}
.axis {{ font-size: 13px; fill: {COLORS['muted']}; }}
.label {{ font-size: 14px; font-weight: 600; }}
.value {{ font-size: 13px; font-weight: 700; }}
</style>
{body}
</svg>'''


def text(x: float, y: float, value: object, css: str = "axis", anchor: str = "start") -> str:
    return f'<text x="{x:.1f}" y="{y:.1f}" class="{css}" text-anchor="{anchor}">{html.escape(str(value))}</text>'


def write_svg(name: str, content: str) -> None:
    path = ASSETS / name
    path.write_text(content, encoding="utf-8")
    ElementTree.parse(path)


def chart_coverage(inventory: list[dict[str, object]]) -> None:
    counts = Counter(run["person"] for run in inventory)
    people = ["Dung", "Minh", "Quy", "Tai"]
    width, height = 960, 520
    left, top, plot_width, plot_height = 110, 105, 760, 300
    maximum = max(counts.values())
    bar_width = 120
    gap = (plot_width - len(people) * bar_width) / (len(people) - 1)
    elements = [text(55, 48, "Số phiên đo thật theo người", "title"), text(55, 76, "Dữ liệu mất cân bằng: Tai có 4 phiên, mỗi người còn lại chỉ có 1 phiên.", "subtitle")]
    for tick in range(maximum + 1):
        y = top + plot_height - tick / maximum * plot_height
        elements.append(f'<line x1="{left}" y1="{y}" x2="{left + plot_width}" y2="{y}" stroke="{COLORS["grid"]}"/>')
        elements.append(text(left - 14, y + 5, tick, anchor="end"))
    for index, person in enumerate(people):
        x = left + index * (bar_width + gap)
        bar_height = counts[person] / maximum * plot_height
        y = top + plot_height - bar_height
        elements.append(f'<rect x="{x}" y="{y}" width="{bar_width}" height="{bar_height}" rx="8" fill="{COLORS[person]}"/>')
        elements.append(text(x + bar_width / 2, y - 12, counts[person], "value", "middle"))
        elements.append(text(x + bar_width / 2, top + plot_height + 30, person, "label", "middle"))
    write_svg("01_so_phien_theo_nguoi.svg", svg_document(width, height, "\n".join(elements), "Số phiên theo người"))


def chart_quality(inventory: list[dict[str, object]]) -> None:
    width, height = 1180, 600
    left, top, plot_width, row_height = 285, 110, 800, 58
    elements = [text(48, 48, "Chất lượng dữ liệu lõi của từng phiên", "title"), text(48, 76, "Thanh biểu diễn tỷ lệ hợp lệ thấp nhất giữa BASELINE, EXPOSURE và RECOVERY.", "subtitle")]
    for tick in range(0, 101, 20):
        x = left + plot_width * tick / 100
        elements.append(f'<line x1="{x}" y1="{top - 25}" x2="{x}" y2="{top + row_height * len(inventory)}" stroke="{COLORS["grid"]}"/>')
        elements.append(text(x, top - 34, f"{tick}%", anchor="middle"))
    for index, run in enumerate(inventory):
        y = top + index * row_height
        quality = run["quality"]
        gas = min(float(quality[f"gas_{phase}_valid_fraction"]) for phase in ("baseline", "exposure", "recovery")) * 100
        mq = min(float(quality[f"mq135_1_{phase}_valid_fraction"]) for phase in ("baseline", "exposure", "recovery")) * 100
        elements.append(text(left - 18, y + 23, run["short"], "label", "end"))
        elements.append(f'<rect x="{left}" y="{y + 4}" width="{plot_width * gas / 100}" height="15" rx="4" fill="#4C78A8"/>')
        elements.append(f'<rect x="{left}" y="{y + 25}" width="{plot_width * mq / 100}" height="15" rx="4" fill="#F58518"/>')
        status = "Đạt" if run["accepted"] else "Loại"
        color = "#17834B" if run["accepted"] else COLORS["rejected"]
        elements.append(f'<text x="{left + plot_width + 18}" y="{y + 27}" class="value" style="fill:{color}">{status}</text>')
    elements.append(f'<rect x="{left}" y="{height - 47}" width="16" height="12" fill="#4C78A8"/>')
    elements.append(text(left + 24, height - 36, "BME gas"))
    elements.append(f'<rect x="{left + 120}" y="{height - 47}" width="16" height="12" fill="#F58518"/>')
    elements.append(text(left + 144, height - 36, "MQ135-1"))
    write_svg("02_chat_luong_tung_phien.svg", svg_document(width, height, "\n".join(elements), "Chất lượng từng phiên"))


def heat_color(value: float, limit: float = 1.0) -> str:
    clipped = max(-limit, min(limit, value)) / limit
    if clipped >= 0:
        start, end = (247, 249, 252), (213, 94, 0)
    else:
        clipped = -clipped
        start, end = (247, 249, 252), (0, 114, 178)
    rgb = tuple(round(start[index] + clipped * (end[index] - start[index])) for index in range(3))
    return "#" + "".join(f"{component:02X}" for component in rgb)


def chart_response_heatmap(inventory: list[dict[str, object]]) -> None:
    width, height = 1180, 720
    left, top, cell_width, cell_height = 310, 135, 150, 62
    elements = [text(48, 48, "Đáp ứng trung bình trong pha EXPOSURE", "title"), text(48, 76, "Đơn vị: % so với median baseline. Màu bị giới hạn ở ±1%; con số trong ô là giá trị thật.", "subtitle")]
    for column, sensor in enumerate(SENSORS):
        elements.append(text(left + column * cell_width + cell_width / 2, top - 22, SENSOR_LABELS[sensor], "label", "middle"))
    for row_index, run in enumerate(inventory):
        y = top + row_index * cell_height
        elements.append(text(left - 18, y + 36, run["short"], "label", "end"))
        if not run["accepted"]:
            elements.append(text(left - 18, y + 53, "phiên bị loại", "axis", "end"))
        for column, sensor in enumerate(SENSORS):
            values = normalized_phase(run, sensor, "EXPOSURE")
            value = mean(values)
            x = left + column * cell_width
            elements.append(f'<rect x="{x}" y="{y}" width="{cell_width - 4}" height="{cell_height - 4}" rx="5" fill="{heat_color(value)}"/>')
            foreground = "#FFFFFF" if abs(value) >= 0.65 else COLORS["text"]
            elements.append(f'<text x="{x + (cell_width - 4) / 2}" y="{y + 36}" class="value" text-anchor="middle" style="fill:{foreground}">{value:+.3f}%</text>')
    legend_y = top + len(inventory) * cell_height + 32
    for index in range(101):
        value = -1 + 2 * index / 100
        elements.append(f'<rect x="{left + index * 4}" y="{legend_y}" width="4.2" height="16" fill="{heat_color(value)}"/>')
    elements.extend([text(left, legend_y + 38, "−1%"), text(left + 202, legend_y + 38, "0%", anchor="middle"), text(left + 404, legend_y + 38, "+1%", anchor="end")])
    write_svg("03_heatmap_dap_ung_cam_bien.svg", svg_document(width, height, "\n".join(elements), "Đáp ứng cảm biến"))


def chart_sensor_scores(scores: list[dict[str, object]]) -> None:
    width, height = 1040, 570
    left, top, plot_width, row_height = 250, 115, 650, 72
    maximum = 1.8
    elements = [text(48, 48, "Khả năng tách Tai khỏi người khác theo cảm biến", "title"), text(48, 76, "Tỷ lệ > 1 tốt hơn; chỉ là chỉ báo thăm dò vì ba người còn lại có một phiên.", "subtitle")]
    for tick in [0, 0.5, 1.0, 1.5]:
        x = left + plot_width * tick / maximum
        elements.append(f'<line x1="{x}" y1="{top - 18}" x2="{x}" y2="{top + row_height * len(scores)}" stroke="{COLORS["grid"]}"/>')
        elements.append(text(x, top - 27, tick, anchor="middle"))
    threshold_x = left + plot_width / maximum
    elements.append(f'<line x1="{threshold_x}" y1="{top - 24}" x2="{threshold_x}" y2="{top + row_height * len(scores)}" stroke="#D55E00" stroke-width="2" stroke-dasharray="6 5"/>')
    for index, score in enumerate(scores):
        y = top + index * row_height
        ratio = float(score["ratio"])
        selected = score["sensor"] in {"gas_resistance_ohm", "mq135_1_voltage_v"}
        color = "#2A9D8F" if selected else "#9AA6B2"
        elements.append(text(left - 18, y + 32, SENSOR_LABELS[score["sensor"]], "label", "end"))
        elements.append(f'<rect x="{left}" y="{y + 10}" width="{plot_width * ratio / maximum}" height="28" rx="6" fill="{color}"/>')
        elements.append(text(left + plot_width * ratio / maximum + 10, y + 31, f"{ratio:.2f} · Tai NN {score['tai_nn']}/3", "value"))
    write_svg("04_xep_hang_cam_bien.svg", svg_document(width, height, "\n".join(elements), "Xếp hạng cảm biến"))


def cosine(left: list[float], right: list[float]) -> float:
    denominator = math.sqrt(sum(value * value for value in left) * sum(value * value for value in right))
    return sum(a * b for a, b in zip(left, right)) / denominator if denominator else 0.0


def vector(row: dict[str, str]) -> list[float]:
    return [float(row[f"v_{index:02d}"]) for index in range(1, 8)]


def chart_cosine_matrix(feature_rows: list[dict[str, str]]) -> None:
    real = [row for row in feature_rows if row["is_augmented"] == "False"]
    labels = [short_run(row["source_run"]) for row in real]
    width, height = 1040, 880
    left, top, cell = 305, 190, 88
    elements = [text(48, 48, "Cosine similarity giữa các phiên thật đạt chất lượng", "title"), text(48, 76, "Vector 7 chiều đã z-score và chuẩn hóa L2. Giá trị cao nghĩa là hướng đặc trưng giống nhau.", "subtitle")]
    for index, label in enumerate(labels):
        elements.append(text(left + index * cell + cell / 2, top - 18, label, "label", "middle"))
        elements.append(text(left - 18, top + index * cell + cell / 2 + 5, label, "label", "end"))
    for row_index, left_row in enumerate(real):
        for column_index, right_row in enumerate(real):
            value = cosine(vector(left_row), vector(right_row))
            normalized = (value + 1) / 2
            start, end = (247, 249, 252), (44, 123, 182)
            rgb = tuple(round(start[i] + normalized * (end[i] - start[i])) for i in range(3))
            color = "#" + "".join(f"{component:02X}" for component in rgb)
            x, y = left + column_index * cell, top + row_index * cell
            elements.append(f'<rect x="{x}" y="{y}" width="{cell - 4}" height="{cell - 4}" rx="5" fill="{color}"/>')
            foreground = "#FFFFFF" if value > 0.35 else COLORS["text"]
            elements.append(f'<text x="{x + (cell - 4) / 2}" y="{y + cell / 2}" class="value" text-anchor="middle" style="fill:{foreground}">{value:.3f}</text>')
    write_svg("05_ma_tran_cosine_phien_that.svg", svg_document(width, height, "\n".join(elements), "Ma trận cosine"))


def chart_augmentation_similarity(feature_rows: list[dict[str, str]]) -> tuple[float, float]:
    real = {row["source_run"]: vector(row) for row in feature_rows if row["is_augmented"] == "False"}
    similarities = [
        cosine(vector(row), real[row["source_run"]])
        for row in feature_rows
        if row["is_augmented"] == "True"
    ]
    lower, upper, bins = 0.95, 1.0, 10
    counts = [0] * bins
    for value in similarities:
        index = min(bins - 1, max(0, int((value - lower) / (upper - lower) * bins)))
        counts[index] += 1
    width, height = 980, 540
    left, top, plot_width, plot_height = 105, 115, 790, 300
    maximum = max(counts)
    bar_width = plot_width / bins
    elements = [text(48, 48, "Mức bảo toàn vector sau augmentation", "title"), text(48, 76, "Cosine giữa mỗi bản augmented và phiên thật nguồn; càng gần 1 càng ít biến dạng.", "subtitle")]
    for tick in range(0, maximum + 1, max(1, maximum // 4)):
        y = top + plot_height - tick / maximum * plot_height
        elements.append(f'<line x1="{left}" y1="{y}" x2="{left + plot_width}" y2="{y}" stroke="{COLORS["grid"]}"/>')
        elements.append(text(left - 12, y + 5, tick, anchor="end"))
    for index, count in enumerate(counts):
        x = left + index * bar_width + 3
        bar_height = count / maximum * plot_height
        y = top + plot_height - bar_height
        elements.append(f'<rect x="{x}" y="{y}" width="{bar_width - 6}" height="{bar_height}" rx="4" fill="#2A9D8F"/>')
    for index in range(bins + 1):
        x = left + index * bar_width
        elements.append(text(x, top + plot_height + 28, f"{lower + index * (upper - lower) / bins:.3f}", anchor="middle"))
    minimum = min(similarities)
    median = statistics.median(similarities)
    elements.append(text(left, height - 50, f"Tối thiểu: {minimum:.3f}", "value"))
    elements.append(text(left + 220, height - 50, f"Trung vị: {median:.3f}", "value"))
    write_svg("06_bao_toan_sau_augmentation.svg", svg_document(width, height, "\n".join(elements), "Bảo toàn sau augmentation"))
    return minimum, median


def markdown_inventory(inventory: list[dict[str, object]]) -> str:
    lines = [
        "| Phiên | Người | Bắt đầu | Dòng | Cảnh báo | Trạng thái |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for run in inventory:
        started = str(run["started_at"])[11:19]
        status = "Đạt" if run["accepted"] else "Loại khỏi augmentation"
        lines.append(
            f"| `{run['folder']}` | {run['person']} | {started} | {run['rows']} | {run['warnings']} | **{status}** |"
        )
    return "\n".join(lines)


def markdown_run_plots(inventory: list[dict[str, object]]) -> str:
    blocks = []
    for run in inventory:
        note = " — phiên bị loại do thiếu dữ liệu BME" if not run["accepted"] else ""
        blocks.append(
            f"""<details>
<summary><strong>{run['short']}</strong>{note}</summary>

![Tín hiệu chuẩn hóa {run['short']}](./{run['folder']}/normalized.png)

</details>"""
        )
    return "\n\n".join(blocks)


def write_readme(
    inventory: list[dict[str, object]],
    scores: list[dict[str, object]],
    minimum_similarity: float,
    median_similarity: float,
) -> None:
    accepted = [run for run in inventory if run["accepted"]]
    rejected = [run for run in inventory if not run["accepted"]]
    score_by_sensor = {row["sensor"]: row for row in scores}
    readme = f"""# Bộ dữ liệu mùi ngày 2026-10-25

## Hướng dẫn sử dụng

### 1. Tạo lại dữ liệu augmented và model vector

Chạy từ thư mục gốc của dự án:

```powershell
python analysis\\augment_and_extract_odor_features.py
```

Lệnh này đọc dữ liệu trong `data/2026-10-25/`, kiểm tra chất lượng, làm giàu tín hiệu, trích đặc trưng và tạo model trong `data/2026-10-25_augmented/`.

### 2. Chuẩn bị một mẫu cần nhận diện

Mẫu mới phải được thu bằng cùng hệ cảm biến và cùng quy trình:

```text
BASELINE 60 giây → EXPOSURE 120 giây → RECOVERY 60 giây
```

Lưu kết quả thành `raw.csv` có cùng cấu trúc cột với dữ liệu hiện tại. Không augmentation mẫu mới trước khi nhận diện.

### 3. Kiểm tra mẫu mới

Có thể truyền đường dẫn tới cả thư mục phiên:

```powershell
python analysis\\predict_odor_identity.py --input "data\\mau_moi"
```

Hoặc truyền trực tiếp file CSV:

```powershell
python analysis\\predict_odor_identity.py --input "data\\mau_moi\\raw.csv"
```

Script tự thực hiện:

1. Kiểm tra chất lượng BME gas và MQ135-1 trong ba pha.
2. Nội suy tín hiệu về 60/120/60 mẫu.
3. Chuẩn hóa theo median baseline.
4. Trích bảy đặc trưng và áp dụng `scaler.json`.
5. Chuẩn hóa L2 thành vector cosine.
6. So sánh với bốn profile trong `identity_model.json`.
7. Kiểm tra cosine và khoảng cách top-1/top-2 theo ngưỡng của từng người.

Kết quả được ghi vào `prediction.json` bên cạnh `raw.csv`.

### 4. Đọc kết quả

| Trạng thái | Ý nghĩa |
|---|---|
| `identity_accepted` | Mẫu phù hợp với profile của người được dự đoán. |
| `identity_rejected` | Không đủ giống hoặc kết quả giữa hai người quá gần nhau. |
| `quality_rejected` | Tín hiệu không đạt chất lượng nên không nhận diện. |
| `ranked_match_only` | Model không có ngưỡng; chỉ trả về bảng xếp hạng cosine. |

Các trường quan trọng trong `prediction.json`:

- `prediction.person`: người được chấp nhận; bằng `null` nếu bị từ chối.
- `prediction.best_match`: người có cosine cao nhất.
- `prediction.best_cosine_similarity`: cosine của người đứng đầu.
- `prediction.margin`: chênh lệch cosine giữa top-1 và top-2.
- `scores`: toàn bộ điểm của bốn người.

Ngưỡng mặc định nằm trong `identity_model.json`. Có thể ghi đè sau khi đã hiệu chỉnh bằng dữ liệu thật độc lập:

```powershell
python analysis\\predict_odor_identity.py `
  --input "data\\mau_moi\\raw.csv" `
  --reject-below <nguong_cosine> `
  --min-margin <chenh_lech_top1_top2>
```

### 5. Các tệp model cần giữ

- `../2026-10-25_augmented/scaler.json`: mean/std để chuẩn hóa đặc trưng mẫu mới.
- `../2026-10-25_augmented/identity_model.json`: centroid và ngưỡng tương thích của bốn người.
- `../2026-10-25_augmented/identity_profiles.csv`: bảng profile để kiểm tra thủ công.
- `../2026-10-25_augmented/feature_vectors.csv`: toàn bộ vector thật và augmented.

> Ngưỡng hiện được ước lượng từ dữ liệu augmented nên vẫn là ngưỡng thử nghiệm. Cần kiểm chứng trên các phiên thật chưa từng dùng tạo model.

---

## Giải thích đã làm gì với bộ dữ liệu `2026-10-25`

### Tóm tắt

Bộ dữ liệu gồm **{len(inventory)} phiên đo của 4 người**: Dung, Minh, Quy và Tai. Sau kiểm tra chất lượng, **{len(accepted)} phiên đạt** và **{len(rejected)} phiên bị loại khỏi pipeline làm giàu**. Dữ liệu này phù hợp để thử nghiệm pipeline tín hiệu và cosine similarity, nhưng chưa đủ để kết luận hệ thống nhận diện ổn định bốn người vì Dung, Minh và Quy mới có một phiên thật/người.

![Số phiên theo người](./report_assets/01_so_phien_theo_nguoi.svg)

### Danh sách phiên đo

{markdown_inventory(inventory)}

Phiên `{rejected[0]['folder']}` bị loại vì tỷ lệ BME hợp lệ trong EXPOSURE chỉ khoảng **3,3%** và trong RECOVERY khoảng **80%**. Phiên này cũng có thời gian MONITOR rất dài và bước nhảy tín hiệu khác hẳn các phiên còn lại.

![Chất lượng từng phiên](./report_assets/02_chat_luong_tung_phien.svg)

### Đáp ứng của từng cảm biến

Heatmap dưới đây biểu diễn mức thay đổi trung bình trong EXPOSURE so với median BASELINE. Dấu âm nghĩa là tín hiệu thấp hơn baseline; không phải điện áp hay điện trở vật lý âm.

![Heatmap đáp ứng cảm biến](./report_assets/03_heatmap_dap_ung_cam_bien.svg)

#### Đánh giá cảm biến

| Cảm biến | Tỷ lệ tách biệt/lặp lại | Tai có láng giềng gần nhất là Tai | Quyết định |
|---|---:|---:|---|
| BME gas resistance | {score_by_sensor['gas_resistance_ohm']['ratio']:.2f} | {score_by_sensor['gas_resistance_ohm']['tai_nn']}/3 | **Giữ** |
| MQ135-1 | {score_by_sensor['mq135_1_voltage_v']['ratio']:.2f} | {score_by_sensor['mq135_1_voltage_v']['tai_nn']}/3 | **Giữ** |
| MQ3-1 | {score_by_sensor['mq3_1_voltage_v']['ratio']:.2f} | {score_by_sensor['mq3_1_voltage_v']['tai_nn']}/3 | Kênh phụ, chưa đưa vào vector chính |
| MQ135-2 | {score_by_sensor['mq135_2_voltage_v']['ratio']:.2f} | {score_by_sensor['mq135_2_voltage_v']['tai_nn']}/3 | Tạm loại khỏi vector |
| MQ3-2 | {score_by_sensor['mq3_2_voltage_v']['ratio']:.2f} | {score_by_sensor['mq3_2_voltage_v']['tai_nn']}/3 | Tạm loại khỏi vector |

![Xếp hạng cảm biến](./report_assets/04_xep_hang_cam_bien.svg)

Tỷ lệ lớn hơn 1 nghĩa là khoảng cách Tai–người khác lớn hơn khoảng cách giữa các phiên Tai. Đây chỉ là đánh giá thăm dò vì chỉ Tai có dữ liệu lặp.

### Mức giống nhau giữa các phiên thật

![Ma trận cosine](./report_assets/05_ma_tran_cosine_phien_that.svg)

Ma trận dùng vector bảy chiều từ BME gas và MQ135-1. Một số phiên khác người vẫn có cosine cao, vì vậy chưa nên đặt ngưỡng nhận diện chính thức từ bộ dữ liệu này.

### Tín hiệu chuẩn hóa của từng phiên

Các hình dưới đây là biểu đồ có sẵn của từng phiên, hiển thị toàn bộ MONITOR, BASELINE, EXPOSURE và RECOVERY.

{markdown_run_plots(inventory)}

### Dữ liệu đã được làm giàu như thế nào

Pipeline nằm tại `../../analysis/augment_and_extract_odor_features.py`. Kết quả nằm trong `../2026-10-25_augmented/`.

#### Lọc và chuẩn hóa

1. Chỉ giữ sáu phiên có ít nhất 90% mẫu hợp lệ trong từng pha lõi.
2. Chỉ dùng `gas_resistance_ohm` và `mq135_1_voltage_v` cho vector chính.
3. Nội suy mỗi phiên về độ dài cố định: BASELINE 60 mẫu, EXPOSURE 120 mẫu, RECOVERY 60 mẫu.
4. Chuẩn hóa từng cảm biến theo median baseline:

```text
response_pct = 100 × (signal - baseline_median) / abs(baseline_median)
```

#### Augmentation

Từ mỗi phiên thật đạt chất lượng, pipeline tạo 20 biến thể. Mọi phép biến đổi đều giữ nguyên thứ tự pha và áp dụng cùng tham số thời gian/biên độ cho hai cảm biến:

- Nhân biên độ toàn cục: `0.97–1.03`.
- Co giãn thời gian nhẹ: `0.98–1.02`.
- Dịch thời gian: `−2..+2` mẫu.
- Cộng `0.10–0.30` lần residual noise lấy từ baseline thật.
- Không trộn dữ liệu giữa hai người, không đảo dấu và không xáo trộn các pha.

Kết quả gồm **126 mẫu**: 6 mẫu thật và 120 mẫu augmented, tương ứng **30.240 dòng tín hiệu**.

![Bảo toàn vector sau augmentation](./report_assets/06_bao_toan_sau_augmentation.svg)

Cosine giữa bản augmented và phiên nguồn có giá trị tối thiểu **{minimum_similarity:.3f}**, trung vị **{median_similarity:.3f}**. Điều này cho thấy augmentation hiện tại chỉ tạo nhiễu/biến dạng nhẹ và không làm đổi mạnh hướng vector đặc trưng.

#### Vector đặc trưng

Mỗi mẫu được nén thành vector bảy đặc trưng:

1. Trung bình BME gas trong EXPOSURE.
2. Trung bình BME gas ở một phần ba giữa EXPOSURE.
3. Phân vị 10% của BME gas trong EXPOSURE.
4. Phân vị 90% của BME gas trong EXPOSURE.
5. Trung bình MQ135-1 ở một phần ba giữa EXPOSURE.
6. Slope MQ135-1 trong EXPOSURE.
7. Trung bình 10 giây cuối RECOVERY của MQ135-1.

Các đặc trưng được z-score bằng mean/std của **sáu phiên thật**, sau đó chuẩn hóa L2 thành `v_01..v_07`. Ngoài prototype chỉ dùng phiên thật, pipeline còn tạo profile augmented theo cách: trung bình các biến thể trong từng `source_run`, chuẩn hóa L2, rồi trung bình các centroid phiên với trọng số bằng nhau. Vì vậy một người có nhiều phiên không làm một phiên cụ thể bị nhân trọng số bởi augmentation.

### Các tệp kết quả

- `../2026-10-25_augmented/augmented_signals.csv`: bảng tín hiệu đã làm giàu.
- `../2026-10-25_augmented/feature_vectors.csv`: đặc trưng gốc, z-score và vector cosine-ready.
- `../2026-10-25_augmented/person_prototypes.csv`: prototype của bốn người.
- `../2026-10-25_augmented/identity_profiles.csv`: vector và ngưỡng tương thích của từng người.
- `../2026-10-25_augmented/identity_model.json`: model vector dùng để kiểm tra mẫu mới.
- `../2026-10-25_augmented/run_quality.csv`: kiểm tra chất lượng từng phiên.
- `../2026-10-25_augmented/scaler.json`: tham số chuẩn hóa để xử lý mẫu mới.

### Kết luận

- Pipeline hiện tại bảo toàn tốt vector nguồn và phù hợp để thử nghiệm cosine similarity.
- BME gas và MQ135-1 là hai kênh nên ưu tiên ở phiên bản đầu.
- Augmentation không giải quyết được việc Dung, Minh và Quy chỉ có một phiên thật.
- Khi đánh giá mô hình, tất cả biến thể có cùng `source_run` phải nằm cùng một phía train hoặc test để tránh rò rỉ dữ liệu.

"""
    _, data_description = readme.split(
        "## Giải thích đã làm gì với bộ dữ liệu `2026-10-25`", 1
    )
    readme = (
        "# Mô tả bộ dữ liệu mùi ngày 2026-10-25\n\n"
        "Tài liệu này chỉ mô tả dữ liệu gốc, chất lượng từng phiên, đáp ứng cảm biến, "
        "các biểu đồ phân tích và những biến đổi đã áp dụng khi tạo bộ augmented. "
        "Hướng dẫn chạy pipeline và nhận diện mẫu mới nằm ở "
        "[`README.md`](../../README.md) tại thư mục gốc của repository.\n\n"
        "## Phân tích bộ dữ liệu"
        + data_description
    )
    (DATA / "README.md").write_text(readme, encoding="utf-8")


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    inventory = load_inventory()
    feature_rows = load_csv(AUGMENTED / "feature_vectors.csv")
    scores = sensor_scores(inventory)
    chart_coverage(inventory)
    chart_quality(inventory)
    chart_response_heatmap(inventory)
    chart_sensor_scores(scores)
    chart_cosine_matrix(feature_rows)
    minimum, median = chart_augmentation_similarity(feature_rows)
    write_readme(inventory, scores, minimum, median)
    print(f"README: {DATA / 'README.md'}")
    print(f"Charts: {ASSETS}")


if __name__ == "__main__":
    main()
