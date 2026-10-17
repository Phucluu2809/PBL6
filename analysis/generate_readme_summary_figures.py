"""Generate compact body-odor figures and supporting tables for README."""

from itertools import combinations
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy.spatial.distance import cdist
from sklearn.metrics import balanced_accuracy_score
from sklearn.preprocessing import StandardScaler


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "chua_co_loc_khi_van_3_c" / "report_outputs" / "tables"
OUT = ROOT / "analysis" / "figures"
TABLE_OUT = SOURCE
OUT.mkdir(parents=True, exist_ok=True)

sns.set_theme(style="whitegrid", context="talk")
plt.rcParams.update({"font.family": "DejaVu Sans", "figure.dpi": 130, "savefig.dpi": 180})

PEOPLE = ["Minh", "Quy", "Tài"]
COLORS = dict(zip(PEOPLE, sns.color_palette("colorblind", 3)))


def save(name: str) -> None:
    plt.savefig(OUT / name, bbox_inches="tight", facecolor="white")
    plt.close()


# 1. Mean exposure by person with every run visible.
controlled = pd.read_csv(SOURCE / "controlled_subset.csv")
signals = [
    ("bme__mean", "BME688 gas"),
    ("mq135__mean", "MQ135"),
    ("mq3__mean", "MQ3"),
]
fig, axes = plt.subplots(1, 3, figsize=(16, 5.5))
for ax, (column, title) in zip(axes, signals):
    for x, person in enumerate(PEOPLE):
        values = controlled.loc[controlled["person"].eq(person), column].to_numpy(float)
        offsets = np.linspace(-0.08, 0.08, len(values)) if len(values) > 1 else np.array([0.0])
        ax.scatter(x + offsets, values, s=80, color=COLORS[person], edgecolor="white", zorder=3)
        mean = values.mean()
        ax.hlines(mean, x - 0.20, x + 0.20, color="black", linewidth=3, zorder=4)
        ax.text(x, .96, f"TB {mean:+.2f}%", transform=ax.get_xaxis_transform(), ha="center", va="top", fontsize=9)
    ax.axhline(0, color="grey", linewidth=.9)
    ax.set_xticks(range(3), PEOPLE)
    ax.set(title=title, xlabel="Người", ylabel="Mean exposure (% baseline)")
fig.suptitle("Lô nhận diện người: đáp ứng trung bình trong cùng điều kiện bụng – không áo", fontsize=16, y=1.03)
plt.tight_layout()
save("15_person_mean_response_simple.png")


# 2. Sensor-quality summary.
quality = pd.read_csv(SOURCE / "run_quality.csv")
sensor_quality = pd.DataFrame({
    "Cảm biến": ["BME688", "MQ135", "MQ3"],
    "Trung vị": [
        quality["bme__baseline_cv_pct"].median(),
        quality["mq135__baseline_cv_pct"].median(),
        quality["mq3__baseline_cv_pct"].median(),
    ],
    "Lớn nhất": [
        quality["bme__baseline_cv_pct"].max(),
        quality["mq135__baseline_cv_pct"].max(),
        quality["mq3__baseline_cv_pct"].max(),
    ],
})
fig, axes = plt.subplots(1, 2, figsize=(14, 5.5), gridspec_kw={"width_ratios": [1.35, 1]})
x = np.arange(3)
width = .34
axes[0].bar(x - width / 2, sensor_quality["Trung vị"], width, label="Trung vị", color="#4c78a8")
axes[0].bar(x + width / 2, sensor_quality["Lớn nhất"], width, label="Lớn nhất", color="#f58518")
axes[0].set_yscale("log")
axes[0].set_xticks(x, sensor_quality["Cảm biến"])
axes[0].set(title="Nhiễu baseline (CV, thang log)", ylabel="CV (%)")
axes[0].legend()
for i, row in sensor_quality.iterrows():
    axes[0].text(i - width / 2, row["Trung vị"] * 1.12, f"{row['Trung vị']:.2f}%", ha="center", fontsize=9)
    axes[0].text(i + width / 2, row["Lớn nhất"] * 1.12, f"{row['Lớn nhất']:.2f}%", ha="center", fontsize=9)

