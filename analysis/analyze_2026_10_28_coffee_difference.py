"""Compare sessions with and without coffee in the 2026-10-28 dataset.

The primary analysis is restricted to Tai so that person identity is not mixed with
coffee status.  The implementation uses only the Python standard library because
the repository's report generators are intentionally dependency-free.
"""

from __future__ import annotations

from collections import defaultdict
import csv
import importlib.util
import itertools
import math
from pathlib import Path
import statistics
import sys


ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data" / "2026-10-28"
OUTPUT_ROOT = DATA_ROOT / "coffee_difference_analysis"
MANIFEST_PATH = DATA_ROOT / "label_manifest.csv"
SOURCE_REPORT = Path(__file__).with_name("generate_2026_10_28_report.py")

SENSOR_ORDER = ("bme", "mq135_1", "mq3_1", "mq135_2", "mq3_2")
SENSOR_LABELS = {
    "bme": "BME688 gas",
    "mq135_1": "MQ135-1",
    "mq3_1": "MQ3-1",
    "mq135_2": "MQ135-2",
    "mq3_2": "MQ3-2",
}
FEATURE_SPECS = (
    ("exposure_mean", "mean EXP", 1.0, "%"),
    ("slope_pct_per_s", "slope EXP", 60.0, "%/min"),
    ("recovery_end", "end REC", 1.0, "%"),
)


