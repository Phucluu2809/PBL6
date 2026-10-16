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
        base_mean = baseline[env].mean()
        exp = exposure.dropna(subset=[env]).sort_values("phase_elapsed_s")
        late = exp[exp["phase_elapsed_s"].ge(exp["phase_elapsed_s"].max() - 20)]
        rec_end = recovery[recovery["phase_elapsed_s"].ge(recovery["phase_elapsed_s"].max() - 10)]
        env_prefix = {"temperature_c": "temp", "humidity_pct": "humidity", "pressure_hpa": "pressure"}[env]
        feat[f"baseline__{env}"] = base_mean
        feat[f"{env_prefix}__mean_delta"] = (exp[env] - base_mean).mean()
        feat[f"{env_prefix}__late20_delta"] = (late[env] - base_mean).mean()
        feat[f"{env_prefix}__min_delta"] = exp[env].min() - base_mean
        feat[f"{env_prefix}__max_delta"] = exp[env].max() - base_mean
        feat[f"{env_prefix}__slope"] = 60 * slope(exp["phase_elapsed_s"], exp[env])
        feat[f"{env_prefix}__recovery_end_delta"] = rec_end[env].mean() - base_mean
        feat[f"{env_prefix}__baseline_std"] = baseline[env].std(ddof=1)
        feat[f"{env_prefix}__baseline_slope"] = 60 * slope(baseline["phase_elapsed_s"], baseline[env])
    feature_rows.append(feat)
    quality_rows.append(qual)
features = pd.DataFrame(feature_rows).sort_values("started_at").reset_index(drop=True)
quality = pd.DataFrame(quality_rows).sort_values("started_at").reset_index(drop=True)
dynamic_features = [c for c in features if c.split("__")[0] in {"bme", "mq135", "mq3"} and c.endswith(("__mean", "__late20", "__min", "__max", "__slope"))]
environment_response_features = [
    c for c in features
    if c.split("__")[0] in {"temp", "humidity", "pressure"}
    and c.endswith(("__mean_delta", "__late20_delta", "__min_delta", "__max_delta", "__slope"))
]

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
    "BME gas (5)": [c for c in dynamic_features if c.startswith("bme__")],
    "BME đầy đủ (20)": [c for c in dynamic_features if c.startswith("bme__")] + environment_response_features,
    "MQ3 (5)": [c for c in dynamic_features if c.startswith("mq3__")],
    "MQ135 (5)": [c for c in dynamic_features if c.startswith("mq135__")],
    "BME + MQ3 (10)": [c for c in dynamic_features if c.startswith(("bme__", "mq3__"))],
    "BME + MQ135 (10)": [c for c in dynamic_features if c.startswith(("bme__", "mq135__"))],
    "Cả 3 cảm biến (15)": dynamic_features,
    "Cả 3 mean (3)": ["bme__mean", "mq135__mean", "mq3__mean"],
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
fig, ax = plt.subplots(figsize=(15, 6.5))
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

# Extended audit: all raw fields, metadata, timing and per-person/day changes.
raw_columns = pd.read_csv(collect_dirs[0] / "raw.csv", nrows=0).columns.tolist()


def field_group(column: str) -> str:
    if column in {"run_id", "seq", "timestamp", "elapsed_s", "phase_elapsed_s", "phase", "sensor_uptime_s"}:
        return "Định danh/thời gian"
    if column in {"loop_interval_s", "loop_duration_s", "schedule_lag_s"} or "read_" in column:
        return "Timing đọc"
    if column.startswith("external_pump") or column == "pump_command":
        return "Bơm"
    if column in {"temperature_c", "humidity_pct", "pressure_hpa", "gas_resistance_ohm"} or column.startswith("bme_") or column in {"gas_valid", "heater_stable", "new_data"}:
        return "BME688"
    if column.startswith("mq135"):
        return "MQ135"
    if column.startswith("mq3"):
        return "MQ3"
    return "Khác"


