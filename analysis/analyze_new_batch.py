"""Analyse data/chua_co_loc_khi_van_3_c and generate report artefacts."""

from __future__ import annotations

from collections import Counter
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
from sklearn.decomposition import PCA
from sklearn.metrics import accuracy_score, balanced_accuracy_score, confusion_matrix, f1_score
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data" / "chua_co_loc_khi_van_3_c"
OUT = DATA_ROOT / "report_outputs"
FIG = OUT / "figures"
TABLE = OUT / "tables"
FIG.mkdir(parents=True, exist_ok=True)
TABLE.mkdir(parents=True, exist_ok=True)

sns.set_theme(style="whitegrid", context="notebook")
plt.rcParams.update({"figure.dpi": 120, "savefig.dpi": 180, "font.family": "DejaVu Sans"})

SIGNALS = ["gas_resistance_ohm", "mq135_voltage_v", "mq3_voltage_v"]
PREFIX = {"gas_resistance_ohm": "bme", "mq135_voltage_v": "mq135", "mq3_voltage_v": "mq3"}
SIGNAL_LABEL = {"gas_resistance_ohm": "BME688 gas", "mq135_voltage_v": "MQ135", "mq3_voltage_v": "MQ3"}
PEOPLE = ["Dũng", "Minh", "Quy", "Tài", "Không rõ"]
PERSON_COLORS = dict(zip(PEOPLE, sns.color_palette("colorblind", len(PEOPLE))))
SESSION_RE = re.compile(r"^\d{8}_\d{6}_[0-9a-f]{32}$", re.I)


def savefig(name: str) -> None:
    plt.savefig(FIG / name, bbox_inches="tight", facecolor="white")
    plt.close()


def parse_label(folder: str) -> dict[str, str]:
    lower = folder.lower()
    if lower.startswith("hihi_"):
        return {"person": "Không rõ", "location": "Không rõ", "clothing": "Không rõ", "condition": "Nhãn hihi"}
    person = "Không rõ"
    if "minh" in lower:
        person = "Minh"
    elif "quy" in lower:
        person = "Quy"
    elif "tai" in lower:
        person = "Tài"
    elif "dung" in lower:
        person = "Dũng"
    if "nguc" in lower:
        location = "Ngực"
    elif "bung" in lower:
        location = "Bụng"
    elif "daugoi" in lower:
        location = "Đầu gối"
    else:
        location = "Không rõ"
    if "khongao" in lower:
        clothing = "Không áo"
    elif "coao" in lower:
        clothing = "Có áo"
    else:
        clothing = "Không rõ"
    condition = "Sau tắm" if "moitam" in lower else "Thông thường"
    return {"person": person, "location": location, "clothing": clothing, "condition": condition}


def slope(t: pd.Series, y: pd.Series) -> float:
    ok = np.isfinite(t) & np.isfinite(y)
    return float(np.polyfit(np.asarray(t)[ok], np.asarray(y)[ok], 1)[0]) if ok.sum() >= 3 else np.nan


# Inventory and integrity.
run_dirs = sorted(p for p in DATA_ROOT.glob("2026-*/*") if p.is_dir())
session_dirs = [p for p in run_dirs if SESSION_RE.match(p.name)]
collect_dirs = [p for p in run_dirs if not SESSION_RE.match(p.name)]
integrity_rows = []
for directory in run_dirs:
    errors = []
    for filename in ["metadata.json", "summary.json", "raw.csv", "events.csv", "signals.png", "normalized.png"]:
        path = directory / filename
        if not path.exists():
            errors.append(f"missing:{filename}")
            continue
        try:
            if path.suffix == ".json":
                json.loads(path.read_text(encoding="utf-8"))
            elif path.suffix == ".csv":
                pd.read_csv(path, nrows=5)
            elif path.suffix == ".png":
                with path.open("rb") as handle:
                    if handle.read(8) != b"\x89PNG\r\n\x1a\n":
                        errors.append(f"invalid_png:{filename}")
        except Exception as exc:
            errors.append(f"{filename}:{type(exc).__name__}")
    integrity_rows.append({"folder": directory.name, "kind": "warmup/session" if directory in session_dirs else "collect", "errors": " | ".join(errors), "valid": not errors})
integrity = pd.DataFrame(integrity_rows)