warning_counts = [8, 10]
labels = ["Baseline drift", "Chưa hồi phục"]
bars = axes[1].bar(labels, warning_counts, color=["#e45756", "#b279a2"], width=.55)
axes[1].set(ylim=(0, 16), title="Số run MQ135 bị cảnh báo", ylabel="Số run / 16")
axes[1].bar_label(bars, labels=["8/16", "10/16"], padding=4)
fig.suptitle("Tóm tắt chất lượng cảm biến", fontsize=16, y=1.03)
plt.tight_layout()
save("16_sensor_quality_simple.png")


# 3. Best leave-one-session-out result for each feature set.
scores = pd.read_csv(SOURCE / "controlled_scores.csv")
best = (
    scores.sort_values(["balanced_accuracy", "accuracy", "macro_f1"], ascending=False)
    .groupby("feature_set", as_index=False)
    .first()
    .sort_values("balanced_accuracy")
)
palette = ["#59a14f" if label == "MQ3 (5)" else "#4c78a8" for label in best["feature_set"]]
fig, ax = plt.subplots(figsize=(11, 6.5))
bars = ax.barh(best["feature_set"], best["balanced_accuracy"], color=palette)
ax.axvline(1 / 3, color="red", linestyle="--", linewidth=1.2, label="Ngẫu nhiên 3 lớp ≈ 33%")
ax.set(xlim=(0, 1), title="Khả năng nhận diện người theo nhóm cảm biến", xlabel="Balanced accuracy", ylabel="")
ax.xaxis.set_major_formatter(lambda value, pos: f"{value:.0%}")
for bar, (_, row) in zip(bars, best.iterrows()):
    ax.text(
        bar.get_width() + .015, bar.get_y() + bar.get_height() / 2,
        f"{row['balanced_accuracy']:.1%} – {row['method']}", va="center", fontsize=9,
    )
ax.legend(loc="lower right")
plt.tight_layout()
save("17_person_model_comparison_simple.png")

# 4. Data-usability funnel and experimental-design coverage.
manifest = pd.read_csv(SOURCE / "run_manifest.csv")
integrity = pd.read_csv(SOURCE / "integrity.csv")
known = manifest[manifest["person"].ne("Không rõ")].copy()
standard = known[
    known["location"].isin(["Ngực", "Bụng"])
    & known["clothing"].eq("Không áo")
    & known["condition"].eq("Thông thường")
]
funnel = pd.DataFrame({
    "Tầng dữ liệu": [
        "Thư mục trên đĩa", "Sau lọc toàn bộ\nwarm-up",
        "Ngực/bụng\nkhông áo", "Subset so sánh\nbụng–không áo",
    ],
    "Số lượng": [len(integrity), len(manifest), len(standard), len(controlled)],
})

coverage = manifest.copy()
coverage["Điều kiện"] = coverage.apply(
    lambda row: (
        "Sau tắm / chưa rõ vị trí" if row["condition"] == "Sau tắm"
        else "Chưa rõ nhãn/điều kiện" if row["person"] == "Không rõ"
        else f"{row['location']} / {row['clothing']}"
    ), axis=1,
)
coverage_order = [
    "Bụng / Không áo", "Ngực / Không áo", "Ngực / Có áo",
    "Đầu gối / Không rõ", "Sau tắm / chưa rõ vị trí",
]
coverage_table = (
    coverage.pivot_table(index="person", columns="Điều kiện", values="folder", aggfunc="count", fill_value=0)
    .reindex(index=["Minh", "Quy", "Tài", "Dũng"], columns=coverage_order, fill_value=0)
)

fig, axes = plt.subplots(1, 2, figsize=(16, 6.5), gridspec_kw={"width_ratios": [1, 1.6]})
bars = axes[0].barh(funnel["Tầng dữ liệu"], funnel["Số lượng"], color=sns.color_palette("Blues_r", len(funnel)))
axes[0].invert_yaxis()
axes[0].set(title="Từ dữ liệu thô đến tập có thể so sánh", xlabel="Số thư mục/run", ylabel="")
axes[0].bar_label(bars, padding=4)
sns.heatmap(coverage_table, annot=True, fmt="g", cmap="Blues", cbar=False, linewidths=.5, ax=axes[1])
axes[1].set(title="Độ phủ người × điều kiện", xlabel="", ylabel="")
axes[1].tick_params(axis="x", rotation=28)
fig.suptitle("Thiết kế dữ liệu hiện tại còn hẹp và không cân bằng", fontsize=16, y=1.02)
plt.tight_layout()
save("18_body_odor_data_coverage.png")