field_rows = []
for column in raw_columns:
    series = raw_all[column]
    numeric = pd.to_numeric(series, errors="coerce")
    non_null = int(series.notna().sum())
    note = ""
    if column in {"bme_error", "mq135_error", "mq3_error"}:
        note = "Trống có chủ đích: mọi trạng thái đọc đều OK"
    elif column in {"mq135_ao_voltage_v", "mq3_ao_voltage_v"}:
        note = "Thiếu cấu hình: hệ số chia áp chưa được xác nhận"
    elif column == "loop_interval_s":
        note = "6 giá trị trống ở mẫu đầu của 6 phiên phần cứng"
    elif column == "gas_resistance_ohm":
        note = "6 mẫu MONITOR đầu phiên bị loại do heater_stable=False; không ảnh hưởng pha lõi"
    elif column in {"pump_command", "external_pump_state", "external_pump_source"}:
        note = "Không có phản hồi vật lý từ bơm/nguồn khí"
    elif series.nunique(dropna=True) <= 1:
        note = "Cột hằng trong lô này; dùng để kiểm tra cấu hình/trạng thái"
    field_rows.append({
        "field": column, "group": field_group(column), "dtype": str(series.dtype),
        "rows": len(series), "non_null": non_null, "missing": int(series.isna().sum()),
        "missing_pct": 100 * series.isna().mean(), "unique": int(series.nunique(dropna=True)),
        "minimum": numeric.min() if numeric.notna().any() else np.nan,
        "median": numeric.median() if numeric.notna().any() else np.nan,
        "maximum": numeric.max() if numeric.notna().any() else np.nan,
        "note": note,
    })
field_audit = pd.DataFrame(field_rows)

metadata_rows = []
phase_rows = []
for directory in collect_dirs:
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    item = runs[runs["folder"].eq(directory.name)].iloc[0]
    metadata_rows.append({
        "folder": directory.name, "person": item["person"], "original_name": metadata.get("original_name"),
        "notes": metadata.get("notes"), "person_code": metadata.get("sample", {}).get("person_code"),
        "source": metadata.get("sample", {}).get("source"), "distance_cm": metadata.get("sample", {}).get("distance_cm"),
        "sample_description": metadata.get("sample", {}).get("sample_description"),
        "sampling_method": metadata.get("sample", {}).get("sampling_method"),
        "purge_method": metadata.get("sample", {}).get("purge_method"), "lid_state": metadata.get("sample", {}).get("lid_state"),
        "pump_enabled": metadata.get("config", {}).get("pump", {}).get("enabled"),
        "pump_confirmed": metadata.get("config", {}).get("pump", {}).get("confirmed"),
        "mq135_divider_confirmed": metadata.get("adc_inputs", {}).get("mq135", {}).get("divider_factor_confirmed"),
        "mq3_divider_confirmed": metadata.get("adc_inputs", {}).get("mq3", {}).get("divider_factor_confirmed"),
        "status": metadata.get("status"), "end_reason": metadata.get("end_reason"),
    })
    for phase_item in metadata.get("phase_intervals", []):
        phase_rows.append({"folder": directory.name, "person": item["person"], **phase_item})
metadata_audit = pd.DataFrame(metadata_rows)
phase_durations = pd.DataFrame(phase_rows)

run_audit_rows = []
for run in runs.itertuples():
    group = raw_all[raw_all["folder"].eq(run.folder)].sort_values("elapsed_s")
    core = group[group["phase"].isin(["BASELINE", "EXPOSURE", "RECOVERY"])]
    durations = phase_durations[phase_durations["folder"].eq(run.folder)].set_index("phase")["actual_s"].to_dict()
    run_audit_rows.append({
        "folder": run.folder, "person": run.person, "date": run.date, "time": run.time,
        "location": run.location, "clothing": run.clothing, "condition": run.condition,
        "rows": len(group), "core_rows": len(core), "duplicate_timestamp": int(group["timestamp"].duplicated().sum()),
        "duplicate_run_seq": int(group.duplicated(["run_id", "seq"]).sum()),
        "max_loop_interval_s": group["loop_interval_s"].max(), "p99_loop_interval_s": group["loop_interval_s"].quantile(.99),
        "max_loop_duration_s": group["loop_duration_s"].max(), "max_schedule_lag_s": group["schedule_lag_s"].max(),
        "heater_unstable_all": int((~group["heater_stable"].astype(bool)).sum()),
        "heater_unstable_core": int((~core["heater_stable"].astype(bool)).sum()),
        "mq135_adc_saturated": int((group["mq135_adc_count"].abs() >= 32700).sum()),
        "mq3_adc_saturated": int((group["mq3_adc_count"].abs() >= 32700).sum()),
        "monitor_s": durations.get("MONITOR"), "wait_exposure_s": durations.get("WAIT_EXPOSURE"),
        "wait_recovery_s": durations.get("WAIT_RECOVERY"), "wait_finish_s": durations.get("WAIT_FINISH"),
        "warning_count": run.warning_count, "warnings": run.warnings,
    })