# Load warm-up/session files. They are supersets containing repeated collect rows.
sessions = []
session_timestamp_sets = {}
for directory in session_dirs:
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    start = pd.Timestamp(metadata["started_at"])
    sessions.append({"folder": directory.name, "start": start, "path": directory})
sessions_df = pd.DataFrame(sessions).sort_values("start").reset_index(drop=True)
sessions_df["session_id"] = [f"S{i + 1}: {t.strftime('%d/%m %H:%M')}" for i, t in enumerate(sessions_df["start"])]
for row in sessions_df.itertuples():
    session_timestamp_sets[row.session_id] = set(pd.read_csv(row.path / "raw.csv", usecols=["timestamp"])["timestamp"].astype(str))

# Load main named collect runs.
frames = []
run_rows = []
for directory in collect_dirs:
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    start = pd.Timestamp(metadata["started_at"])
    prior = sessions_df[sessions_df["start"].le(start)]
    session_id = prior.iloc[-1]["session_id"] if len(prior) else "Không rõ"
    parsed = parse_label(directory.name)
    raw = pd.read_csv(directory / "raw.csv")
    raw["folder"] = directory.name
    raw["session_id"] = session_id
    for key, value in parsed.items():
        raw[key] = value
    frames.append(raw)
    timestamps = set(raw["timestamp"].astype(str))
    repeated = max((len(timestamps & values) for values in session_timestamp_sets.values()), default=0)
    run_rows.append({
        "folder": directory.name, "run_id": metadata.get("run_id"), **parsed,
        "started_at": start, "date": start.strftime("%Y-%m-%d"), "time": start.strftime("%H:%M:%S"),
        "session_id": session_id, "rows": len(raw), "status": metadata.get("status"),
        "baseline_stable": metadata.get("baseline_quality", {}).get("stable"),
        "warning_count": len(summary.get("warnings", [])), "warnings": " | ".join(summary.get("warnings", [])),
        "rows_repeated_in_session": repeated, "repeated_pct": 100 * repeated / max(len(timestamps), 1),
    })
runs = pd.DataFrame(run_rows).sort_values("started_at").reset_index(drop=True)
raw_all = pd.concat(frames, ignore_index=True)

# Sensor-specific validity rules.
for col in ["gas_valid", "heater_stable", "new_data", "bme_fresh", "mq135_fresh", "mq3_fresh"]:
    raw_all[col] = raw_all[col].astype("boolean")
valid_masks = {
    "gas_resistance_ohm": raw_all["bme_status"].eq("OK") & raw_all["bme_fresh"].fillna(False) & raw_all["gas_valid"].fillna(False) & raw_all["heater_stable"].fillna(False) & raw_all["new_data"].fillna(False),
    "mq135_voltage_v": raw_all["mq135_status"].eq("OK") & raw_all["mq135_fresh"].fillna(False),
    "mq3_voltage_v": raw_all["mq3_status"].eq("OK") & raw_all["mq3_fresh"].fillna(False),
}
for signal, mask in valid_masks.items():
    raw_all.loc[~mask, signal] = np.nan

# Per-run baseline normalization.
norm_parts = []
for folder, group in raw_all.groupby("folder", sort=False):
    group = group.copy()
    baseline = group[group["phase"].eq("BASELINE")]
    for signal in SIGNALS:
        base = baseline[signal].median()
        group[f"{signal}_pct"] = 100 * (group[signal] / base - 1)
    norm_parts.append(group)
norm = pd.concat(norm_parts, ignore_index=True)