# 5. MQ3 consistency across the three comparable sessions.
session_order = list(dict.fromkeys(controlled["session_id"].tolist()))
fig, ax = plt.subplots(figsize=(11, 6.5))
for person in PEOPLE:
    subset = controlled[controlled["person"].eq(person)].set_index("session_id").reindex(session_order)
    ax.plot(session_order, subset["mq3__mean"], marker="o", linewidth=2.5, markersize=9,
            color=COLORS[person], label=person)
ax.axhline(0, color="grey", linewidth=.9)
ax.set(title="MQ3 giữ thứ tự người qua ba phiên bụng–không áo",
       xlabel="Phiên", ylabel="Mean exposure (% baseline)")
ax.legend(title="Người")
ax.tick_params(axis="x", rotation=12)
ax.text(.01, .98, "S4 không có Minh; S5 và S6 có đủ ba người", transform=ax.transAxes,
        ha="left", va="top", fontsize=10)
plt.tight_layout()
save("19_mq3_session_consistency.png")


# 6. How much of each sensor's mean-response variance aligns with person labels.
sensor_columns = {"BME688": "bme__mean", "MQ135": "mq135__mean", "MQ3": "mq3__mean"}
discrimination_rows = []
person_stat_rows = []
for sensor, column in sensor_columns.items():
    grand_mean = controlled[column].mean()
    ss_total = ((controlled[column] - grand_mean) ** 2).sum()
    ss_between = sum(
        len(group) * (group[column].mean() - grand_mean) ** 2
        for _, group in controlled.groupby("person")
    )
    eta_squared = ss_between / ss_total if ss_total else np.nan
    prefix = column.split("__")[0]
    dynamic_columns = [
        f"{prefix}__mean", f"{prefix}__late20", f"{prefix}__min",
        f"{prefix}__max", f"{prefix}__slope",
    ]
    correlation = controlled[dynamic_columns].corr(method="spearman").abs().to_numpy()
    median_redundancy = np.median(correlation[np.triu_indices_from(correlation, 1)])
    discrimination_rows.append({
        "sensor": sensor, "eta_squared_person": eta_squared,
        "median_abs_spearman_5_features": median_redundancy,
    })
    for person, group in controlled.groupby("person"):
        values = group[column].to_numpy(float)
        person_stat_rows.append({
            "sensor": sensor, "person": person, "n": len(values),
            "mean": values.mean(), "sd": values.std(ddof=1),
            "min": values.min(), "max": values.max(), "range": np.ptp(values),
        })

discrimination = pd.DataFrame(discrimination_rows)
person_stats = pd.DataFrame(person_stat_rows)
discrimination.to_csv(TABLE_OUT / "controlled_sensor_discrimination.csv", index=False, encoding="utf-8-sig")
person_stats.to_csv(TABLE_OUT / "controlled_person_sensor_stats.csv", index=False, encoding="utf-8-sig")

fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))
colors = ["#4c78a8", "#e45756", "#59a14f"]
bars = axes[0].bar(discrimination["sensor"], discrimination["eta_squared_person"], color=colors)
axes[0].set(ylim=(0, 1), title="Phần phương sai mean gắn với nhãn người", ylabel="η² mô tả", xlabel="")
axes[0].bar_label(bars, labels=[f"{value:.1%}" for value in discrimination["eta_squared_person"]], padding=3)
bars = axes[1].bar(discrimination["sensor"], discrimination["median_abs_spearman_5_features"], color=colors)
axes[1].set(ylim=(0, 1), title="Mức trùng thông tin giữa 5 đặc trưng", ylabel="Median |Spearman ρ|", xlabel="")
axes[1].bar_label(bars, labels=[f"{value:.2f}" for value in discrimination["median_abs_spearman_5_features"]], padding=3)
fig.suptitle("MQ3 phân tách tốt nhất nhưng các đặc trưng động học còn dư thừa", fontsize=16, y=1.03)
plt.tight_layout()
save("20_sensor_discrimination_diagnostics.png")


# 7. Sampling uncertainty and an exact exploratory label-permutation check.
mq3_columns = ["mq3__mean", "mq3__late20", "mq3__min", "mq3__max", "mq3__slope"]
groups = controlled["session_id"].to_numpy()
x = controlled[mq3_columns].to_numpy(float)
true_labels = controlled["person"].to_numpy()