run_audit = pd.DataFrame(run_audit_rows).sort_values(["date", "time"])

person_day_columns = [
    "folder", "person", "date", "time", "session_id", "location", "clothing", "condition",
    "baseline__temperature_c", "baseline__humidity_pct", "baseline__pressure_hpa",
    "temp__mean_delta", "humidity__mean_delta", "pressure__mean_delta",
    "bme__mean", "bme__late20", "bme__slope", "bme__recovery_end",
    "mq135__mean", "mq135__late20", "mq135__slope", "mq135__recovery_end",
    "mq3__mean", "mq3__late20", "mq3__slope", "mq3__recovery_end",
]
person_day = features[person_day_columns].copy()

# Figure 13: completeness and diversity of all 51 raw fields.
audit_plot = field_audit.sort_values(["group", "field"], ascending=[True, False]).reset_index(drop=True)
fig, axes = plt.subplots(1, 2, figsize=(16, 18), sharey=True)
y = np.arange(len(audit_plot))
colors = dict(zip(audit_plot["group"].unique(), sns.color_palette("tab10", audit_plot["group"].nunique())))
bar_colors = [colors[g] for g in audit_plot["group"]]
axes[0].barh(y, audit_plot["missing_pct"], color=bar_colors)
axes[0].set(xlabel="Thiếu (%)", ylabel="Trường raw", title="Mức thiếu dữ liệu")
axes[0].set_yticks(y, audit_plot["field"], fontsize=8)
axes[0].set_xlim(0, 105)
axes[1].barh(y, np.log10(audit_plot["unique"].clip(lower=1)), color=bar_colors)
axes[1].set(xlabel="log10(số giá trị khác nhau)", title="Độ đa dạng của trường")
axes[1].axvline(0, color="black", linewidth=.7)
fig.suptitle("Kiểm toán toàn bộ 50 trường raw trên 10.478 dòng", fontsize=15, y=.995)
plt.tight_layout()
savefig("13_all_field_audit.png")

# Figure 14: timing and manual transition variability.
timing_label = run_audit.apply(lambda r: f"{r.person} {r.date[5:]} {r.time[:5]}", axis=1)
fig, axes = plt.subplots(1, 2, figsize=(16, 8))
wait_plot = run_audit.set_index(timing_label)[["wait_exposure_s", "wait_recovery_s", "wait_finish_s"]]
wait_plot.plot(kind="barh", ax=axes[0], color=["#4c78a8", "#f58518", "#54a24b"])
axes[0].set(title="Thời gian chờ thao tác thủ công", xlabel="Giây", ylabel="Run")
loop_plot = run_audit.set_index(timing_label)[["p99_loop_interval_s", "max_loop_interval_s"]]
loop_plot.plot(kind="barh", ax=axes[1], color=["#72b7b2", "#e45756"])
axes[1].axvline(1, color="black", linestyle="--", linewidth=.8)
axes[1].set(title="Nhịp lấy mẫu 1 Hz", xlabel="Loop interval (giây)", ylabel="")
fig.suptitle("Kiểm tra timing và độ lặp lại của thao tác chuyển pha", fontsize=15, y=1.01)
plt.tight_layout()
savefig("14_timing_and_manual_steps.png")

