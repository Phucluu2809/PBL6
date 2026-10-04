"""Generate the figures and result tables embedded in the project README."""

from __future__ import annotations

from pathlib import Path
import json
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy.spatial.distance import cdist
from scipy.stats import spearmanr
from sklearn.decomposition import PCA
from sklearn.metrics import confusion_matrix
from sklearn.preprocessing import StandardScaler


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "first_trial"
FIG_DIR = ROOT / "analysis" / "figures"
RESULT_DIR = ROOT / "analysis" / "results"
FIG_DIR.mkdir(parents=True, exist_ok=True)
RESULT_DIR.mkdir(parents=True, exist_ok=True)

sns.set_theme(style="whitegrid", context="notebook")
plt.rcParams.update({"figure.dpi": 120, "savefig.dpi": 180, "font.family": "DejaVu Sans"})

LABELS = ["khongkhi", "ao", "nach", "nuochoa", "mamtom"]
LABEL_VI = {
    "khongkhi": "Không khí",
    "ao": "Áo",
    "nach": "Nách",
    "nuochoa": "Nước hoa",
    "mamtom": "Mắm tôm",
}
LABEL_ORDER = [LABEL_VI[x] for x in LABELS]
PALETTE = dict(zip(LABEL_ORDER, sns.color_palette("colorblind", len(LABEL_ORDER))))
TRIAL_STYLE = {1: "-", 2: "--"}
SIGNALS = ["gas_resistance_ohm", "mq135_voltage_v", "mq3_voltage_v"]
SIGNAL_PREFIX = {
    "gas_resistance_ohm": "bme_gas",
    "mq135_voltage_v": "mq135",
    "mq3_voltage_v": "mq3",
}
SIGNAL_TITLE = {
    "gas_resistance_ohm": "BME688 gas resistance",
    "mq135_voltage_v": "MQ135 voltage",
    "mq3_voltage_v": "MQ3 voltage",
}
PRIMARY_RE = re.compile(r"^trial(?P<trial>0[12])_(?P<label>khongkhi|ao|nach|nuochoa|mamtom)_")


def savefig(name: str) -> None:
    plt.savefig(FIG_DIR / name, bbox_inches="tight", facecolor="white")
    plt.close()


def safe_slope(t: pd.Series, y: pd.Series) -> float:
    ok = np.isfinite(t) & np.isfinite(y)
    if ok.sum() < 3:
        return np.nan
    return float(np.polyfit(np.asarray(t)[ok], np.asarray(y)[ok], 1)[0])


# ---------------------------------------------------------------------------
# Load only trial01/trial02 runs, as specified by data/first_trial/note.txt.
# ---------------------------------------------------------------------------
run_records: list[dict] = []
frames: list[pd.DataFrame] = []
metadata_by_folder: dict[str, dict] = {}
summary_by_folder: dict[str, dict] = {}

for run_dir in sorted(p for p in DATA_DIR.iterdir() if p.is_dir()):
    match = PRIMARY_RE.match(run_dir.name)
    if not match:
        continue
    trial = int(match.group("trial"))
    label = match.group("label")
    metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    raw = pd.read_csv(run_dir / "raw.csv")
    raw["folder"] = run_dir.name
    raw["trial"] = trial
    raw["label"] = label
    raw["label_vi"] = LABEL_VI[label]
    raw["started_at_parsed"] = pd.Timestamp(metadata["started_at"])
    frames.append(raw)
    metadata_by_folder[run_dir.name] = metadata
    summary_by_folder[run_dir.name] = summary
    run_records.append(
        {
            "folder": run_dir.name,
            "trial": trial,
            "label": label,
            "label_vi": LABEL_VI[label],
            "started_at": metadata["started_at"],
            "rows": len(raw),
            "baseline_stable": metadata.get("baseline_quality", {}).get("stable"),
        }
    )

runs = pd.DataFrame(run_records).sort_values(["trial", "started_at"]).reset_index(drop=True)
raw_all = pd.concat(frames, ignore_index=True)

for col in ["gas_valid", "heater_stable", "new_data", "bme_fresh", "mq135_fresh", "mq3_fresh"]:
    raw_all[col] = raw_all[col].astype("boolean")