def load_report_module():
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("report_2026_10_28", SOURCE_REPORT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {SOURCE_REPORT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def mean(values: list[float]) -> float:
    return statistics.fmean(values)


def sample_sd(values: list[float]) -> float:
    return statistics.stdev(values) if len(values) > 1 else 0.0


def hedges_g(group_zero: list[float], group_one: list[float]) -> float:
    n_zero = len(group_zero)
    n_one = len(group_one)
    denominator_df = n_zero + n_one - 2
    pooled_variance = (
        (n_zero - 1) * sample_sd(group_zero) ** 2
        + (n_one - 1) * sample_sd(group_one) ** 2
    ) / denominator_df
    if pooled_variance <= 0:
        return 0.0
    cohens_d = (mean(group_one) - mean(group_zero)) / math.sqrt(pooled_variance)
    correction = 1 - 3 / (4 * (n_zero + n_one) - 9)
    return correction * cohens_d


def cliffs_delta(group_zero: list[float], group_one: list[float]) -> float:
    comparisons = [
        (one > zero) - (one < zero) for one in group_one for zero in group_zero
    ]
    return mean([float(value) for value in comparisons])


def exact_permutation_p(values: list[float], labels: list[int]) -> float:
    positive_count = sum(labels)
    observed = abs(
        mean([value for value, label in zip(values, labels) if label == 1])
        - mean([value for value, label in zip(values, labels) if label == 0])
    )
    extreme = 0
    total = 0
    indices = range(len(values))
    for positive_indices in itertools.combinations(indices, positive_count):
        positive_set = set(positive_indices)
        positive = [values[index] for index in indices if index in positive_set]
        negative = [values[index] for index in indices if index not in positive_set]
        difference = abs(mean(positive) - mean(negative))
        extreme += difference >= observed - 1e-12
        total += 1
    return extreme / total


def benjamini_hochberg(rows: list[dict[str, object]]) -> None:
    ordered = sorted(enumerate(rows), key=lambda item: float(item[1]["p_exact"]))
    adjusted = [1.0] * len(rows)
    running = 1.0
    for rank_index in range(len(ordered) - 1, -1, -1):
        original_index, row = ordered[rank_index]
        rank = rank_index + 1
        running = min(running, float(row["p_exact"]) * len(rows) / rank)
        adjusted[original_index] = min(running, 1.0)
    for row, q_value in zip(rows, adjusted):
        row["q_bh"] = q_value


def jacobi_eigen(matrix: list[list[float]]) -> tuple[list[float], list[list[float]]]:
    size = len(matrix)
    work = [row[:] for row in matrix]
    vectors = [[float(row == column) for column in range(size)] for row in range(size)]
    for _ in range(100 * size * size):
        pivot_row = 0
        pivot_column = 1 if size > 1 else 0
        maximum = 0.0
        for row in range(size):
            for column in range(row + 1, size):
                value = abs(work[row][column])
                if value > maximum:
                    maximum = value
                    pivot_row, pivot_column = row, column
        if maximum < 1e-12:
            break
        left = work[pivot_row][pivot_row]
        right = work[pivot_column][pivot_column]
        cross = work[pivot_row][pivot_column]
        angle = 0.5 * math.atan2(2 * cross, right - left)
        cosine = math.cos(angle)
        sine = math.sin(angle)
        for index in range(size):
            if index in {pivot_row, pivot_column}:
                continue
            row_value = work[index][pivot_row]
            column_value = work[index][pivot_column]
            work[index][pivot_row] = work[pivot_row][index] = (
                cosine * row_value - sine * column_value
            )
            work[index][pivot_column] = work[pivot_column][index] = (
                sine * row_value + cosine * column_value
            )
        work[pivot_row][pivot_row] = (
            cosine * cosine * left
            - 2 * sine * cosine * cross
            + sine * sine * right
        )
        work[pivot_column][pivot_column] = (
            sine * sine * left
            + 2 * sine * cosine * cross
            + cosine * cosine * right
        )
        work[pivot_row][pivot_column] = work[pivot_column][pivot_row] = 0.0
        for index in range(size):
            vector_row = vectors[index][pivot_row]
            vector_column = vectors[index][pivot_column]
            vectors[index][pivot_row] = cosine * vector_row - sine * vector_column
            vectors[index][pivot_column] = sine * vector_row + cosine * vector_column
    eigenvalues = [work[index][index] for index in range(size)]
    order = sorted(range(size), key=lambda index: eigenvalues[index], reverse=True)
    return (
        [eigenvalues[index] for index in order],
        [[vectors[row][index] for index in order] for row in range(size)],
    )


def standardize(matrix: list[list[float]]) -> tuple[list[list[float]], list[float], list[float]]:
    columns = list(zip(*matrix))
    centers = [mean(list(column)) for column in columns]
    scales = [sample_sd(list(column)) or 1.0 for column in columns]
    standardized = [
        [(value - centers[index]) / scales[index] for index, value in enumerate(row)]
        for row in matrix
    ]
    return standardized, centers, scales


def pca(matrix: list[list[float]]) -> tuple[list[list[float]], list[float], list[list[float]]]:
    standardized, _, _ = standardize(matrix)
    row_count = len(standardized)
    column_count = len(standardized[0])
    covariance = [
        [
            sum(standardized[row][left] * standardized[row][right] for row in range(row_count))
            / (row_count - 1)
            for right in range(column_count)
        ]
        for left in range(column_count)
    ]
    eigenvalues, eigenvectors = jacobi_eigen(covariance)
    eigenvalues = [max(value, 0.0) for value in eigenvalues]
    total = sum(eigenvalues) or 1.0
    explained = [value / total for value in eigenvalues]
    scores = [
        [
            sum(row[feature] * eigenvectors[feature][component] for feature in range(column_count))
            for component in range(column_count)
        ]
        for row in standardized
    ]
    return scores, explained, eigenvectors


def balanced_accuracy(truth: list[int], predicted: list[int]) -> float:
    recalls = []
    for label in (0, 1):
        relevant = [index for index, value in enumerate(truth) if value == label]
        recalls.append(
            sum(predicted[index] == label for index in relevant) / len(relevant)
        )
    return mean(recalls)


def loocv_nearest_centroid(matrix: list[list[float]], labels: list[int]) -> float:
    predictions = []
    for test_index in range(len(matrix)):
        train_indices = [index for index in range(len(matrix)) if index != test_index]
        train = [matrix[index] for index in train_indices]
        train_labels = [labels[index] for index in train_indices]
        train_standardized, centers, scales = standardize(train)
        effect_scores = []
        for feature_index in range(len(matrix[0])):
            group_zero = [
                row[feature_index]
                for row, label in zip(train_standardized, train_labels)
                if label == 0
            ]
            group_one = [
                row[feature_index]
                for row, label in zip(train_standardized, train_labels)
                if label == 1
            ]
            effect_scores.append(abs(mean(group_one) - mean(group_zero)))
        selected = sorted(
            range(len(effect_scores)), key=effect_scores.__getitem__, reverse=True
        )[:2]
        centroids = {
            label: [
                mean(
                    [
                        row[feature]
                        for row, train_label in zip(train_standardized, train_labels)
                        if train_label == label
                    ]
                )
                for feature in selected
            ]
            for label in (0, 1)
        }
        test = [
            (matrix[test_index][feature] - centers[feature]) / scales[feature]
            for feature in selected
        ]
        distances = {
            label: sum(
                (value - centroid) ** 2
                for value, centroid in zip(test, centroids[label])
            )
            for label in (0, 1)
        }
        predictions.append(min(distances, key=distances.get))
    return balanced_accuracy(labels, predictions)


def classifier_permutation_p(matrix: list[list[float]], labels: list[int]) -> tuple[float, float]:
    observed = loocv_nearest_centroid(matrix, labels)
    positive_count = sum(labels)
    scores = []
    for positive_indices in itertools.combinations(range(len(labels)), positive_count):
        positive_set = set(positive_indices)
        permuted = [int(index in positive_set) for index in range(len(labels))]
        scores.append(loocv_nearest_centroid(matrix, permuted))
    return observed, sum(score >= observed - 1e-12 for score in scores) / len(scores)


def load_sessions() -> tuple[list[dict[str, object]], list[str]]:
    report = load_report_module()
    with MANIFEST_PATH.open(encoding="utf-8-sig", newline="") as handle:
        manifest = list(csv.DictReader(handle))
    sessions = []
    feature_names = [
        f"{sensor}__{feature}"
        for sensor in SENSOR_ORDER
        for feature, _, _, _ in FEATURE_SPECS
    ]
    for manifest_row in manifest:
        if manifest_row["binary_use"] != "ELIGIBLE":
            continue
        run = report.load_run(DATA_ROOT / manifest_row["folder"])
        features = {}
        for sensor in SENSOR_ORDER:
            for feature, _, multiplier, _ in FEATURE_SPECS:
                value = run["features"][sensor][feature]
                if value is None:
                    raise ValueError(f"Missing {sensor}/{feature} in {manifest_row['folder']}")
                features[f"{sensor}__{feature}"] = float(value) * multiplier
        sessions.append(
            {
                "session_no": int(manifest_row["session_no"]),
                "folder": manifest_row["folder"],
                "person_id": manifest_row["person_id"],
                "label": int(manifest_row["coffee_on_person_label"]),
                "started_at": manifest_row["started_at"],
                "features": features,
            }
        )
    return sessions, feature_names


def feature_label(name: str) -> str:
    sensor, feature = name.split("__", 1)
    spec = next(item for item in FEATURE_SPECS if item[0] == feature)
    return f"{SENSOR_LABELS[sensor]} – {spec[1]} ({spec[3]})"


def compare_features(
    sessions: list[dict[str, object]], feature_names: list[str]
) -> list[dict[str, object]]:
    labels = [int(session["label"]) for session in sessions]
    rows = []
    for feature_name in feature_names:
        values = [float(session["features"][feature_name]) for session in sessions]
        group_zero = [value for value, label in zip(values, labels) if label == 0]
        group_one = [value for value, label in zip(values, labels) if label == 1]
        rows.append(
            {
                "feature": feature_name,
                "feature_label": feature_label(feature_name),
                "without_coffee_mean": mean(group_zero),
                "without_coffee_sd": sample_sd(group_zero),
                "with_coffee_mean": mean(group_one),
                "with_coffee_sd": sample_sd(group_one),
                "difference": mean(group_one) - mean(group_zero),
                "hedges_g": hedges_g(group_zero, group_one),
                "cliffs_delta": cliffs_delta(group_zero, group_one),
                "p_exact": exact_permutation_p(values, labels),
            }
        )
    benjamini_hochberg(rows)
    return sorted(rows, key=lambda row: abs(float(row["hedges_g"])), reverse=True)


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def escape_xml(value: object) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def write_pca_svg(
    sessions: list[dict[str, object]], scores: list[list[float]], explained: list[float]
) -> None:
    width, height = 860, 600
    left, right, top, bottom = 95, 40, 60, 85
    plot_width = width - left - right
    plot_height = height - top - bottom
    x_values = [row[0] for row in scores]
    y_values = [row[1] for row in scores]
    x_padding = (max(x_values) - min(x_values)) * 0.12 or 1.0
    y_padding = (max(y_values) - min(y_values)) * 0.12 or 1.0
    x_min, x_max = min(x_values) - x_padding, max(x_values) + x_padding
    y_min, y_max = min(y_values) - y_padding, max(y_values) + y_padding

    def map_x(value: float) -> float:
        return left + (value - x_min) / (x_max - x_min) * plot_width

    def map_y(value: float) -> float:
        return top + (y_max - value) / (y_max - y_min) * plot_height

    elements = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<text x="430" y="30" text-anchor="middle" font-family="Arial" font-size="20" font-weight="bold">PCA – Tài có và không có cà phê</text>',
        f'<rect x="{left}" y="{top}" width="{plot_width}" height="{plot_height}" fill="#fafafa" stroke="#cccccc"/>',
    ]
    if x_min <= 0 <= x_max:
        elements.append(
            f'<line x1="{map_x(0):.1f}" y1="{top}" x2="{map_x(0):.1f}" y2="{top + plot_height}" stroke="#dddddd"/>'
        )
    if y_min <= 0 <= y_max:
        elements.append(
            f'<line x1="{left}" y1="{map_y(0):.1f}" x2="{left + plot_width}" y2="{map_y(0):.1f}" stroke="#dddddd"/>'
        )
    colors = {0: "#4c78a8", 1: "#e45756"}
    for session, score in zip(sessions, scores):
        label = int(session["label"])
        x = map_x(score[0])
        y = map_y(score[1])
        elements.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="7" fill="{colors[label]}" stroke="white" stroke-width="1.5"/>'
        )
        elements.append(
            f'<text x="{x + 10:.1f}" y="{y - 8:.1f}" font-family="Arial" font-size="11">#{session["session_no"]}</text>'
        )
    elements.extend(
        [
            f'<text x="{left + plot_width / 2}" y="{height - 30}" text-anchor="middle" font-family="Arial" font-size="14">PC1 ({explained[0] * 100:.1f}%)</text>',
            f'<text x="25" y="{top + plot_height / 2}" text-anchor="middle" transform="rotate(-90 25 {top + plot_height / 2})" font-family="Arial" font-size="14">PC2 ({explained[1] * 100:.1f}%)</text>',
            '<circle cx="590" cy="48" r="6" fill="#4c78a8"/><text x="602" y="52" font-family="Arial" font-size="12">Không cà phê</text>',
            '<circle cx="705" cy="48" r="6" fill="#e45756"/><text x="717" y="52" font-family="Arial" font-size="12">Có cà phê</text>',
            '</svg>',
        ]
    )
    (OUTPUT_ROOT / "pca_scatter.svg").write_text("\n".join(elements), encoding="utf-8")