# Run-level features and quality.
feature_rows, quality_rows = [], []
for run in runs.itertuples():
    group = norm[norm["folder"].eq(run.folder)].sort_values("elapsed_s")
    baseline = group[group["phase"].eq("BASELINE")]
    exposure = group[group["phase"].eq("EXPOSURE")]
    recovery = group[group["phase"].eq("RECOVERY")]
    common = {key: getattr(run, key) for key in ["folder", "person", "location", "clothing", "condition", "started_at", "date", "time", "session_id"]}
    feat = common.copy()
    qual = common.copy()
    qual.update({"rows": len(group), "core_rows": int(group["phase"].isin(["BASELINE", "EXPOSURE", "RECOVERY"]).sum()), "max_gap_s": group["elapsed_s"].diff().max(), "baseline_stable": run.baseline_stable, "warning_count": run.warning_count, "warnings": run.warnings})
    for signal in SIGNALS:
        prefix, pct = PREFIX[signal], f"{signal}_pct"
        exp = exposure.dropna(subset=[pct]).sort_values("phase_elapsed_s")
        early = exp[exp["phase_elapsed_s"].le(20)]
        late = exp[exp["phase_elapsed_s"].ge(exp["phase_elapsed_s"].max() - 20)]
        rec_end = recovery[recovery["phase_elapsed_s"].ge(recovery["phase_elapsed_s"].max() - 10)]
        feat.update({
            f"{prefix}__mean": exp[pct].mean(), f"{prefix}__early20": early[pct].mean(),
            f"{prefix}__late20": late[pct].mean(), f"{prefix}__min": exp[pct].min(),
            f"{prefix}__max": exp[pct].max(), f"{prefix}__slope": 60 * slope(exp["phase_elapsed_s"], exp[pct]),
            f"{prefix}__abs_auc": np.trapezoid(np.abs(exp[pct]), exp["phase_elapsed_s"]),
            f"{prefix}__recovery_end": rec_end[pct].mean(),
        })
        base_values = baseline[signal].dropna()
        qual[f"{prefix}__valid_pct"] = 100 * group[signal].notna().mean()
        qual[f"{prefix}__baseline_cv_pct"] = 100 * base_values.std(ddof=1) / abs(base_values.mean())
        qual[f"{prefix}__recovery_end"] = rec_end[pct].mean()
    for env in ["temperature_c", "humidity_pct", "pressure_hpa"]:
        feat[f"baseline__{env}"] = baseline[env].mean()
    feature_rows.append(feat)
    quality_rows.append(qual)
features = pd.DataFrame(feature_rows).sort_values("started_at").reset_index(drop=True)
quality = pd.DataFrame(quality_rows).sort_values("started_at").reset_index(drop=True)
dynamic_features = [c for c in features if c.split("__")[0] in {"bme", "mq135", "mq3"} and c.endswith(("__mean", "__late20", "__min", "__max", "__slope"))]

# Controlled identity subset.
controlled = features[
    features["location"].eq("Bụng") & features["clothing"].eq("Không áo")
    & features["condition"].eq("Thông thường") & features["person"].isin(["Minh", "Quy", "Tài"])
].copy().reset_index(drop=True)


def grouped_predict(columns: list[str], method: str) -> pd.DataFrame:
    rows = []
    for held_session in controlled["session_id"].unique():
        train = controlled[~controlled["session_id"].eq(held_session)].copy()
        test = controlled[controlled["session_id"].eq(held_session)].copy()
        median = train[columns].median()
        scaler = StandardScaler().fit(train[columns].fillna(median))
        x_train = scaler.transform(train[columns].fillna(median))
        x_test = scaler.transform(test[columns].fillna(median))
        if method == "1-NN":
            predicted = train.iloc[cdist(x_test, x_train).argmin(axis=1)]["person"].to_numpy()
        else:
            labels = sorted(train["person"].unique())
            centroids = np.vstack([x_train[train["person"].to_numpy() == label].mean(axis=0) for label in labels])
            predicted = np.asarray(labels)[cdist(x_test, centroids).argmin(axis=1)]
        for (_, item), pred in zip(test.iterrows(), predicted):
            rows.append({"held_session": held_session, "folder": item["folder"], "true": item["person"], "predicted": pred, "correct": item["person"] == pred, "method": method})
    return pd.DataFrame(rows)


feature_sets = {
    "BME (5)": [c for c in dynamic_features if c.startswith("bme__")],
    "MQ135+MQ3 (10)": [c for c in dynamic_features if c.startswith(("mq135__", "mq3__"))],
    "Tất cả động học (15)": dynamic_features,
    "Chỉ mean (3)": ["bme__mean", "mq135__mean", "mq3__mean"],
}
prediction_frames, score_rows = [], []
for feature_set, columns in feature_sets.items():
    for method in ["1-NN", "Nearest centroid"]:
        pred = grouped_predict(columns, method)
        pred["feature_set"] = feature_set
        prediction_frames.append(pred)
        score_rows.append({
            "feature_set": feature_set, "method": method, "correct": int(pred["correct"].sum()), "n": len(pred),
            "accuracy": accuracy_score(pred["true"], pred["predicted"]),
            "balanced_accuracy": balanced_accuracy_score(pred["true"], pred["predicted"]),
            "macro_f1": f1_score(pred["true"], pred["predicted"], average="macro", zero_division=0),
        })