valid_masks = {
    "gas_resistance_ohm": (
        raw_all["bme_status"].eq("OK")
        & raw_all["bme_fresh"].fillna(False)
        & raw_all["gas_valid"].fillna(False)
        & raw_all["heater_stable"].fillna(False)
        & raw_all["new_data"].fillna(False)
    ),
    "mq135_voltage_v": raw_all["mq135_status"].eq("OK") & raw_all["mq135_fresh"].fillna(False),
    "mq3_voltage_v": raw_all["mq3_status"].eq("OK") & raw_all["mq3_fresh"].fillna(False),
}
for signal, mask in valid_masks.items():
    raw_all.loc[~mask, signal] = np.nan

# Baseline normalization inside each run.
norm_parts: list[pd.DataFrame] = []
for folder, group in raw_all.groupby("folder", sort=False):
    group = group.copy()
    baseline = group[group["phase"].eq("BASELINE")]
    for signal in SIGNALS:
        baseline_median = baseline[signal].median()
        group[f"{signal}_baseline"] = baseline_median
        group[f"{signal}_pct"] = 100 * (group[signal] / baseline_median - 1)
    norm_parts.append(group)
norm = pd.concat(norm_parts, ignore_index=True)


# ---------------------------------------------------------------------------
# Run-level QC and phase duration tables.
# ---------------------------------------------------------------------------
quality_rows: list[dict] = []
duration_rows: list[dict] = []
for run in runs.itertuples():
    group = norm[norm["folder"].eq(run.folder)].sort_values("elapsed_s")
    baseline = group[group["phase"].eq("BASELINE")]
    recovery = group[group["phase"].eq("RECOVERY")]
    metadata = metadata_by_folder[run.folder]
    row = {
        "folder": run.folder,
        "run": f"T{run.trial}-{run.label_vi}",
        "trial": run.trial,
        "label": run.label,
        "label_vi": run.label_vi,
        "rows": len(group),
        "median_dt_s": group["elapsed_s"].diff().median(),
        "max_gap_s": group["elapsed_s"].diff().max(),
        "baseline_stable": bool(run.baseline_stable),
        "baseline_temperature_c": baseline["temperature_c"].mean(),
        "baseline_humidity_pct": baseline["humidity_pct"].mean(),
    }
    for signal in SIGNALS:
        prefix = SIGNAL_PREFIX[signal]
        base_values = baseline[signal].dropna()
        row[f"{prefix}_valid_pct"] = 100 * group[signal].notna().mean()
        row[f"{prefix}_baseline_cv_pct"] = 100 * base_values.std(ddof=1) / abs(base_values.mean())
        rec_pct = recovery[f"{signal}_pct"].dropna()
        last_t = recovery["phase_elapsed_s"].max()
        row[f"{prefix}_recovery_end_pct"] = recovery.loc[
            recovery["phase_elapsed_s"].ge(last_t - 10), f"{signal}_pct"
        ].mean()
    quality_rows.append(row)

    for interval in metadata.get("phase_intervals", []):
        duration_rows.append(
            {
                "run": f"T{run.trial}-{run.label_vi}",
                "trial": run.trial,
                "label_vi": run.label_vi,
                "phase": interval["phase"],
                "duration_s": interval.get("actual_s", np.nan),
            }
        )

quality = pd.DataFrame(quality_rows).sort_values(["trial", "label_vi"]).reset_index(drop=True)
durations = pd.DataFrame(duration_rows)


# ---------------------------------------------------------------------------
# Run-level response features.
# ---------------------------------------------------------------------------
feature_rows: list[dict] = []
for run in runs.itertuples():
    group = norm[norm["folder"].eq(run.folder)]
    row = {
        "folder": run.folder,
        "run": f"T{run.trial}-{run.label_vi}",
        "trial": run.trial,
        "label": run.label,
        "label_vi": run.label_vi,
        "started_at": run.started_at,
    }
    for signal in SIGNALS:
        prefix = SIGNAL_PREFIX[signal]
        pct_col = f"{signal}_pct"
        exposure = group[group["phase"].eq("EXPOSURE")].dropna(subset=[pct_col]).sort_values("phase_elapsed_s")
        recovery = group[group["phase"].eq("RECOVERY")].dropna(subset=[pct_col]).sort_values("phase_elapsed_s")
        late = exposure[exposure["phase_elapsed_s"].ge(exposure["phase_elapsed_s"].max() - 20)]
        rec_end = recovery[recovery["phase_elapsed_s"].ge(recovery["phase_elapsed_s"].max() - 10)]
        row.update(
            {
                f"{prefix}__mean_pct": exposure[pct_col].mean(),
                f"{prefix}__late20_pct": late[pct_col].mean(),
                f"{prefix}__min_pct": exposure[pct_col].min(),
                f"{prefix}__max_pct": exposure[pct_col].max(),
                f"{prefix}__abs_auc_pct_s": np.trapezoid(
                    np.abs(exposure[pct_col]), exposure["phase_elapsed_s"]
                ),
                f"{prefix}__slope_pct_min": 60 * safe_slope(exposure["phase_elapsed_s"], exposure[pct_col]),
                f"{prefix}__recovery_end_pct": rec_end[pct_col].mean(),
            }
        )
    baseline = group[group["phase"].eq("BASELINE")]
    row["baseline_temperature_c"] = baseline["temperature_c"].mean()
    row["baseline_humidity_pct"] = baseline["humidity_pct"].mean()
    feature_rows.append(row)