def write_effect_svg(rows: list[dict[str, object]]) -> None:
    selected = rows[:8]
    width, height = 960, 440
    left, right, top, bottom = 360, 55, 45, 45
    plot_width = width - left - right
    limit = max(abs(float(row["hedges_g"])) for row in selected) * 1.15
    zero = left + plot_width / 2
    elements = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<text x="480" y="25" text-anchor="middle" font-family="Arial" font-size="19" font-weight="bold">Đặc trưng khác biệt mạnh nhất (Hedges g)</text>',
        f'<line x1="{zero:.1f}" y1="{top - 5}" x2="{zero:.1f}" y2="{height - bottom}" stroke="#666"/>',
    ]
    row_height = (height - top - bottom) / len(selected)
    for index, row in enumerate(selected):
        y = top + (index + 0.5) * row_height
        effect = float(row["hedges_g"])
        endpoint = zero + effect / (2 * limit) * plot_width
        color = "#e45756" if effect > 0 else "#4c78a8"
        x = min(zero, endpoint)
        bar_width = abs(endpoint - zero)
        elements.append(
            f'<text x="{left - 12}" y="{y + 4:.1f}" text-anchor="end" font-family="Arial" font-size="12">{escape_xml(row["feature_label"])}</text>'
        )
        elements.append(
            f'<rect x="{x:.1f}" y="{y - 10:.1f}" width="{bar_width:.1f}" height="20" fill="{color}"/>'
        )
        elements.append(
            f'<text x="{endpoint + (6 if effect >= 0 else -6):.1f}" y="{y + 4:.1f}" text-anchor="{"start" if effect >= 0 else "end"}" font-family="Arial" font-size="11">{effect:.2f}</text>'
        )
    elements.extend(
        [
            f'<text x="{left}" y="{height - 12}" font-family="Arial" font-size="11" fill="#4c78a8">← thấp hơn khi có cà phê</text>',
            f'<text x="{width - right}" y="{height - 12}" text-anchor="end" font-family="Arial" font-size="11" fill="#e45756">cao hơn khi có cà phê →</text>',
            '</svg>',
        ]
    )
    (OUTPUT_ROOT / "top_feature_effects.svg").write_text(
        "\n".join(elements), encoding="utf-8"
    )


