"""Evaluate a small temporal CNN without changing the dashboard model."""

import argparse
import json
from pathlib import Path
from statistics import fmean, median

import numpy as np
import torch
from torch import nn

from models_v2.benchmark_coffee import CURRENT, matrix, summarize
from models_v2.train_coffee import OUTPUT, columns, fit, load
from robonose_s3.coffee_detection import AVAILABLE_SIGNALS, TRUE_FLAGS, extract_features, valid_signal


def sequence(rows):
    features = extract_features(rows, tuple(AVAILABLE_SIGNALS.items()))
    result = []
    for signal, device in AVAILABLE_SIGNALS.items():
        def valid(row):
            return (row.get(f"{device}_status") == "OK" and valid_signal(row, signal)
                    and (device != "bme688" or all(row.get(flag) in TRUE_FLAGS
                                                    for flag in ("heater_stable", "new_data"))))
        base = median(float(row[signal]) for row in rows if row["phase"] == "BASELINE" and valid(row))
        bins = [[] for _ in range(12)]
        for row in rows:
            if row["phase"] == "EXPOSURE" and valid(row):
                time = float(row["phase_elapsed_s"])
                if 0 <= time < 120:
                    bins[int(time // 10)].append(100 * (float(row[signal]) - base) / abs(base))
        if any(len(window) < 5 for window in bins):
            raise ValueError("Exposure window has fewer than five valid scans.")
        result.extend(fmean(window) for window in bins)
    return features + result


class CoffeeCNN(nn.Module):
    def __init__(self, channels):
        super().__init__()
        self.network = nn.Sequential(
            nn.Conv1d(channels, 12, 3, padding=1), nn.GELU(),
            nn.Conv1d(12, 12, 3, padding=1), nn.GELU(),
        )
        self.head = nn.Sequential(nn.Dropout(.25), nn.Linear(24, 1))

    def forward(self, value):
        trace = self.network(value)
        return self.head(torch.cat((trace.mean(dim=-1), trace.amax(dim=-1)), dim=1)).squeeze(1)


def fit_predict(x, labels, category, query):
    x = torch.as_tensor(x, dtype=torch.float32)
    query = torch.as_tensor(query, dtype=torch.float32)
    y = torch.as_tensor(labels, dtype=torch.float32)
    center = x.mean(dim=(0, 2), keepdim=True)
    scale = x.std(dim=(0, 2), keepdim=True, unbiased=False).clamp_min(.01)
    x = ((x - center) / scale).clamp(-8, 8)
    query = ((query - center) / scale).clamp(-8, 8)
    weights = torch.as_tensor(np.where(category == "identity_name_proxy", .65, 1.), dtype=torch.float32)
    weights = weights / torch.where(y > 0, weights[y > 0].sum(), weights[y == 0].sum())
    outputs = []
    for seed in (13, 42, 81):
        torch.manual_seed(seed)
        model = CoffeeCNN(x.shape[1])
        optimizer = torch.optim.AdamW(model.parameters(), lr=.003, weight_decay=.025)
        for _ in range(75):
            gains = (1 + torch.randn((x.shape[0], x.shape[1], 1)) * .1).clamp(.7, 1.3)
            augmented = x * gains + .03 * torch.randn_like(x)
            loss = nn.functional.binary_cross_entropy_with_logits(model(augmented), y, reduction="none")
            optimizer.zero_grad(set_to_none=True)
            (loss * weights).sum().backward()
            optimizer.step()
        model.eval()
        with torch.inference_mode():
            outputs.append(model(query))
    return torch.stack(outputs).mean(dim=0).numpy()


def traces(x):
    return x[:, 25:].reshape(-1, 5, 12)


def v2_features(x):
    return x[:, columns(CURRENT)]


def deployed_v2_margins(x):
    model = json.loads(OUTPUT.read_text(encoding="utf-8"))
    values = (v2_features(x) - model["mean"]) / model["scale"]
    return values @ np.array(model["weights"]) + model["intercept"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nov07-root", type=Path, required=True)
    args = parser.parse_args()
    torch.set_num_threads(1)
    root = Path("data").resolve()
    samples, skipped = load(root, extractor=sequence)
    x, y, kinds = matrix(samples)
    days = np.array([row[0] for row in samples])
    seq = traces(x)
    archive, logits = {}, {}
    choices = {"all": [0, 1, 2, 3, 4], "v2_channels": [1, 3, 4]}
    v2 = np.empty(len(y))
    for name, channels in choices.items():
        pred = np.empty(len(y))
        for day in sorted(set(days)):
            train = days != day
            pred[~train] = fit_predict(seq[train][:, channels], y[train], kinds[train], seq[~train][:, channels])
            if name == "all":
                scaler, clf = fit(v2_features(x[train]), y[train], .1)
                v2[~train] = clf.decision_function(scaler.transform(v2_features(x[~train])))
        logits[name] = pred
        archive[name] = summarize(y, pred > 0, kinds)
    chosen = max(archive, key=lambda name: archive[name]["all"]["balanced_accuracy"])
    channels = choices[chosen]
    blends = (.15, .3, .5)
    blend_metrics = {weight: summarize(y, ((1-weight) * v2 + weight * logits[chosen]) > 0, kinds)
                     for weight in blends}
    blend = max(blends, key=lambda weight: blend_metrics[weight]["all"]["balanced_accuracy"])
    hashes = {row[4] for row in samples}
    holdout = {}
    for name, (rows, bad) in (
        ("nov07", load(args.nov07_root.resolve(strict=True), extractor=sequence, crosscheck_day="2026-11-07")),
        ("hardware", load(root, hardware=True, extractor=sequence)),
    ):
        hx, hy, hk = matrix([row for row in rows if row[4] not in hashes])
        pred = fit_predict(seq[:, channels], y, kinds, traces(hx)[:, channels])
        fused = (1 - blend) * deployed_v2_margins(hx) + blend * pred
        holdout[name] = {"metrics": summarize(hy, pred > 0, hk),
                         "blend": summarize(hy, fused > 0, hk), "invalid": bad}
    report = {"archive_trials": len(samples), "invalid_archive": skipped,
              "archive_grouped": archive, "selected": chosen,
              "archive_blends": blend_metrics, "selected_blend": blend, "holdout": holdout, "activated": False}
    Path(__file__).with_name("coffee_cnn_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