predictions = pd.concat(prediction_frames, ignore_index=True)
scores = pd.DataFrame(score_rows)

# Pairwise distances in controlled subset.
ctrl_X = controlled[dynamic_features].fillna(controlled[dynamic_features].median())
ctrl_Z = StandardScaler().fit_transform(ctrl_X)
pair_rows = []
for i in range(len(controlled)):
    for j in range(i + 1, len(controlled)):
        pair_rows.append({
            "run_a": controlled.loc[i, "folder"], "run_b": controlled.loc[j, "folder"],
            "person_a": controlled.loc[i, "person"], "person_b": controlled.loc[j, "person"],
            "same_person": controlled.loc[i, "person"] == controlled.loc[j, "person"],
            "same_session": controlled.loc[i, "session_id"] == controlled.loc[j, "session_id"],
            "distance": float(np.linalg.norm(ctrl_Z[i] - ctrl_Z[j])),
        })
pair_distances = pd.DataFrame(pair_rows)

# Figure 1: design and timeline.
fig, axes = plt.subplots(1, 2, figsize=(16, 6), gridspec_kw={"width_ratios": [1.35, 1]})
timeline = runs.copy()
timeline["hours"] = (timeline["started_at"] - timeline["started_at"].min()).dt.total_seconds() / 3600
for person, group in timeline.groupby("person"):
    axes[0].scatter(group["hours"], group["person"], s=90, color=PERSON_COLORS[person], edgecolor="white")
    for _, row in group.iterrows():
        label = f"{row['location']} / {row['clothing']}"
        if row["condition"] != "Thông thường":
            label += f" / {row['condition']}"
        axes[0].annotate(label, (row["hours"], row["person"]), xytext=(4, 5), textcoords="offset points", fontsize=7, rotation=20)
axes[0].set(title="Timeline 16 run chính", xlabel="Giờ kể từ run đầu", ylabel="Người")
design = runs.pivot_table(index="person", columns=["location", "clothing"], values="folder", aggfunc="count", fill_value=0)
sns.heatmap(design, annot=True, fmt="g", cmap="Blues", cbar=False, ax=axes[1])
axes[1].set(title="Số run theo người × điều kiện", xlabel="Vị trí / trạng thái áo", ylabel="")
axes[1].tick_params(axis="x", rotation=35)
fig.suptitle("Thiết kế thu dữ liệu mới", fontsize=15, y=1.02)
plt.tight_layout()
savefig("01_dataset_design.png")

# Figure 2: aligned traces.
aligned_parts = []
for phase, offset in [("EXPOSURE", 0), ("RECOVERY", 120)]:
    part = norm[norm["phase"].eq(phase)].copy()
    part["aligned_s"] = offset + part["phase_elapsed_s"]
    aligned_parts.append(part)
aligned = pd.concat(aligned_parts, ignore_index=True)
fig, axes = plt.subplots(3, 1, figsize=(15, 12), sharex=True)
for ax, signal in zip(axes, SIGNALS):
    for folder, group in aligned.groupby("folder"):
        meta = runs[runs["folder"].eq(folder)].iloc[0]
        ax.plot(group["aligned_s"], group[f"{signal}_pct"], color=PERSON_COLORS[meta["person"]], alpha=.7, linewidth=1.2, label=meta["person"])
    ax.axvline(120, color="black", linestyle="--", linewidth=1)
    ax.axhline(0, color="grey", linewidth=.8)
    ax.set(title=SIGNAL_LABEL[signal], ylabel="Δ baseline (%)")
handles, labels = axes[0].get_legend_handles_labels()
unique = dict(zip(labels, handles))
axes[0].legend(unique.values(), unique.keys(), ncol=5, fontsize=8)
axes[-1].set_xlabel("Exposure 0–120 s | Recovery 120–180 s")
fig.suptitle("Đường đáp ứng của toàn bộ 16 run chính", fontsize=15, y=1.01)
plt.tight_layout()
savefig("02_all_signal_traces.png")