# Figures 15-16: per-person changes over collection days.
known = features[features["person"].isin(["Dũng", "Minh", "Quy", "Tài"])].sort_values("started_at")
people_order = ["Dũng", "Minh", "Quy", "Tài"]
env_specs = [
    ("baseline__temperature_c", "Nhiệt độ nền (°C)"),
    ("baseline__humidity_pct", "Độ ẩm nền (%)"),
    ("baseline__pressure_hpa", "Áp suất nền (hPa)"),
]
fig, axes = plt.subplots(4, 3, figsize=(16, 14), sharex=False)
for row_index, person in enumerate(people_order):
    subset = known[known["person"].eq(person)]
    labels_x = subset.apply(lambda r: f"{r['date'][5:]}\n{r['time'][:5]}\n{r['location']}", axis=1)
    for column_index, (column, title) in enumerate(env_specs):
        ax = axes[row_index, column_index]
        ax.plot(range(len(subset)), subset[column], "o-", color=PERSON_COLORS[person], linewidth=1.8)
        ax.set_xticks(range(len(subset)), labels_x, rotation=20, fontsize=8)
        ax.set_title(f"{person} – {title}")
        ax.grid(alpha=.3)
fig.suptitle("Biến đổi môi trường baseline của từng người theo ngày/run", fontsize=15, y=1.01)
plt.tight_layout()
savefig("15_person_day_environment.png")

sensor_specs = [("bme__mean", "BME688 gas"), ("mq135__mean", "MQ135"), ("mq3__mean", "MQ3")]
fig, axes = plt.subplots(4, 3, figsize=(16, 14), sharex=False)
for row_index, person in enumerate(people_order):
    subset = known[known["person"].eq(person)]
    labels_x = subset.apply(lambda r: f"{r['date'][5:]}\n{r['time'][:5]}\n{r['location']}", axis=1)
    for column_index, (column, title) in enumerate(sensor_specs):
        ax = axes[row_index, column_index]
        ax.plot(range(len(subset)), subset[column], "o-", color=PERSON_COLORS[person], linewidth=1.8)
        ax.axhline(0, color="black", linewidth=.7)
        ax.set_xticks(range(len(subset)), labels_x, rotation=20, fontsize=8)
        ax.set_title(f"{person} – {title}")
        ax.set_ylabel("Mean exposure (% baseline)")
        ax.grid(alpha=.3)
fig.suptitle("Biến đổi đáp ứng cảm biến của từng người theo ngày/run", fontsize=15, y=1.01)
plt.tight_layout()
savefig("16_person_day_sensor_response.png")

# Figure 17: environment-response correlations; descriptive only.
corr_columns = [
    "baseline__temperature_c", "baseline__humidity_pct", "baseline__pressure_hpa",
    "temp__mean_delta", "humidity__mean_delta", "pressure__mean_delta",
    "bme__mean", "mq135__mean", "mq3__mean",
]
corr_labels = ["T nền", "RH nền", "P nền", "ΔT exp", "ΔRH exp", "ΔP exp", "BME gas", "MQ135", "MQ3"]
corr = features[corr_columns].corr(method="spearman").set_axis(corr_labels, axis=0).set_axis(corr_labels, axis=1)
plt.figure(figsize=(10, 8))
sns.heatmap(corr, annot=True, fmt=".2f", cmap="vlag", center=0, vmin=-1, vmax=1, square=True)
plt.title("Tương quan Spearman giữa môi trường và đáp ứng trên 16 run")
plt.tight_layout()
savefig("17_environment_sensor_correlation.png")

# Figure 18: environmental changes during exposure and end of recovery.
env_heat_columns = [
    "temp__mean_delta", "humidity__mean_delta", "pressure__mean_delta",
    "temp__recovery_end_delta", "humidity__recovery_end_delta", "pressure__recovery_end_delta",
]
env_heat = features.set_index(features.apply(lambda r: f"{r.person} | {r.location} | {r.date[5:]} {r.time[:5]}", axis=1))[env_heat_columns]
env_scaled = env_heat.copy()
env_scaled[["pressure__mean_delta", "pressure__recovery_end_delta"]] *= 10
env_scaled.columns = ["ΔT exp (°C)", "ΔRH exp (điểm %)", "10×ΔP exp (hPa)", "ΔT rec", "ΔRH rec", "10×ΔP rec"]
plt.figure(figsize=(12, 9))
sns.heatmap(env_scaled, annot=True, fmt=".2f", cmap="vlag", center=0, linewidths=.3)
plt.title("Biến đổi nhiệt độ, độ ẩm và áp suất so với baseline")
plt.xlabel("Đại lượng (áp suất nhân 10 để dễ nhìn)")
plt.ylabel("Run")
plt.tight_layout()
savefig("18_environment_phase_changes.png")