def format_number(value: float, digits: int = 2) -> str:
    return f"{value:.{digits}f}"


def write_report(
    primary: list[dict[str, object]],
    sensitivity: list[dict[str, object]],
    pca_rows: list[dict[str, object]],
    loadings: list[dict[str, object]],
    explained: list[float],
    classifier_score: float,
    classifier_p: float,
) -> None:
    primary_top = primary[:8]
    sensitivity_by_feature = {row["feature"]: row for row in sensitivity}
    loading_pc1 = sorted(loadings, key=lambda row: abs(float(row["pc1_loading"])), reverse=True)[:5]
    loading_pc2 = sorted(loadings, key=lambda row: abs(float(row["pc2_loading"])), reverse=True)[:5]
    minimum_exact_p = 1 / math.comb(9, 4)
    lines = [
        "# Khác biệt giữa mẫu có và không có cà phê",
        "",
        "## Kết luận nhanh",
        "",
        "Phân tích chính dùng **9 phiên của riêng Tài**: 5 không cà phê và 4 có cà phê. Đây là lựa chọn quan trọng để giảm nguy cơ mô hình học danh tính người thay vì học cà phê.",
        "",
        "- Khác biệt chuẩn hóa lớn nhất là **MQ135-2 cuối RECOVERY** (`g=-1,25`), nhưng đây có thể là dấu vết purge/carry-over chứ không phải fingerprint cà phê trực tiếp.",
        "- Trong EXPOSURE, hướng dễ diễn giải nhất vẫn là **BME688 giảm thêm 0,89 điểm %** và **MQ3-1 tăng thêm 0,51 điểm %** khi có cà phê; effect size chỉ nhỏ–vừa và hai nhóm còn chồng lấn.",
        "- Đặc trưng động học nổi bật nhất là slope MQ3-1 (`g=0,88`): nhóm có cà phê tăng theo thời gian, còn nhóm không cà phê giảm nhẹ.",
        f"- PCA: PC1 giải thích **{explained[0] * 100:.1f}%**, PC2 giải thích **{explained[1] * 100:.1f}%** phương sai. PCA chỉ mô tả cấu trúc, không dùng nhãn để tìm trục.",
        f"- Bộ phân loại nearest-centroid LOOCV đạt balanced accuracy **{classifier_score:.1%}**, nhưng kiểm định hoán vị cho `p={classifier_p:.3f}`; chỉ nên xem là kiểm tra thăm dò.",
        "- Với 9 phiên, không có đủ lực thống kê để tuyên bố một biomarker chắc chắn hoặc hiệu năng triển khai.",
        "",
        "## Thiết kế phân tích",
        "",
        "Mỗi phiên là một mẫu độc lập. Tín hiệu hợp lệ được lọc và chuẩn hóa bằng median BASELINE giống `README_PHAN_TICH.md`. Với mỗi cảm biến, ba đặc trưng được dùng:",
        "",
        "1. Trung bình đáp ứng trong EXPOSURE.",
        "2. Slope EXPOSURE, đổi sang `%/phút`.",
        "3. Trung bình 10 điểm cuối RECOVERY.",
        "",
        "Tổng cộng có 15 đặc trưng. Mỗi đặc trưng được mô tả bằng chênh lệch trung bình, Hedges g, Cliff's delta và kiểm định hoán vị chính xác hai phía. Giá trị q dùng hiệu chỉnh Benjamini–Hochberg trên 15 phép so sánh.",
        "",
        "## Đặc trưng khác biệt nhất",
        "",
        "![Các effect size lớn nhất](./top_feature_effects.svg)",
        "",
        "| Đặc trưng | Không CF | Có CF | Chênh lệch | Hedges g | Cliff δ | p exact | q BH |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in primary_top:
        lines.append(
            f"| {row['feature_label']} | {format_number(float(row['without_coffee_mean']))} | "
            f"{format_number(float(row['with_coffee_mean']))} | {format_number(float(row['difference']))} | "
            f"{format_number(float(row['hedges_g']))} | {format_number(float(row['cliffs_delta']))} | "
            f"{format_number(float(row['p_exact']), 3)} | {format_number(float(row['q_bh']), 3)} |"
        )
    lines.extend(
        [
            "",
            f"Với 5 mẫu âm và 4 mẫu dương, độ phân giải nhỏ nhất của kiểm định hoán vị là `{minimum_exact_p:.4f}`. Sau hiệu chỉnh đa kiểm định, kết quả không nên được diễn giải theo cách nhị phân ‘có/không có ý nghĩa’; effect size và độ ổn định qua lần đo quan trọng hơn.",
            "",
            "## PCA",
            "",
            "![PCA của 9 phiên Tài](./pca_scatter.svg)",
            "",
            "Các trục PCA chịu ảnh hưởng mạnh nhất bởi:",
            "",
            "| PC1 | Loading | PC2 | Loading |",
            "|---|---:|---|---:|",
        ]
    )
    for left, right in zip(loading_pc1, loading_pc2):
        lines.append(
            f"| {left['feature_label']} | {format_number(float(left['pc1_loading']), 3)} | "
            f"{right['feature_label']} | {format_number(float(right['pc2_loading']), 3)} |"
        )
    lines.extend(
        [
            "",
            "Hai phiên có cà phê buổi chiều (#7, #8) nằm cao trên PC2, nhưng hai phiên có cà phê buổi tối (#15, #16) lại chồng với vùng của nhóm không cà phê. Đây là dấu hiệu batch/thời gian mạnh hơn một ranh giới cà phê ổn định.",
            "",
            "PCA không chứng minh khả năng phân loại. Các trục tối đa hóa phương sai chung, bao gồm cả drift theo thời gian, khác biệt môi trường và nhiễu cảm biến.",
            "",
            "## Phân tích độ nhạy",
            "",
            "Khi thêm Minh và Quy vào nhóm không cà phê (7 âm so với 4 dương), hướng của các đặc trưng mạnh nhất được kiểm tra lại:",
            "",
            "| Đặc trưng | Hedges g – chỉ Tài | Hedges g – mọi người | Cùng hướng |",
            "|---|---:|---:|:---:|",
        ]
    )
    for row in primary_top[:6]:
        other = sensitivity_by_feature[str(row["feature"])]
        same_direction = float(row["hedges_g"]) * float(other["hedges_g"]) > 0
        lines.append(
            f"| {row['feature_label']} | {format_number(float(row['hedges_g']))} | "
            f"{format_number(float(other['hedges_g']))} | {'Có' if same_direction else 'Không'} |"
        )
    lines.extend(
        [
            "",
            "Phân tích mọi người bị confound vì nhóm có cà phê chỉ có Tài. Vì vậy bảng này chỉ kiểm tra độ nhạy, không thay thế phân tích chính.",
            "",
            "## Diễn giải thực nghiệm",
            "",
            "- **BME688:** mean EXP giảm từ `-1,04%` xuống `-1,94%` khi có cà phê, đúng hướng kỳ vọng nhưng Hedges g chỉ `-0,43`.",
            "- **MQ3-1:** mean EXP tăng từ `0,47%` lên `0,98%`; slope thay đổi rõ hơn mean, song MQ3-2 không lặp lại cùng hành vi.",
            "- **MQ135-2:** cuối RECOVERY có effect size lớn nhất, nhưng mean EXP chỉ khác `-0,36` điểm %, nên không nên dùng recovery làm dấu hiệu cà phê nếu purge chưa chuẩn hóa.",
            "- **Thống kê:** không đặc trưng nào còn nổi bật sau hiệu chỉnh đa kiểm định (`q` nhỏ nhất `0,655`).",
            "",
            "## Hạn chế",
            "",
            "1. Chỉ có 9 phiên trong so sánh chính và tất cả cùng một ngày.",
            "2. Nhóm dương chỉ có Tài; chưa kiểm tra tổng quát hóa sang người khác.",
            "3. Nhãn vẫn là `PROVISIONAL_NAME_ONLY`, suy ra từ tên phiên.",
            "4. Hai khối giờ có điều kiện môi trường khác nhau; PCA có thể phản ánh drift.",
            "5. Feature selection trong LOOCV giúp giảm chiều nhưng không loại bỏ độ bất định do mẫu nhỏ.",
            "",
            "## File đầu ra",
            "",
            "- `session_features.csv`: 15 đặc trưng của 11 phiên binary eligible.",
            "- `univariate_tai.csv`: so sánh chính 5 Tài không cà phê và 4 Tài có cà phê.",
            "- `univariate_all_people.csv`: phân tích độ nhạy 7 âm và 4 dương.",
            "- `pca_scores.csv`, `pca_loadings.csv`: dữ liệu PCA của 9 phiên Tài.",
            "- Script tái lập: `analysis/analyze_2026_10_28_coffee_difference.py`.",
        ]
    )
    (OUTPUT_ROOT / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    sessions, feature_names = load_sessions()
    tai_sessions = [session for session in sessions if session["person_id"] == "Tai"]
    tai_sessions.sort(key=lambda session: int(session["session_no"]))
    sessions.sort(key=lambda session: int(session["session_no"]))
    if len(tai_sessions) != 9 or sum(int(session["label"]) for session in tai_sessions) != 4:
        raise ValueError("Expected 9 Tai sessions with 4 coffee-positive sessions")

    session_rows = []
    for session in sessions:
        session_rows.append(
            {
                "session_no": session["session_no"],
                "folder": session["folder"],
                "person_id": session["person_id"],
                "coffee_on_person_label": session["label"],
                **session["features"],
            }
        )
    write_csv(
        OUTPUT_ROOT / "session_features.csv",
        session_rows,
        ["session_no", "folder", "person_id", "coffee_on_person_label", *feature_names],
    )

    primary = compare_features(tai_sessions, feature_names)
    sensitivity = compare_features(sessions, feature_names)
    comparison_fields = [
        "feature",
        "feature_label",
        "without_coffee_mean",
        "without_coffee_sd",
        "with_coffee_mean",
        "with_coffee_sd",
        "difference",
        "hedges_g",
        "cliffs_delta",
        "p_exact",
        "q_bh",
    ]
    write_csv(OUTPUT_ROOT / "univariate_tai.csv", primary, comparison_fields)
    write_csv(OUTPUT_ROOT / "univariate_all_people.csv", sensitivity, comparison_fields)

    matrix = [
        [float(session["features"][feature]) for feature in feature_names]
        for session in tai_sessions
    ]
    labels = [int(session["label"]) for session in tai_sessions]
    scores, explained, eigenvectors = pca(matrix)
    pca_rows = [
        {
            "session_no": session["session_no"],
            "folder": session["folder"],
            "coffee_on_person_label": session["label"],
            "pc1": score[0],
            "pc2": score[1],
            "pc3": score[2],
        }
        for session, score in zip(tai_sessions, scores)
    ]
    write_csv(
        OUTPUT_ROOT / "pca_scores.csv",
        pca_rows,
        ["session_no", "folder", "coffee_on_person_label", "pc1", "pc2", "pc3"],
    )
    loading_rows = [
        {
            "feature": feature,
            "feature_label": feature_label(feature),
            "pc1_loading": eigenvectors[index][0],
            "pc2_loading": eigenvectors[index][1],
            "pc3_loading": eigenvectors[index][2],
        }
        for index, feature in enumerate(feature_names)
    ]
    write_csv(
        OUTPUT_ROOT / "pca_loadings.csv",
        loading_rows,
        ["feature", "feature_label", "pc1_loading", "pc2_loading", "pc3_loading"],
    )

    classifier_score, classifier_p = classifier_permutation_p(matrix, labels)
    write_pca_svg(tai_sessions, scores, explained)
    write_effect_svg(primary)
    write_report(
        primary,
        sensitivity,
        pca_rows,
        loading_rows,
        explained,
        classifier_score,
        classifier_p,
    )
    print(f"Wrote analysis to {OUTPUT_ROOT}")
    print(f"PCA explained variance: PC1={explained[0]:.3f}, PC2={explained[1]:.3f}")
    print(f"LOOCV balanced accuracy={classifier_score:.3f}, permutation p={classifier_p:.3f}")


if __name__ == "__main__":
    main()