# Figure 3: response heatmap.
heat_cols = ["bme__mean", "mq135__mean", "mq3__mean", "bme__recovery_end", "mq135__recovery_end", "mq3__recovery_end"]
heat = features.set_index(features.apply(lambda r: f"{r.person} | {r.location} | {r.time}", axis=1))[heat_cols]
plt.figure(figsize=(11, 9))
sns.heatmap(heat, annot=True, fmt=".2f", cmap="vlag", center=0, linewidths=.3, cbar_kws={"label": "% baseline"})
plt.title("Đáp ứng trung bình exposure và tín hiệu còn lại cuối recovery", fontsize=14)
plt.xlabel("Đặc trưng")
plt.ylabel("Run")
plt.xticks(rotation=30, ha="right")
plt.tight_layout()
savefig("03_response_heatmap.png")

# Figure 4: quality heatmaps.
qindex = quality.set_index(quality.apply(lambda r: f"{r.person} | {r.location} | {r.time}", axis=1))
cv_cols = ["bme__baseline_cv_pct", "mq135__baseline_cv_pct", "mq3__baseline_cv_pct"]
rec_cols = ["bme__recovery_end", "mq135__recovery_end", "mq3__recovery_end"]
fig, axes = plt.subplots(1, 2, figsize=(14, 10))
sns.heatmap(qindex[cv_cols].set_axis(["BME", "MQ135", "MQ3"], axis=1), annot=True, fmt=".2f", cmap="YlOrRd", ax=axes[0], cbar_kws={"label": "CV (%)"})
axes[0].set(title="Nhiễu baseline", xlabel="", ylabel="Run")
sns.heatmap(qindex[rec_cols].set_axis(["BME", "MQ135", "MQ3"], axis=1), annot=True, fmt=".2f", cmap="vlag", center=0, ax=axes[1], cbar_kws={"label": "% baseline"})
axes[1].set(title="Tín hiệu cuối recovery", xlabel="", ylabel="")
fig.suptitle("Kiểm tra chất lượng từng run", fontsize=15, y=1.01)
plt.tight_layout()
savefig("04_quality_control.png")

# Figure 5: temporal drift.
env_cols = ["baseline__temperature_c", "baseline__humidity_pct", "baseline__pressure_hpa", "bme__mean", "mq135__mean", "mq3__mean"]
fig, axes = plt.subplots(3, 2, figsize=(15, 11), sharex=True)
for ax, col in zip(axes.ravel(), env_cols):
    for person, group in features.groupby("person"):
        ax.plot(group["started_at"], group[col], "o-", color=PERSON_COLORS[person], alpha=.75, label=person)
    ax.set_title(col.replace("baseline__", "Baseline ").replace("__mean", " exposure mean"))
    ax.tick_params(axis="x", rotation=25)
handles, labels = axes[0, 0].get_legend_handles_labels()
axes[0, 0].legend(handles, labels, ncol=2, fontsize=8)
fig.suptitle("Điều kiện nền và đáp ứng thay đổi theo thời gian thu", fontsize=15, y=1.01)
plt.tight_layout()
savefig("05_temporal_drift.png")

# Figure 6: PCA all runs.
X_all = features[dynamic_features].fillna(features[dynamic_features].median())
Z_all = StandardScaler().fit_transform(X_all)
pca_all = PCA(n_components=2).fit(Z_all)
P_all = pca_all.transform(Z_all)
fig, ax = plt.subplots(figsize=(10, 7))
markers = {"Bụng": "o", "Ngực": "s", "Đầu gối": "^", "Không rõ": "X"}
for i, row in features.iterrows():
    ax.scatter(P_all[i, 0], P_all[i, 1], color=PERSON_COLORS[row["person"]], marker=markers[row["location"]], s=110, edgecolor="white")
    ax.annotate(f"{row['person']}-{row['location']}-{row['time'][:5]}", (P_all[i, 0], P_all[i, 1]), xytext=(4, 4), textcoords="offset points", fontsize=7)
ax.set(title="PCA toàn bộ 16 run (mô tả, chưa kiểm soát điều kiện)", xlabel=f"PC1 ({pca_all.explained_variance_ratio_[0]:.1%})", ylabel=f"PC2 ({pca_all.explained_variance_ratio_[1]:.1%})")
plt.tight_layout()
savefig("06_pca_all_runs.png")