features = pd.DataFrame(feature_rows).sort_values(["trial", "started_at"]).reset_index(drop=True)
model_features = [
    c
    for c in features
    if "__" in c and c.endswith(("__mean_pct", "__late20_pct", "__min_pct", "__max_pct", "__slope_pct_min"))
]
feature_labels = {
    c: c.replace("bme_gas__", "BME ")
    .replace("mq135__", "MQ135 ")
    .replace("mq3__", "MQ3 ")
    .replace("mean_pct", "mean")
    .replace("late20_pct", "late20")
    .replace("min_pct", "min")
    .replace("max_pct", "max")
    .replace("slope_pct_min", "slope")
    for c in model_features
}


# ---------------------------------------------------------------------------
# Figure 1: measured phase durations.
# ---------------------------------------------------------------------------
phase_order = ["MONITOR", "BASELINE", "WAIT_EXPOSURE", "EXPOSURE", "WAIT_RECOVERY", "RECOVERY", "WAIT_FINISH"]
phase_colors = {
    "MONITOR": "#9ecae1",
    "BASELINE": "#4c78a8",
    "WAIT_EXPOSURE": "#f2cf5b",
    "EXPOSURE": "#e45756",
    "WAIT_RECOVERY": "#b8e186",
    "RECOVERY": "#54a24b",
    "WAIT_FINISH": "#bdbdbd",
}
duration_pivot = durations.pivot_table(index="run", columns="phase", values="duration_s", aggfunc="sum", fill_value=0)
run_order = [f"T{r.trial}-{r.label_vi}" for r in runs.itertuples()]
duration_pivot = duration_pivot.reindex(run_order)

fig, axes = plt.subplots(1, 2, figsize=(16, 7), gridspec_kw={"width_ratios": [1.25, 1]})
left = np.zeros(len(duration_pivot))
for phase in phase_order:
    values = duration_pivot.get(phase, pd.Series(0, index=duration_pivot.index)).to_numpy()
    axes[0].barh(duration_pivot.index, values, left=left, color=phase_colors[phase], label=phase)
    left += values
axes[0].invert_yaxis()
axes[0].set(title="Toàn bộ thời lượng ghi nhận", xlabel="Giây", ylabel="Run")
axes[0].legend(ncol=2, fontsize=8, loc="lower right")

protocol_phases = [p for p in phase_order if p != "MONITOR"]
left = np.zeros(len(duration_pivot))
for phase in protocol_phases:
    values = duration_pivot.get(phase, pd.Series(0, index=duration_pivot.index)).to_numpy()
    axes[1].barh(duration_pivot.index, values, left=left, color=phase_colors[phase], label=phase)
    left += values
axes[1].invert_yaxis()
axes[1].set(title="Phóng to protocol sau monitor/warm-up", xlabel="Giây", ylabel="")
axes[1].legend(ncol=2, fontsize=8, loc="lower right")
fig.suptitle("Thời lượng thực tế của từng pha trong 10 run chính", fontsize=15, y=1.01)
plt.tight_layout()
savefig("01_phase_durations.png")


# ---------------------------------------------------------------------------
# Figures 2-4: exposure + recovery response curves for every class and trial.
# ---------------------------------------------------------------------------
aligned_parts = []
for phase, offset in [("EXPOSURE", 0), ("RECOVERY", 120)]:
    part = norm[norm["phase"].eq(phase)].copy()
    part["aligned_s"] = offset + part["phase_elapsed_s"]
    aligned_parts.append(part)