def grouped_mq3_score(labels: np.ndarray) -> float:
    predicted = np.empty(len(labels), dtype=object)
    for held_session in pd.unique(groups):
        train = groups != held_session
        test = ~train
        scaler = StandardScaler().fit(x[train])
        x_train = scaler.transform(x[train])
        x_test = scaler.transform(x[test])
        train_labels = labels[train]
        available = sorted(set(train_labels))
        centroids = np.vstack([x_train[train_labels == label].mean(axis=0) for label in available])
        predicted[test] = np.asarray(available)[cdist(x_test, centroids).argmin(axis=1)]
    return balanced_accuracy_score(labels, predicted)


observed_ba = grouped_mq3_score(true_labels)
permuted_scores = []
indices = list(range(len(controlled)))
for minh_indices in combinations(indices, 2):
    remaining = [index for index in indices if index not in minh_indices]
    for quy_indices in combinations(remaining, 3):
        labels = np.asarray(["Tài"] * len(controlled), dtype=object)
        labels[list(minh_indices)] = "Minh"
        labels[list(quy_indices)] = "Quy"
        permuted_scores.append(grouped_mq3_score(labels))
permuted_scores = np.asarray(permuted_scores)
permutation_p = float(np.mean(permuted_scores >= observed_ba - 1e-12))

n, correct = 8, 6
z = 1.959963984540054
p_hat = correct / n
denominator = 1 + z**2 / n
center = (p_hat + z**2 / (2 * n)) / denominator
half_width = z * math.sqrt(p_hat * (1 - p_hat) / n + z**2 / (4 * n**2)) / denominator
ci_low, ci_high = center - half_width, center + half_width

uncertainty = {
    "accuracy": p_hat,
    "accuracy_wilson_95": [ci_low, ci_high],
    "balanced_accuracy": observed_ba,
    "permutation_assignments": int(len(permuted_scores)),
    "permutation_ge_observed": int(np.sum(permuted_scores >= observed_ba - 1e-12)),
    "permutation_p_exploratory": permutation_p,
    "note": "Post-selection exploratory check; not a confirmatory p-value.",
}
(TABLE_OUT / "controlled_uncertainty.json").write_text(
    json.dumps(uncertainty, ensure_ascii=False, indent=2), encoding="utf-8",
)

fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))
axes[0].errorbar([0], [p_hat], yerr=[[p_hat - ci_low], [ci_high - p_hat]], fmt="o",
                 markersize=11, capsize=8, linewidth=3, color="#59a14f")
axes[0].axhline(1 / 3, color="red", linestyle="--", linewidth=1.2, label="Ngẫu nhiên 3 lớp")
axes[0].axhline(3 / 8, color="grey", linestyle=":", linewidth=1.2, label="Đoán lớp đông nhất")
axes[0].set(xlim=(-.5, .5), ylim=(0, 1), xticks=[0], xticklabels=["MQ3\n6/8 đúng"],
            title="Accuracy và khoảng Wilson 95%", ylabel="Accuracy")
axes[0].yaxis.set_major_formatter(lambda value, pos: f"{value:.0%}")
axes[0].legend(loc="lower right", fontsize=9)
axes[0].text(0, ci_high + .035, f"{ci_low:.1%}–{ci_high:.1%}", ha="center", fontsize=10)

bins = np.linspace(0, 1, 13)
axes[1].hist(permuted_scores, bins=bins, color="#9ecae9", edgecolor="white")
axes[1].axvline(observed_ba, color="#e45756", linewidth=2.5,
                label=f"Quan sát {observed_ba:.1%}")
axes[1].set(title="Hoán vị nhãn cho mô hình MQ3 đã cố định",
            xlabel="Balanced accuracy", ylabel="Số cách gán nhãn")
axes[1].xaxis.set_major_formatter(lambda value, pos: f"{value:.0%}")
axes[1].legend()
axes[1].text(.98, .95, f"6/560 ≥ quan sát\np mô tả = {permutation_p:.3f}",
             transform=axes[1].transAxes, ha="right", va="top", fontsize=10)
fig.suptitle("Tín hiệu MQ3 đáng chú ý, nhưng độ bất định vẫn rất rộng", fontsize=16, y=1.03)
plt.tight_layout()
save("21_mq3_uncertainty.png")


print("Generated 7 compact README figures and 3 supporting result files")