# Figure 7: controlled subset mean responses.
long_mean = controlled.melt(id_vars=["person", "session_id", "time"], value_vars=["bme__mean", "mq135__mean", "mq3__mean"], var_name="sensor", value_name="response")
fig, axes = plt.subplots(1, 3, figsize=(16, 5))
for ax, sensor in zip(axes, ["bme__mean", "mq135__mean", "mq3__mean"]):
    subset = long_mean[long_mean["sensor"].eq(sensor)]
    sns.stripplot(data=subset, x="person", y="response", hue="session_id", dodge=True, size=9, ax=ax)
    ax.axhline(0, color="black", linewidth=.8)
    ax.set(title=sensor.replace("__mean", " mean"), xlabel="", ylabel="Δ baseline (%)")
    ax.legend(fontsize=6, title="Session")
fig.suptitle("Subset kiểm soát: bụng – không áo – điều kiện thường (8 run)", fontsize=15, y=1.02)
plt.tight_layout()
savefig("07_controlled_mean_responses.png")

# Figure 8: controlled PCA.
pca_ctrl = PCA(n_components=2).fit(ctrl_Z)
P_ctrl = pca_ctrl.transform(ctrl_Z)
fig, ax = plt.subplots(figsize=(9, 7))
session_markers = {session: marker for session, marker in zip(controlled["session_id"].unique(), ["o", "s", "^"])}
for i, row in controlled.iterrows():
    ax.scatter(P_ctrl[i, 0], P_ctrl[i, 1], color=PERSON_COLORS[row["person"]], marker=session_markers[row["session_id"]], s=140, edgecolor="white")
    ax.annotate(f"{row['person']} {row['time'][:5]}", (P_ctrl[i, 0], P_ctrl[i, 1]), xytext=(5, 5), textcoords="offset points", fontsize=8)
ax.set(title="PCA subset bụng – không áo", xlabel=f"PC1 ({pca_ctrl.explained_variance_ratio_[0]:.1%})", ylabel=f"PC2 ({pca_ctrl.explained_variance_ratio_[1]:.1%})")
plt.tight_layout()
savefig("08_controlled_pca.png")

# Figure 9: same/different-person distance.
fig, ax = plt.subplots(figsize=(8, 5.5))
pair_plot = pair_distances.copy()
pair_plot["group"] = np.where(pair_plot["same_person"], "Cùng người", "Khác người")
sns.boxplot(data=pair_plot, x="group", y="distance", color="#dbe8f4", width=.45, ax=ax)
sns.stripplot(data=pair_plot, x="group", y="distance", hue="same_session", palette={True: "#d62728", False: "#1f77b4"}, size=7, jitter=.12, ax=ax)
ax.set(title="Khoảng cách fingerprint trong subset kiểm soát", xlabel="", ylabel="Khoảng cách z-score")
ax.legend(title="Cùng session")
plt.tight_layout()
savefig("09_controlled_distances.png")

# Figure 10: classification scores.
fig, ax = plt.subplots(figsize=(11, 6))
sns.barplot(data=scores, x="feature_set", y="balanced_accuracy", hue="method", ax=ax)
ax.axhline(1 / 3, color="red", linestyle="--", linewidth=1, label="Ngẫu nhiên 3 lớp ≈ 33%")
ax.set(ylim=(0, 1.05), title="Nhận diện người: leave-one-session-out trên 8 run kiểm soát", xlabel="Nhóm đặc trưng", ylabel="Balanced accuracy")
ax.yaxis.set_major_formatter(lambda x, pos: f"{x:.0%}")
ax.tick_params(axis="x", rotation=15)
plt.tight_layout()
savefig("10_controlled_classification.png")

# Figure 11: best classifier confusion matrix.
best = scores.sort_values(["balanced_accuracy", "accuracy", "macro_f1"], ascending=False).iloc[0]
best_pred = predictions[(predictions["feature_set"].eq(best["feature_set"])) & (predictions["method"].eq(best["method"]))]
labels = ["Minh", "Quy", "Tài"]
cm = confusion_matrix(best_pred["true"], best_pred["predicted"], labels=labels)
fig, axes = plt.subplots(1, 2, figsize=(12, 5))
sns.heatmap(cm, annot=True, fmt="d", cmap="Blues", xticklabels=labels, yticklabels=labels, cbar=False, ax=axes[0])
axes[0].set(title=f"Confusion matrix: {best['method']} / {best['feature_set']}", xlabel="Dự đoán", ylabel="Thực tế")
by_person = best_pred.groupby("true")["correct"].mean().reindex(labels)
axes[1].bar(by_person.index, by_person.values, color=[PERSON_COLORS[x] for x in labels])
axes[1].axhline(1 / 3, color="red", linestyle="--", linewidth=1)
axes[1].set(ylim=(0, 1.05), title="Độ đúng theo người", ylabel="Accuracy")
axes[1].yaxis.set_major_formatter(lambda x, pos: f"{x:.0%}")
plt.tight_layout()
savefig("11_controlled_confusion.png")