aligned = pd.concat(aligned_parts, ignore_index=True)

for number, signal in enumerate(SIGNALS, start=2):
    pct_col = f"{signal}_pct"
    fig, axes = plt.subplots(1, 5, figsize=(20, 4.6), sharex=True)
    for ax, label_vi in zip(axes, LABEL_ORDER):
        subset = aligned[aligned["label_vi"].eq(label_vi)]
        for trial, group in subset.groupby("trial"):
            ax.plot(
                group["aligned_s"],
                group[pct_col],
                linestyle=TRIAL_STYLE[trial],
                color=PALETTE[label_vi],
                linewidth=1.7,
                label=f"Trial {trial}",
            )
        ax.axvline(120, color="black", linestyle=":", linewidth=1)
        ax.axhline(0, color="grey", linewidth=.8)
        ax.axvspan(120, 180, color="#54a24b", alpha=.07)
        ax.set_title(label_vi)
        ax.set_xlabel("Thời gian căn chỉnh (s)")
        ax.legend(fontsize=8)
    axes[0].set_ylabel("Thay đổi so với baseline (%)")
    fig.suptitle(
        f"{SIGNAL_TITLE[signal]}: exposure 0–120 s và recovery 120–180 s",
        fontsize=15,
        y=1.02,
    )
    plt.tight_layout()
    savefig(f"{number:02d}_{SIGNAL_PREFIX[signal]}_curves.png")


# ---------------------------------------------------------------------------
# Figure 5: mean exposure response for each sensor.
# ---------------------------------------------------------------------------
fig, axes = plt.subplots(1, 3, figsize=(17, 5.5))
for ax, signal in zip(axes, SIGNALS):
    prefix = SIGNAL_PREFIX[signal]
    col = f"{prefix}__mean_pct"
    for x, label_vi in enumerate(LABEL_ORDER):
        subset = features[features["label_vi"].eq(label_vi)].sort_values("trial")
        ax.plot([x - .08, x + .08], subset[col], color=PALETTE[label_vi], linewidth=1.5, alpha=.7)
        ax.scatter(
            [x - .08, x + .08],
            subset[col],
            c=["#1f77b4", "#ff7f0e"],
            edgecolor="white",
            s=75,
            zorder=3,
        )
    ax.axhline(0, color="black", linewidth=.8)
    ax.set_xticks(range(len(LABEL_ORDER)), LABEL_ORDER, rotation=25, ha="right")
    ax.set(title=SIGNAL_TITLE[signal], ylabel="Mean exposure response (%)")
axes[0].scatter([], [], c="#1f77b4", label="Trial 1")
axes[0].scatter([], [], c="#ff7f0e", label="Trial 2")
axes[0].legend()
fig.suptitle("Đáp ứng trung bình trong 120 giây exposure", fontsize=15, y=1.02)
plt.tight_layout()
savefig("05_mean_exposure_response.png")


# ---------------------------------------------------------------------------
# Figure 6: BME response dynamics (peak, late exposure, recovery end).
# ---------------------------------------------------------------------------
dynamic_cols = ["bme_gas__min_pct", "bme_gas__late20_pct", "bme_gas__recovery_end_pct"]
dynamic_titles = ["Minimum trong exposure", "Trung bình 20 s cuối exposure", "Trung bình 10 s cuối recovery"]
fig, axes = plt.subplots(1, 3, figsize=(17, 5.5))
for ax, col, title in zip(axes, dynamic_cols, dynamic_titles):
    for x, label_vi in enumerate(LABEL_ORDER):
        subset = features[features["label_vi"].eq(label_vi)].sort_values("trial")
        ax.plot([x - .08, x + .08], subset[col], color=PALETTE[label_vi], linewidth=1.5, alpha=.7)
        ax.scatter([x - .08, x + .08], subset[col], c=["#1f77b4", "#ff7f0e"], s=75, edgecolor="white", zorder=3)
    ax.axhline(0, color="black", linewidth=.8)
    ax.set_xticks(range(len(LABEL_ORDER)), LABEL_ORDER, rotation=25, ha="right")
    ax.set(title=title, ylabel="BME gas response (%)")
fig.suptitle("Động học đáp ứng BME688 và mức hồi phục", fontsize=15, y=1.02)
plt.tight_layout()
savefig("06_bme_dynamics.png")


