"""Test the unchanged RBF-SVM pipeline on data from 2026-10-28 and 2026-10-30.

Eligible human sessions are evaluated by leave-one-session-out. Ambient-air,
coffee-only and paired-protocol sessions are shown but excluded from accuracy.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
from html import escape
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_coffee_odor as detector


DEFAULT_OUTPUT = ROOT / "BAO_CAO_SVM_TRAIN_TEST_2026_10_28_30.md"
ASSET_DIR = ROOT / "data" / "svm_2026_10_28_30_report_assets"
DECISIVE = {"COFFEE_ODOR_LIKELY", "NO_COFFEE_ODOR_LIKELY"}
ABSTAIN = {"UNCERTAIN", "OUT_OF_DOMAIN", "INVALID_MEASUREMENT"}


def parse_label(value: object) -> int | None:
    text = str(value).strip()
    return int(text) if text in {"0", "1"} else None


def rows_2026_10_28(data_root: Path) -> list[dict[str, object]]:
    day_root = data_root / "2026-10-28"
    with (day_root / "label_manifest.csv").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        manifest = list(csv.DictReader(handle))
    rows = []
    for row in manifest:
        label = parse_label(row.get("coffee_on_person_label"))
        eligible = row.get("binary_use") == "ELIGIBLE" and label is not None
        rows.append(
            {
                "day": "2026-10-28",
                "session_no": int(row["session_no"]),
                "folder": row["folder"],
                "raw_path": day_root / row["folder"] / "raw.csv",
                "group": row.get("experiment_group") or "UNKNOWN",
                "label": label if eligible else None,
                "eligible": eligible,
            }
        )
    return rows


def classify_day30_folder(name: str) -> tuple[str, int | None, bool]:
    lowered = name.lower()
    if lowered.startswith("duongcaphe2_"):
        return "HUMAN_COFFEE", 1, True
    if lowered.startswith(("duong_", "dat_")):
        return "HUMAN_ONLY", 0, True
    if lowered.startswith(("caphe1_", "caphe2_")):
        return "COFFEE_ONLY", None, False
    if lowered.startswith("khongkhi_"):
        return "AIR", None, False
    return "UNKNOWN", None, False


def rows_2026_10_30(data_root: Path) -> list[dict[str, object]]:
    day_root = data_root / "2026-10-30"
    rows = []
    for session_no, directory in enumerate(sorted(day_root.iterdir()), start=1):
        raw_path = directory / "raw.csv"
        if not directory.is_dir() or not raw_path.is_file():
            continue
        group, label, eligible = classify_day30_folder(directory.name)
        rows.append(
            {
                "day": "2026-10-30",
                "session_no": session_no,
                "folder": directory.name,
                "raw_path": raw_path,
                "group": group,
                "label": label,
                "eligible": eligible,
            }
        )
    return rows


def evaluate(prediction: str, label: int | None, eligible: bool) -> str:
    if not eligible or label is None:
        return "OUT_OF_SCOPE"
    if prediction in ABSTAIN:
        return "ABSTAIN"
    predicted_label = int(prediction == "COFFEE_ODOR_LIKELY")
    return "CORRECT" if predicted_label == label else "WRONG"


def rejection_reason(result: dict[str, object]) -> str:
    prediction = str(result["prediction"])
    if prediction == "OUT_OF_DOMAIN":
        distance = result.get("nearest_training_distance")
        threshold = result.get("ood_threshold")
        max_abs_z = result.get("max_abs_z")
        details = []
        if distance is not None and threshold is not None:
            details.append(f"distance {float(distance):.2f} > ngưỡng {float(threshold):.2f}")
        if max_abs_z is not None and float(max_abs_z) > 5.0:
            details.append(f"max |z| = {float(max_abs_z):.2f} > 5")
        suffix = "; ".join(details) if details else "đặc trưng nằm ngoài miền train"
        return f"Ngoài miền học: {suffix}"
    if prediction != "UNCERTAIN":
        return "–"
    main_score = float(result["decision_score"])
    mq_score = float(result["focused_mq135_mq3_score"])
    if (main_score < 0 <= mq_score) or (mq_score < 0 <= main_score):
        return "Main và MQ trái dấu, hai mô hình không đồng thuận"
    missing = []
    if main_score < detector.BROAD_POSITIVE_GATE:
        missing.append(
            f"Main {main_score:+.3f} < {detector.BROAD_POSITIVE_GATE:.2f}"
        )
    if mq_score < detector.FOCUSED_POSITIVE_GATE:
        missing.append(
            f"MQ {mq_score:+.3f} < {detector.FOCUSED_POSITIVE_GATE:.2f}"
        )
    return "Bằng chứng CÓ chưa đủ: " + "; ".join(missing)


def test_sessions(data_root: Path) -> list[dict[str, object]]:
    source_rows = rows_2026_10_28(data_root) + rows_2026_10_30(data_root)
    tested = []
    for row in source_rows:
        result = detector.predict(Path(row["raw_path"]), data_root)
        prediction = str(result["prediction"])
        tested.append(
            {
                **row,
                "prediction": prediction,
                "evaluation": evaluate(
                    prediction, row["label"], bool(row["eligible"])
                ),
                "main_score": result.get("decision_score"),
                "mq_score": result.get("focused_mq135_mq3_score"),
                "out_of_distribution": result.get("out_of_distribution"),
                "quality_pass": result.get("quality", {}).get("passed"),
                "rejection_reason": rejection_reason(result),
            }
        )
    return tested


def summarize(rows: list[dict[str, object]]) -> dict[str, object]:
    eligible = [row for row in rows if row["eligible"]]
    decisive = [row for row in eligible if row["prediction"] in DECISIVE]
    correct = sum(row["evaluation"] == "CORRECT" for row in eligible)
    positives = [row for row in eligible if row["label"] == 1]
    negatives = [row for row in eligible if row["label"] == 0]
    return {
        "total": len(rows),
        "eligible": len(eligible),
        "out_of_scope": len(rows) - len(eligible),
        "negative": len(negatives),
        "positive": len(positives),
        "decisive": len(decisive),
        "correct": correct,
        "wrong": sum(row["evaluation"] == "WRONG" for row in eligible),
        "abstained": len(eligible) - len(decisive),
        "coverage": len(decisive) / len(eligible),
        "accuracy_when_decisive": correct / len(decisive) if decisive else None,
        "correct_over_all": correct / len(eligible),
        "positive_detected": sum(
            row["prediction"] == "COFFEE_ODOR_LIKELY" for row in positives
        ),
        "positive_missed": sum(
            row["prediction"] == "NO_COFFEE_ODOR_LIKELY" for row in positives
        ),
        "positive_abstained": sum(row["prediction"] in ABSTAIN for row in positives),
        "negative_false_positive": sum(
            row["prediction"] == "COFFEE_ODOR_LIKELY" for row in negatives
        ),
    }


def format_number(value: object) -> str:
    return "–" if value is None else f"{float(value):+.3f}"


def format_percent(value: object) -> str:
    return "–" if value is None else f"{float(value):.1%}"


def result_table(rows: list[dict[str, object]]) -> list[str]:
    lines = [
        "| Ngày | STT | Nhãn | Main | MQ | Kết quả | Đánh giá | Nhóm | Folder |",
        "|---|---:|:---:|---:|---:|---|---|---|---|",
    ]
    for row in rows:
        label = "–" if row["label"] is None else str(row["label"])
        lines.append(
            "| {day} | {session_no} | {label} | {main} | {mq} | `{prediction}` | "
            "**{evaluation}** | {group} | `{folder}` |".format(
                day=row["day"],
                session_no=row["session_no"],
                label=label,
                main=format_number(row["main_score"]),
                mq=format_number(row["mq_score"]),
                prediction=row["prediction"],
                evaluation=row["evaluation"],
                group=row["group"],
                folder=row["folder"],
            )
        )
    return lines


def day_summary_table(rows: list[dict[str, object]]) -> list[str]:
    lines = [
        "| Ngày | Eligible | Âm | Dương | Kết luận | Đúng | Sai | Từ chối | Coverage | Accuracy khi kết luận |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for day in ("2026-10-28", "2026-10-30"):
        summary = summarize([row for row in rows if row["day"] == day])
        lines.append(
            f"| {day} | {summary['eligible']} | {summary['negative']} | "
            f"{summary['positive']} | {summary['decisive']} | {summary['correct']} | "
            f"{summary['wrong']} | {summary['abstained']} | "
            f"{format_percent(summary['coverage'])} | "
            f"{format_percent(summary['accuracy_when_decisive'])} |"
        )
    return lines


def svg_text(
    x: float,
    y: float,
    value: object,
    size: int = 14,
    anchor: str = "start",
    weight: str = "normal",
    color: str = "#172033",
    rotate: int | None = None,
) -> str:
    transform = f' transform="rotate({rotate} {x} {y})"' if rotate is not None else ""
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-family="Arial, sans-serif" '
        f'font-size="{size}" text-anchor="{anchor}" font-weight="{weight}" '
        f'fill="{color}"{transform}>{escape(str(value))}</text>'
    )


def write_svg(path: Path, width: int, height: int, elements: list[str]) -> None:
    content = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        *elements,
        "</svg>",
    ]
    path.write_text("\n".join(content), encoding="utf-8")


def plot_score_map(rows: list[dict[str, object]], path: Path) -> None:
    eligible = [row for row in rows if row["eligible"]]
    x_values = [float(row["main_score"]) for row in eligible]
    y_values = [float(row["mq_score"]) for row in eligible]
    x_min, x_max = min(-1.6, min(x_values) - 0.18), max(1.1, max(x_values) + 0.18)
    y_min, y_max = min(-2.5, min(y_values) - 0.2), max(2.0, max(y_values) + 0.2)
    width, height = 1120, 720
    left, right, top, bottom = 105, 1060, 76, 630

    def sx(value: float) -> float:
        return left + (value - x_min) / (x_max - x_min) * (right - left)

    def sy(value: float) -> float:
        return bottom - (value - y_min) / (y_max - y_min) * (bottom - top)

    elements = [svg_text(width / 2, 38, "Bản đồ score SVM – 15 mẫu eligible của hai ngày", 23, "middle", "bold")]
    elements.extend(
        [
            f'<rect x="{sx(x_min):.1f}" y="{sy(0):.1f}" width="{sx(0)-sx(x_min):.1f}" height="{sy(y_min)-sy(0):.1f}" fill="#dcecf8"/>',
            f'<rect x="{sx(detector.BROAD_POSITIVE_GATE):.1f}" y="{sy(y_max):.1f}" width="{sx(x_max)-sx(detector.BROAD_POSITIVE_GATE):.1f}" height="{sy(detector.FOCUSED_POSITIVE_GATE)-sy(y_max):.1f}" fill="#dff3e8"/>',
            f'<rect x="{left}" y="{top}" width="{right-left}" height="{bottom-top}" fill="none" stroke="#aab5c3"/>',
        ]
    )
    for value in (-1.5, -1.0, -0.5, 0, 0.25, 0.5, 1.0):
        if x_min <= value <= x_max:
            x = sx(value)
            elements.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{bottom}" stroke="#d7dee8"/>')
            elements.append(svg_text(x, bottom + 24, f"{value:g}", 12, "middle"))
    for value in (-2.0, -1.5, -1.0, -0.5, 0, 0.6, 1.0, 1.5, 2.0):
        if y_min <= value <= y_max:
            y = sy(value)
            elements.append(f'<line x1="{left}" y1="{y:.1f}" x2="{right}" y2="{y:.1f}" stroke="#d7dee8"/>')
            elements.append(svg_text(left - 12, y + 4, f"{value:g}", 12, "end"))
    elements.extend(
        [
            f'<line x1="{sx(0):.1f}" y1="{top}" x2="{sx(0):.1f}" y2="{bottom}" stroke="#4b5563" stroke-width="1.5"/>',
            f'<line x1="{left}" y1="{sy(0):.1f}" x2="{right}" y2="{sy(0):.1f}" stroke="#4b5563" stroke-width="1.5"/>',
            f'<line x1="{sx(detector.BROAD_POSITIVE_GATE):.1f}" y1="{top}" x2="{sx(detector.BROAD_POSITIVE_GATE):.1f}" y2="{bottom}" stroke="#dc6674" stroke-dasharray="7 6"/>',
            f'<line x1="{left}" y1="{sy(detector.FOCUSED_POSITIVE_GATE):.1f}" x2="{right}" y2="{sy(detector.FOCUSED_POSITIVE_GATE):.1f}" stroke="#dc6674" stroke-dasharray="7 6"/>',
            svg_text(left + 10, bottom - 12, "Vùng kết luận KHÔNG", 13, "start", "bold", "#2878b5"),
            svg_text(right - 10, top + 22, "Vùng kết luận CÓ", 13, "end", "bold", "#218c5a"),
        ]
    )
    for row in eligible:
        color = "#d1495b" if row["label"] == 1 else "#2878b5"
        x, y = sx(float(row["main_score"])), sy(float(row["mq_score"]))
        if row["prediction"] == "OUT_OF_DOMAIN":
            elements.extend(
                [
                    f'<line x1="{x-7:.1f}" y1="{y-7:.1f}" x2="{x+7:.1f}" y2="{y+7:.1f}" stroke="{color}" stroke-width="4"/>',
                    f'<line x1="{x-7:.1f}" y1="{y+7:.1f}" x2="{x+7:.1f}" y2="{y-7:.1f}" stroke="{color}" stroke-width="4"/>',
                ]
            )
        elif row["day"] == "2026-10-28":
            elements.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="8" fill="{color}" stroke="white" stroke-width="2"/>')
        else:
            elements.append(f'<rect x="{x-8:.1f}" y="{y-8:.1f}" width="16" height="16" rx="2" fill="{color}" stroke="white" stroke-width="2"/>')
        short_day = "28" if row["day"] == "2026-10-28" else "30"
        elements.append(svg_text(x + 10, y - 9, f"{short_day}-#{row['session_no']}", 11, "start", "bold", color))
    elements.extend(
        [
            svg_text((left + right) / 2, 684, "Main RBF-SVM score", 15, "middle", "bold"),
            svg_text(30, (top + bottom) / 2, "MQ135/MQ3 RBF-SVM score", 15, "middle", "bold", rotate=-90),
            svg_text(right, 662, "○ 28/10   □ 30/10   × ngoài miền   Xanh: nhãn 0   Đỏ: nhãn 1", 12, "end"),
        ]
    )
    write_svg(path, width, height, elements)


def plot_decision_matrix(rows: list[dict[str, object]], path: Path) -> None:
    eligible = [row for row in rows if row["eligible"]]
    matrix = [[0, 0, 0], [0, 0, 0]]
    for row in eligible:
        column = 0 if row["prediction"] == "NO_COFFEE_ODOR_LIKELY" else 2 if row["prediction"] == "COFFEE_ODOR_LIKELY" else 1
        matrix[int(row["label"])][column] += 1
    width, height = 900, 470
    left, top, cell_w, cell_h = 250, 115, 185, 115
    maximum = max(max(values) for values in matrix) or 1
    elements = [svg_text(width / 2, 40, "Ma trận quyết định có tính trạng thái từ chối", 23, "middle", "bold")]
    columns = ["Kết luận KHÔNG", "Từ chối", "Kết luận CÓ"]
    rows_labels = ["Nhãn 0 – không cà phê", "Nhãn 1 – có cà phê"]
    for column, label in enumerate(columns):
        elements.append(svg_text(left + column * cell_w + cell_w / 2, 88, label, 13, "middle", "bold"))
    for row_index, label in enumerate(rows_labels):
        elements.append(svg_text(left - 14, top + row_index * cell_h + cell_h / 2 + 5, label, 13, "end", "bold"))
        total = sum(matrix[row_index])
        for column_index, count in enumerate(matrix[row_index]):
            intensity = count / maximum
            blue = int(245 - 115 * intensity)
            fill = f"rgb({blue},{blue + 5},{min(255, blue + 35)})"
            x, y = left + column_index * cell_w, top + row_index * cell_h
            elements.append(f'<rect x="{x}" y="{y}" width="{cell_w}" height="{cell_h}" fill="{fill}" stroke="white" stroke-width="3"/>')
            elements.append(svg_text(x + cell_w / 2, y + 50, count, 25, "middle", "bold", "#13233a"))
            elements.append(svg_text(x + cell_w / 2, y + 78, f"{count / total:.1%}", 14, "middle", "normal", "#13233a"))
    elements.append(svg_text(left + 1.5 * cell_w, 405, "Quyết định của pipeline", 15, "middle", "bold"))
    write_svg(path, width, height, elements)


def plot_outcomes_by_day(rows: list[dict[str, object]], path: Path) -> None:
    days = ["2026-10-28", "2026-10-30"]
    categories = [("CORRECT", "Đúng", "#2ca25f"), ("WRONG", "Sai", "#d1495b"), ("ABSTAIN", "Từ chối", "#e3a82b")]
    width, height = 860, 520
    top, bottom, bar_w = 80, 430, 155
    centers = [300, 590]
    maximum = max(sum(row["eligible"] and row["day"] == day for row in rows) for day in days)
    elements = [svg_text(width / 2, 38, "Đúng, sai và từ chối theo ngày", 23, "middle", "bold")]
    for tick in range(0, maximum + 1, 2):
        y = bottom - tick / (maximum + 1) * (bottom - top)
        elements.append(f'<line x1="110" y1="{y:.1f}" x2="785" y2="{y:.1f}" stroke="#d7dee8"/>')
        elements.append(svg_text(96, y + 4, tick, 12, "end"))
    for index, day in enumerate(days):
        y_bottom = bottom
        for category, label, color in categories:
            count = sum(row["eligible"] and row["day"] == day and row["evaluation"] == category for row in rows)
            segment_h = count / (maximum + 1) * (bottom - top)
            y_top = y_bottom - segment_h
            if count:
                elements.append(f'<rect x="{centers[index]-bar_w/2:.1f}" y="{y_top:.1f}" width="{bar_w}" height="{segment_h:.1f}" fill="{color}"/>')
                elements.append(svg_text(centers[index], y_top + segment_h / 2 + 5, count, 17, "middle", "bold", "white"))
            y_bottom = y_top
        total = sum(row["eligible"] and row["day"] == day for row in rows)
        elements.append(svg_text(centers[index], 460, day[-5:], 15, "middle", "bold"))
        elements.append(svg_text(centers[index], 481, f"{total} eligible", 12, "middle"))
    legend_x = 175
    for _, label, color in categories:
        elements.append(f'<rect x="{legend_x}" y="62" width="14" height="14" fill="{color}"/>')
        elements.append(svg_text(legend_x + 20, 74, label, 12))
        legend_x += 145
    elements.append(svg_text(34, (top + bottom) / 2, "Số phiên", 15, "middle", "bold", rotate=-90))
    write_svg(path, width, height, elements)


def generate_charts(rows: list[dict[str, object]]) -> dict[str, Path]:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    paths = {
        "score_map": ASSET_DIR / "01_ban_do_score_svm.svg",
        "decision_matrix": ASSET_DIR / "02_ma_tran_quyet_dinh.svg",
        "outcomes_by_day": ASSET_DIR / "03_ket_qua_theo_ngay.svg",
    }
    plot_score_map(rows, paths["score_map"])
    plot_decision_matrix(rows, paths["decision_matrix"])
    plot_outcomes_by_day(rows, paths["outcomes_by_day"])
    return paths


def markdown_path(path: Path, report_path: Path) -> str:
    return Path(os.path.relpath(path, report_path.parent)).as_posix()


def rejection_table(rows: list[dict[str, object]]) -> list[str]:
    rejected = [
        row for row in rows if row["eligible"] and row["prediction"] in ABSTAIN
    ]
    lines = [
        "| Ngày–STT | Nhãn | Main | MQ | Trạng thái | Lý do trực tiếp |",
        "|---|:---:|---:|---:|---|---|",
    ]
    for row in rejected:
        lines.append(
            f"| {str(row['day'])[-5:]}–#{row['session_no']} | {row['label']} | "
            f"{format_number(row['main_score'])} | {format_number(row['mq_score'])} | "
            f"`{row['prediction']}` | {row['rejection_reason']} |"
        )
    return lines


def generate_report(
    data_root: Path,
    rows: list[dict[str, object]] | None = None,
    self_test: dict[str, object] | None = None,
    report_path: Path = DEFAULT_OUTPUT,
) -> str:
    rows = test_sessions(data_root) if rows is None else rows
    summary = summarize(rows)
    self_test = detector.self_test(data_root) if self_test is None else self_test
    chart_paths = generate_charts(rows)
    score_chart = markdown_path(chart_paths["score_map"], report_path)
    matrix_chart = markdown_path(chart_paths["decision_matrix"], report_path)
    day_chart = markdown_path(chart_paths["outcomes_by_day"], report_path)
    loo = self_test["loo"]
    lines = [
        "# Báo cáo SVM train/test trên dữ liệu 2026-10-28 và 2026-10-30",
        "",
        f"> Tạo lúc: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## 1. Phạm vi thay đổi",
        "",
        "Pipeline xử lý được giữ nguyên: 25 đặc trưng chuẩn hóa theo baseline, "
        "`StandardScaler`, RBF-SVM chính và RBF-SVM phụ MQ135-1/MQ3-1, cùng các "
        "ngưỡng quyết định cũ. Thay đổi duy nhất về mô hình là nguồn phiên dùng "
        "để train và test.",
        "",
        "- Train pool: các phiên người có nhãn trong `data/2026-10-28` và "
        "`data/2026-10-30`.",
        f"- Tổng tập học: **{self_test['sessions']} phiên**, gồm "
        f"**{self_test['negative']} âm** và **{self_test['positive']} dương**.",
        "- Ngày 30/10: `Duong`, `Dat` được gán nhãn 0; `DuongCaphe2` được gán "
        "nhãn 1 theo tên phiên đã đánh nhãn.",
        "- `Caphe1`, `Caphe2`, `khongkhi` và các protocol ngoài bài toán người "
        "mang mùi cà phê chỉ được hiển thị, không tính accuracy.",
        "",
        "## 2. Cách kiểm thử",
        "",
        "Vì người dùng yêu cầu test lại chính hai ngày dùng để xây dựng tập học, "
        "mỗi phiên eligible được kiểm tra bằng **leave-one-session-out**: loại phiên "
        "đang test khỏi train, train trên 14 phiên còn lại rồi mới dự đoán. Cách này "
        "tránh việc một file vừa nằm trong train vừa nằm trong test của chính nó.",
        "",
        "Ngoài ra, báo cáo giữ kết quả **holdout theo ngày**: train trên một ngày "
        "và test toàn bộ ngày còn lại.",
        "",
        "## 3. Kết quả tổng hợp LOOCV",
        "",
        f"- Raw balanced accuracy tại dấu score 0: **{loo['raw_balanced_accuracy']:.1%}**.",
        f"- Raw sensitivity: **{loo['raw_sensitivity']:.1%}**; raw specificity: "
        f"**{loo['raw_specificity']:.1%}**.",
        f"- Coverage sau vùng từ chối: **{summary['coverage']:.1%}** "
        f"({summary['decisive']}/{summary['eligible']}).",
        f"- Accuracy khi mô hình đưa ra kết luận: "
        f"**{format_percent(summary['accuracy_when_decisive'])}** "
        f"({summary['correct']}/{summary['decisive']}).",
        f"- Tỷ lệ đúng trên toàn bộ eligible, tính cả từ chối: "
        f"**{summary['correct_over_all']:.1%}**.",
        f"- Mẫu có cà phê: phát hiện **{summary['positive_detected']}/{summary['positive']}**, "
        f"nhầm thành không cà phê **{summary['positive_missed']}**, "
        f"từ chối **{summary['positive_abstained']}**.",
        f"- Mẫu không cà phê bị báo nhầm có cà phê: "
        f"**{summary['negative_false_positive']}/{summary['negative']}**.",
        "",
        "## 4. Biểu đồ kết quả SVM",
        "",
        f"![Bản đồ score SVM]({score_chart})",
        "",
        "*Hình 1. Bản đồ Main score và MQ score của 15 mẫu eligible. Hình tròn là "
        "ngày 28/10, hình vuông là ngày 30/10; màu thể hiện nhãn thật.*",
        "",
        "Vùng xanh lá chỉ được kết luận có cà phê khi **Main ≥ 0,25 và MQ ≥ "
        "0,60**. Vùng xanh dương được kết luận không cà phê khi **Main < 0 và "
        "MQ < 0**. Mọi vùng còn lại là vùng hai mô hình mâu thuẫn hoặc bằng chứng "
        "chưa đủ mạnh, vì vậy pipeline trả về `UNCERTAIN`.",
        "",
        f"![Ma trận quyết định]({matrix_chart})",
        "",
        "*Hình 2. Ma trận quyết định gồm ba cột: không cà phê, từ chối và có cà "
        "phê. Tỷ lệ được tính riêng trong từng nhãn thật.*",
        "",
        f"![Kết quả theo ngày]({day_chart})",
        "",
        "*Hình 3. Số phiên đúng, sai và bị từ chối theo ngày.*",
        "",
        "Ngày 30/10 không có kết luận dứt khoát trong LOOCV: cả bốn phiên người "
        "đều rơi vào vùng bất đồng, bằng chứng yếu hoặc ngoài miền học. Đây là dấu "
        "hiệu rõ của batch effect giữa hai ngày.",
        "",
        "## 5. Vì sao các mẫu bị từ chối?",
        "",
        "`UNCERTAIN` không có nghĩa là file lỗi. Nó có nghĩa score chưa đồng thời "
        "thỏa một trong hai luật kết luận. `OUT_OF_DOMAIN` xảy ra trước bước áp "
        "ngưỡng khi vector 25 đặc trưng quá xa các phiên train còn lại.",
        "",
        *rejection_table(rows),
        "",
        "## 6. Kết quả theo ngày",
        "",
        *day_summary_table(rows),
        "",
        "## 7. Holdout chéo theo ngày",
        "",
        "| Ngày test | Raw balanced accuracy | Sensitivity | Specificity | Coverage | Accuracy khi kết luận |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for day, details in self_test["day_holdouts"].items():
        evaluation = details["evaluation"]
        lines.append(
            f"| {day} | {format_percent(evaluation['raw_balanced_accuracy'])} | "
            f"{format_percent(evaluation['raw_sensitivity'])} | "
            f"{format_percent(evaluation['raw_specificity'])} | "
            f"{format_percent(evaluation['abstention_coverage'])} | "
            f"{format_percent(evaluation['accuracy_when_decisive'])} |"
        )
    lines.extend(
        [
            "",
            "## 8. Chi tiết toàn bộ phiên của hai ngày",
            "",
            *result_table(rows),
            "",
            "## 9. Nhận xét",
            "",
            "- Việc thêm ngày 30/10 làm tập dương tăng từ 4 lên 6 phiên và giúp "
            "đánh giá được khả năng chuyển ngày, nhưng tổng dữ liệu vẫn rất nhỏ.",
            "- LOOCV raw balanced accuracy phản ánh khả năng phân lớp trước khi áp "
            "dụng vùng từ chối; chỉ số accuracy khi kết luận phản ánh pipeline hoàn chỉnh.",
            "- Các phiên `UNCERTAIN` không phải kết luận sai mà là mô hình chưa đủ "
            "đồng thuận giữa score tổng và score MQ để đưa ra nhãn chắc chắn.",
            "- Kết quả trên coffee-only và ambient-air không được dùng để tuyên bố "
            "accuracy của bài toán phát hiện cà phê trên người.",
            "- Holdout theo ngày là kiểm tra khó hơn LOOCV và đáng tin hơn để đánh giá "
            "batch effect, nhưng ngày 30/10 mới chỉ có bốn phiên người.",
            "",
            "## 10. Khả năng tái lập",
            "",
            f"- Model version: `{self_test['model_version']}`",
            f"- Feature version: `{self_test['feature_version']}`",
            f"- Training manifest hash: `{self_test['training_manifest_hash']}`",
            "- Lệnh chạy: `.\\.venv\\Scripts\\python.exe "
            "analysis\\report_svm_2026_10_28_30.py`",
            "",
        ]
    )
    return "\n".join(lines)


def print_terminal_report(rows: list[dict[str, object]]) -> None:
    summary = summarize(rows)
    print("=" * 126)
    print("BATCH TEST SVM – TẤT CẢ MẪU 2026-10-28 VÀ 2026-10-30")
    print("=" * 126)
    print(
        "Ngày  | STT | Nhãn | Main   | MQ     | Kết quả                  | "
        "Đánh giá     | Nhóm          | Folder"
    )
    for row in rows:
        label = "-" if row["label"] is None else str(row["label"])
        print(
            f"{str(row['day'])[-5:]:>5} | {int(row['session_no']):>3} | "
            f"{label:^4} | {format_number(row['main_score']):>6} | "
            f"{format_number(row['mq_score']):>6} | "
            f"{str(row['prediction']):<24} | {str(row['evaluation']):<12} | "
            f"{str(row['group']):<13} | {row['folder']}"
        )
    print("\nTHỐNG KÊ TRÊN CÁC MẪU ELIGIBLE CÓ NHÃN 0/1")
    print(
        f"  Tổng {summary['eligible']}; kết luận {summary['decisive']}; "
        f"đúng {summary['correct']}; sai {summary['wrong']}; "
        f"từ chối {summary['abstained']}"
    )
    print(
        f"  Coverage: {summary['coverage']:.1%}; accuracy khi có kết luận: "
        f"{format_percent(summary['accuracy_when_decisive'])}; "
        f"đúng trên toàn bộ eligible: {summary['correct_over_all']:.1%}"
    )
    print(
        f"  Có cà phê: phát hiện {summary['positive_detected']}/{summary['positive']}; "
        f"kết luận nhầm KHÔNG {summary['positive_missed']}; "
        f"từ chối {summary['positive_abstained']}"
    )
    print(
        f"  Không cà phê: {summary['negative_false_positive']} false positive / "
        f"{summary['negative']} mẫu"
    )
    print(f"  Ngoài phạm vi accuracy: {summary['out_of_scope']} phiên")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Xuất báo cáo Markdown SVM cho dữ liệu 28/10 và 30/10."
    )
    parser.add_argument("--data-root", type=Path, default=detector.DATA_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = test_sessions(args.data_root)
    self_test = detector.self_test(args.data_root)
    report = generate_report(args.data_root, rows, self_test, args.output)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    print_terminal_report(rows)
    print(f"\nĐã ghi báo cáo Markdown: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