# Tables and summary.
runs.to_csv(TABLE / "run_manifest.csv", index=False, encoding="utf-8-sig")
integrity.to_csv(TABLE / "integrity.csv", index=False, encoding="utf-8-sig")
quality.to_csv(TABLE / "run_quality.csv", index=False, encoding="utf-8-sig")
features.to_csv(TABLE / "run_features.csv", index=False, encoding="utf-8-sig")
controlled.to_csv(TABLE / "controlled_subset.csv", index=False, encoding="utf-8-sig")
pair_distances.to_csv(TABLE / "controlled_pair_distances.csv", index=False, encoding="utf-8-sig")
predictions.to_csv(TABLE / "controlled_predictions.csv", index=False, encoding="utf-8-sig")
scores.to_csv(TABLE / "controlled_scores.csv", index=False, encoding="utf-8-sig")
field_audit.to_csv(TABLE / "field_audit_all_50_fields.csv", index=False, encoding="utf-8-sig")
metadata_audit.to_csv(TABLE / "metadata_audit.csv", index=False, encoding="utf-8-sig")
phase_durations.to_csv(TABLE / "phase_durations.csv", index=False, encoding="utf-8-sig")
run_audit.to_csv(TABLE / "run_audit.csv", index=False, encoding="utf-8-sig")
person_day.to_csv(TABLE / "person_day_changes.csv", index=False, encoding="utf-8-sig")
scores[scores["feature_set"].str.startswith("BME")].to_csv(TABLE / "model_table_main_bme688.csv", index=False, encoding="utf-8-sig")
scores[scores["feature_set"].str.startswith("Cả 3")].to_csv(TABLE / "model_table_all_3_sensors.csv", index=False, encoding="utf-8-sig")
scores[scores["feature_set"].eq("BME + MQ3 (10)")].to_csv(TABLE / "model_table_bme688_mq3.csv", index=False, encoding="utf-8-sig")
scores[scores["feature_set"].isin(["MQ3 (5)", "MQ135 (5)", "BME + MQ3 (10)", "BME + MQ135 (10)"])].to_csv(TABLE / "sensor_ablation_scores.csv", index=False, encoding="utf-8-sig")
corr.to_csv(TABLE / "environment_sensor_spearman.csv", encoding="utf-8-sig")

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
    "raw_field_count": len(raw_columns),
    "all_null_fields": field_audit.loc[field_audit["missing_pct"].eq(100), "field"].tolist(),
    "loop_interval_missing": int(raw_all["loop_interval_s"].isna().sum()),
    "duplicate_timestamps": int(raw_all["timestamp"].duplicated().sum()),
    "duplicate_run_seq": int(raw_all.duplicated(["run_id", "seq"]).sum()),
    "heater_unstable_core_rows": int(run_audit["heater_unstable_core"].sum()),
    "adc_saturation_rows": int(run_audit[["mq135_adc_saturated", "mq3_adc_saturated"]].sum().sum()),
    "wait_exposure_range_s": [float(run_audit["wait_exposure_s"].min()), float(run_audit["wait_exposure_s"].max())],
    "wait_recovery_range_s": [float(run_audit["wait_recovery_s"].min()), float(run_audit["wait_recovery_s"].max())],
    "metadata_empty_core_labels": {
        key: int(metadata_audit[key].fillna("").astype(str).str.strip().eq("").sum())
        for key in ["notes", "person_code", "source", "distance_cm"]
    },
}
(OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=True, indent=2))
print(f"Generated {len(list(FIG.glob('*.png')))} figures and {len(list(TABLE.glob('*.csv')))} tables")