# ---------------------------------------------------------------------------
# Figure 7: baseline CV and recovery end QC heatmaps.
# ---------------------------------------------------------------------------
quality_indexed = quality.set_index("run").reindex(run_order)
cv_cols = [f"{p}_baseline_cv_pct" for p in ["bme_gas", "mq135", "mq3"]]
rec_cols = [f"{p}_recovery_end_pct" for p in ["bme_gas", "mq135", "mq3"]]
column_names = ["BME gas", "MQ135", "MQ3"]
fig, axes = plt.subplots(1, 2, figsize=(13, 8))
sns.heatmap(
    quality_indexed[cv_cols].set_axis(column_names, axis=1),
    annot=True,
    fmt=".2f",
    cmap="YlOrRd",
    ax=axes[0],
    cbar_kws={"label": "CV (%)"},
)
axes[0].set(title="Nhiễu tương đối trong baseline", xlabel="", ylabel="Run")
sns.heatmap(
    quality_indexed[rec_cols].set_axis(column_names, axis=1),
    annot=True,
    fmt=".2f",
    cmap="vlag",
    center=0,
    ax=axes[1],
    cbar_kws={"label": "Lệch baseline (%)"},
)
axes[1].set(title="Tín hiệu còn lại cuối recovery", xlabel="", ylabel="")
fig.suptitle("Kiểm tra chất lượng baseline và recovery", fontsize=15, y=1.01)
plt.tight_layout()
savefig("07_quality_control.png")


# ---------------------------------------------------------------------------
# Figure 8: standardized fingerprint heatmap.
# ---------------------------------------------------------------------------
X = features[model_features].copy()
X = X.fillna(X.median())
scaler_all = StandardScaler().fit(X)
Xz = scaler_all.transform(X)
fingerprint = pd.DataFrame(Xz, index=features["run"], columns=[feature_labels[c] for c in model_features])
plt.figure(figsize=(16, 7))
sns.heatmap(fingerprint, cmap="vlag", center=0, linewidths=.25)
plt.title("Fingerprint cấp run — z-score theo từng đặc trưng", fontsize=15)
plt.xlabel("Đặc trưng")
plt.ylabel("Run")
plt.xticks(rotation=35, ha="right")
plt.tight_layout()
savefig("08_fingerprint_heatmap.png")


# ---------------------------------------------------------------------------
# Figure 9: PCA.
# ---------------------------------------------------------------------------
pca = PCA(n_components=2)
Z = pca.fit_transform(Xz)
pca_df = features[["run", "trial", "label", "label_vi"]].copy()
pca_df[["PC1", "PC2"]] = Z

fig, ax = plt.subplots(figsize=(9, 7))
for label_vi in LABEL_ORDER:
    group = pca_df[pca_df["label_vi"].eq(label_vi)].sort_values("trial")
    ax.plot(group["PC1"], group["PC2"], color=PALETTE[label_vi], alpha=.45, linewidth=1.5)
    for marker, (_, row) in zip(["o", "s"], group.iterrows()):
        ax.scatter(row.PC1, row.PC2, color=PALETTE[label_vi], marker=marker, s=120, edgecolor="white")
        ax.text(row.PC1 + .08, row.PC2 + .08, row.run, fontsize=8)
ax.set(
    xlabel=f"PC1 ({pca.explained_variance_ratio_[0]:.1%})",
    ylabel=f"PC2 ({pca.explained_variance_ratio_[1]:.1%})",
    title="PCA của fingerprint cấp run",
)
ax.scatter([], [], marker="o", color="grey", label="Trial 1")
ax.scatter([], [], marker="s", color="grey", label="Trial 2")
ax.legend()
plt.tight_layout()
savefig("09_pca.png")


# ---------------------------------------------------------------------------
# Figures 10-11: cross-trial distance and within/between distributions.
# ---------------------------------------------------------------------------
t1 = features[features["trial"].eq(1)].set_index("label").reindex(LABELS)
t2 = features[features["trial"].eq(2)].set_index("label").reindex(LABELS)
A = scaler_all.transform(t1[model_features].fillna(X.median()))
B = scaler_all.transform(t2[model_features].fillna(X.median()))
D = cdist(A, B)
distance_df = pd.DataFrame(D, index=LABEL_ORDER, columns=LABEL_ORDER)