# Figure 12: special runs that cannot support identity conclusions.
special = features[(features["condition"].ne("Thông thường")) | features["location"].isin(["Đầu gối", "Không rõ"]) | features["clothing"].eq("Có áo")].copy()
special_long = special.melt(id_vars=["person", "location", "clothing", "condition", "time"], value_vars=["bme__mean", "mq135__mean", "mq3__mean"], var_name="sensor", value_name="response")
special_long["run"] = special_long.apply(lambda r: f"{r.person} | {r.location} | {r.clothing} | {r.condition}", axis=1)
plt.figure(figsize=(12, 6))
sns.barplot(data=special_long, x="run", y="response", hue="sensor")
plt.axhline(0, color="black", linewidth=.8)
plt.title("Các run đặc biệt/không đủ điều kiện đối chứng")
plt.xlabel("")
plt.ylabel("Mean exposure response (%)")
plt.xticks(rotation=25, ha="right")
plt.tight_layout()
savefig("12_special_runs.png")

# Tables and summary.
runs.to_csv(TABLE / "run_manifest.csv", index=False, encoding="utf-8-sig")
integrity.to_csv(TABLE / "integrity.csv", index=False, encoding="utf-8-sig")
quality.to_csv(TABLE / "run_quality.csv", index=False, encoding="utf-8-sig")
features.to_csv(TABLE / "run_features.csv", index=False, encoding="utf-8-sig")
controlled.to_csv(TABLE / "controlled_subset.csv", index=False, encoding="utf-8-sig")
pair_distances.to_csv(TABLE / "controlled_pair_distances.csv", index=False, encoding="utf-8-sig")
predictions.to_csv(TABLE / "controlled_predictions.csv", index=False, encoding="utf-8-sig")
scores.to_csv(TABLE / "controlled_scores.csv", index=False, encoding="utf-8-sig")

warning_counts = Counter()
for warning_text in runs["warnings"].dropna():
    for warning in str(warning_text).split(" | "):
        if warning:
            warning_counts[warning] += 1
same = pair_distances[pair_distances["same_person"]]["distance"]
different = pair_distances[~pair_distances["same_person"]]["distance"]
summary = {
    "folders_total": len(run_dirs), "collect_runs": len(collect_dirs), "warmup_session_folders": len(session_dirs),
    "all_files_valid": bool(integrity["valid"].all()), "collect_rows": int(len(raw_all)),
    "core_rows": int(norm["phase"].isin(["BASELINE", "EXPOSURE", "RECOVERY"]).sum()),
    "minimum_sensor_valid_pct": float(quality[[c for c in quality if c.endswith("__valid_pct")]].min().min()),
    "all_collect_rows_repeated_in_sessions": bool(np.isclose(runs["repeated_pct"], 100).all()),
    "known_people": sorted(runs.loc[runs["person"].ne("Không rõ"), "person"].unique().tolist()),
    "person_counts": runs["person"].value_counts().to_dict(),
    "controlled_subset_runs": len(controlled), "controlled_person_counts": controlled["person"].value_counts().to_dict(),
    "warning_counts": dict(warning_counts),
    "same_person_median_distance": float(same.median()), "different_person_median_distance": float(different.median()),
    "distance_separation_ratio": float(different.median() / same.median()),
    "best_classifier": {key: (float(best[key]) if key in {"accuracy", "balanced_accuracy", "macro_f1"} else str(best[key])) for key in ["feature_set", "method", "accuracy", "balanced_accuracy", "macro_f1"]},
    "pca_all_explained": pca_all.explained_variance_ratio_.tolist(),
    "pca_controlled_explained": pca_ctrl.explained_variance_ratio_.tolist(),
}
(OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=True, indent=2))
print(f"Generated {len(list(FIG.glob('*.png')))} figures and {len(list(TABLE.glob('*.csv')))} tables")