plt.figure(figsize=(8, 6.5))
sns.heatmap(distance_df, annot=True, fmt=".2f", cmap="mako_r", linewidths=.5)
plt.title("Khoảng cách fingerprint chéo trial\nTrial 1 (hàng) và Trial 2 (cột)", fontsize=14)
plt.xlabel("Trial 2")
plt.ylabel("Trial 1")
plt.tight_layout()
savefig("10_cross_trial_distance.png")

within = np.diag(D)
between = D[~np.eye(len(D), dtype=bool)]
distance_long = pd.DataFrame(
    {
        "Nhóm": ["Cùng nhãn"] * len(within) + ["Khác nhãn"] * len(between),
        "Khoảng cách": np.concatenate([within, between]),
    }
)
fig, ax = plt.subplots(figsize=(7, 5.5))
sns.boxplot(data=distance_long, x="Nhóm", y="Khoảng cách", color="#d9e8f5", width=.45, ax=ax)
sns.stripplot(data=distance_long, x="Nhóm", y="Khoảng cách", hue="Nhóm", palette=["#1f77b4", "#d62728"], size=7, jitter=.12, legend=False, ax=ax)
separation_ratio = float(np.median(between) / np.median(within))
ax.set_title(f"Độ lặp lại fingerprint — separation ratio = {separation_ratio:.2f}")
ax.set_xlabel("")
plt.tight_layout()
savefig("11_within_between_distance.png")


# ---------------------------------------------------------------------------
# Figures 12-13: cross-trial nearest-neighbour and sensor ablation.
# ---------------------------------------------------------------------------
feature_sets = {
    "BME gas": [c for c in model_features if c.startswith("bme_gas__")],
    "MQ135 + MQ3": [c for c in model_features if c.startswith(("mq135__", "mq3__"))],
    "Tất cả": model_features,
}
prediction_rows: list[dict] = []
for feature_set, columns in feature_sets.items():
    for reference_trial, query_trial in [(1, 2), (2, 1)]:
        reference = features[features["trial"].eq(reference_trial)].reset_index(drop=True)
        query = features[features["trial"].eq(query_trial)].reset_index(drop=True)
        median = reference[columns].median()
        scaler = StandardScaler().fit(reference[columns].fillna(median))
        ref_values = scaler.transform(reference[columns].fillna(median))
        query_values = scaler.transform(query[columns].fillna(median))
        distances = cdist(query_values, ref_values)
        nearest = distances.argmin(axis=1)
        for i, j in enumerate(nearest):
            prediction_rows.append(
                {
                    "feature_set": feature_set,
                    "reference_trial": reference_trial,
                    "query_trial": query_trial,
                    "true_label": query.loc[i, "label"],
                    "true_label_vi": query.loc[i, "label_vi"],
                    "predicted_label": reference.loc[j, "label"],
                    "predicted_label_vi": reference.loc[j, "label_vi"],
                    "distance": distances[i, j],
                    "correct": query.loc[i, "label"] == reference.loc[j, "label"],
                }
            )

predictions = pd.DataFrame(prediction_rows)
scores = (
    predictions.groupby(["feature_set", "reference_trial", "query_trial"], as_index=False)
    .agg(correct=("correct", "sum"), n=("correct", "size"), accuracy=("correct", "mean"))
)

fig, ax = plt.subplots(figsize=(9, 5.5))
sns.barplot(
    data=scores,
    x="feature_set",
    y="accuracy",
    hue="query_trial",
    palette=["#1f77b4", "#ff7f0e"],
    ax=ax,
)
ax.axhline(.2, color="red", linestyle="--", linewidth=1, label="Ngẫu nhiên 5 lớp = 20%")
ax.set(ylim=(0, 1.08), xlabel="Nhóm cảm biến", ylabel="Accuracy", title="Ablation: nearest-neighbour chéo trial")
ax.yaxis.set_major_formatter(lambda x, pos: f"{x:.0%}")
ax.legend(title="Trial truy vấn")
plt.tight_layout()
savefig("12_sensor_ablation.png")

all_predictions = predictions[predictions["feature_set"].eq("Tất cả")]
cm = confusion_matrix(all_predictions["true_label_vi"], all_predictions["predicted_label_vi"], labels=LABEL_ORDER)
class_accuracy = all_predictions.groupby("true_label_vi")["correct"].mean().reindex(LABEL_ORDER)
fig, axes = plt.subplots(1, 2, figsize=(14, 5.5), gridspec_kw={"width_ratios": [1.2, 1]})
sns.heatmap(cm, annot=True, fmt="d", cmap="Blues", xticklabels=LABEL_ORDER, yticklabels=LABEL_ORDER, ax=axes[0], cbar=False)
axes[0].set(title="Confusion matrix (10 truy vấn)", xlabel="Dự đoán", ylabel="Nhãn thật")
axes[0].tick_params(axis="x", rotation=25)
axes[0].tick_params(axis="y", rotation=0)
axes[1].bar(class_accuracy.index, class_accuracy.values, color=[PALETTE[x] for x in class_accuracy.index])
axes[1].axhline(.2, color="red", linestyle="--", linewidth=1)
axes[1].set(ylim=(0, 1.08), title="Độ đúng theo nhãn", xlabel="", ylabel="Accuracy")
axes[1].tick_params(axis="x", rotation=25)
axes[1].yaxis.set_major_formatter(lambda x, pos: f"{x:.0%}")
plt.tight_layout()
savefig("13_classification_results.png")


# ---------------------------------------------------------------------------
# Figure 14: exploratory nuisance correlations.
# ---------------------------------------------------------------------------
ordered = features.sort_values("started_at").copy()
ordered["collection_order"] = np.arange(1, len(ordered) + 1)
nuisances = ["baseline_temperature_c", "baseline_humidity_pct", "collection_order"]
correlation = pd.DataFrame(index=[feature_labels[c] for c in model_features], columns=["Nhiệt độ nền", "Độ ẩm nền", "Thứ tự thu"], dtype=float)
for feature in model_features:
    for nuisance, nuisance_vi in zip(nuisances, correlation.columns):
        correlation.loc[feature_labels[feature], nuisance_vi] = spearmanr(ordered[feature], ordered[nuisance], nan_policy="omit").statistic

plt.figure(figsize=(8, 8))
sns.heatmap(correlation, annot=True, fmt=".2f", cmap="vlag", center=0, vmin=-1, vmax=1, linewidths=.35)
plt.title("Tương quan Spearman với biến gây nhiễu (n = 10)", fontsize=14)
plt.xlabel("")
plt.ylabel("Đặc trưng")
plt.tight_layout()
savefig("14_nuisance_correlations.png")


# ---------------------------------------------------------------------------
# Save reusable result tables and compact summary.
# ---------------------------------------------------------------------------
quality.to_csv(RESULT_DIR / "run_quality.csv", index=False, encoding="utf-8-sig")
features.to_csv(RESULT_DIR / "run_features.csv", index=False, encoding="utf-8-sig")
distance_df.to_csv(RESULT_DIR / "cross_trial_distances.csv", encoding="utf-8-sig")
predictions.to_csv(RESULT_DIR / "nearest_neighbor_predictions.csv", index=False, encoding="utf-8-sig")
scores.to_csv(RESULT_DIR / "sensor_ablation_scores.csv", index=False, encoding="utf-8-sig")
correlation.to_csv(RESULT_DIR / "nuisance_correlations.csv", encoding="utf-8-sig")

mean_response = features.groupby("label_vi")[[f"{SIGNAL_PREFIX[s]}__mean_pct" for s in SIGNALS]].agg(["mean", "min", "max"])
mean_response.to_csv(RESULT_DIR / "class_response_summary.csv", encoding="utf-8-sig")

all_score = float(all_predictions["correct"].mean())
summary = {
    "primary_runs": int(len(runs)),
    "primary_raw_rows": int(len(raw_all)),
    "minimum_valid_pct": float(quality[[c for c in quality if c.endswith("_valid_pct")]].min().min()),
    "unstable_baseline_runs": quality.loc[~quality["baseline_stable"], "run"].tolist(),
    "max_abs_recovery_end_pct": float(quality[[c for c in quality if c.endswith("_recovery_end_pct")]].abs().max().max()),
    "pca_pc1_explained": float(pca.explained_variance_ratio_[0]),
    "pca_pc2_explained": float(pca.explained_variance_ratio_[1]),
    "median_within_distance": float(np.median(within)),
    "median_between_distance": float(np.median(between)),
    "separation_ratio": separation_ratio,
    "all_sensor_cross_trial_accuracy": all_score,
    "class_accuracy": {label: float(value) for label, value in class_accuracy.items()},
}
(RESULT_DIR / "summary_metrics.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

print(json.dumps(summary, ensure_ascii=True, indent=2))
print(f"Generated {len(list(FIG_DIR.glob('*.png')))} figures in {FIG_DIR}")
