"""Binary coffee detection from a completed RoboNose S3 sensor trial."""

from functools import lru_cache
import json
import math
from pathlib import Path
from statistics import fmean, median, quantiles

from ..schema import valid_signal


PHASE_SPANS = {"BASELINE": 50, "EXPOSURE": 105}
SIGNALS = (("gas_resistance_ohm", "bme688"), ("mq3_1_voltage_v", "mq3_1"))
AVAILABLE_SIGNALS = dict((*SIGNALS, ("tgs2602_voltage_v", "tgs2602"),
                          ("mq135_2_voltage_v", "mq135_2"), ("mq3_2_voltage_v", "mq3_2")))
TRUE_FLAGS = (True, "True", "true", 1, "1")


def extract_features(rows, signals=SIGNALS, *, kinetics=False):
    phases = {phase: [] for phase in PHASE_SPANS}
    for row in rows:
        if row["phase"] in phases:
            phases[row["phase"]].append(row)

    features = []
    for signal, device in signals:
        valid = {}
        for phase, minimum_span in PHASE_SPANS.items():
            samples = phases[phase]
            times = [float(row["phase_elapsed_s"]) for row in samples]
            if any(not math.isfinite(time) for time in times) or any(
                not 0 <= right - left <= 3 for left, right in zip(times, times[1:])
            ):
                raise ValueError(f"Pha {phase} có thời gian lấy mẫu không hợp lệ.")
            points = [(time, float(row[signal])) for time, row in zip(times, samples)
                      if row.get(f"{device}_status") == "OK" and valid_signal(row, signal)
                      and (device != "bme688" or all(row.get(flag) in TRUE_FLAGS
                                                     for flag in ("heater_stable", "new_data")))]
            if not points or len(points) < .9 * len(samples) or points[-1][0] - points[0][0] < minimum_span or any(
                right[0] - left[0] > 3 for left, right in zip(points, points[1:])
            ):
                raise ValueError(f"Tín hiệu {device} ở pha {phase} không đủ độ phủ.")
            valid[phase] = points

        baseline = median(value for _, value in valid["BASELINE"])
        if not baseline:
            raise ValueError(f"Đường nền {device} bằng 0.")
        exposure = [(time, 100 * (value - baseline) / abs(baseline)) for time, value in valid["EXPOSURE"]]
        times, values = zip(*exposure)
        window = [value for time, value in exposure if 40 <= time < 80]
        if not window:
            raise ValueError(f"Thiếu tín hiệu {device} trong cửa sổ 40–80 giây.")
        low, *_, high = quantiles(values, n=10, method="inclusive")
        time_center, value_center = fmean(times), fmean(values)
        slope = sum((t - time_center) * (v - value_center) for t, v in exposure)
        slope /= sum((t - time_center) ** 2 for t in times)
        features.extend((value_center, fmean(window), low, high, 60 * slope))
        if kinetics:
            baseline_values = [100 * (value - baseline) / abs(baseline)
                               for _, value in valid["BASELINE"]]
            base_low, *_, base_high = quantiles(baseline_values, n=10, method="inclusive")
            early = fmean(value for time, value in exposure if 5 <= time < 30)
            late = fmean(value for time, value in exposure if 85 <= time < 105)
            features.extend((early, late, late - early, base_high - base_low))
    return features


@lru_cache(maxsize=1)
def load_model():
    folder = Path(__file__).parent
    path = next((folder / name for name in ("model_sensor_tuned.json", "model_sensor_ml.json", "model_sensor_v3.json",
                                           "model_sensor_v2.json") if (folder / name).is_file()),
                folder / "model.json")
    return json.loads(path.read_text(encoding="utf-8"))


def _tree_score(features, tree):
    node = 0
    while tree["left"][node] != -1:
        branch = "left" if features[tree["feature"][node]] <= tree["threshold"][node] else "right"
        node = tree[branch][node]
    return tree["positive"][node]


def predict_features(features, model=None):
    if not all(map(math.isfinite, features)):
        raise ValueError("Đặc trưng cảm biến không hữu hạn.")
    model = load_model() if model is None else model
    if model.get("kind") == "extra_trees":
        score = fmean(_tree_score(features, tree) for tree in model["trees"])
        return {"status": "PREDICTED", "has_coffee": score >= .5, "model": model["version"]}
    scaled = [(value - center) / scale for value, center, scale in
              zip(features, model["mean"], model["scale"], strict=True)]
    if model.get("kind") == "svm_rbf":
        score = model["intercept"] + math.fsum(
            weight * math.exp(-model["gamma"] * math.fsum(
                (value - anchor) ** 2 for value, anchor in zip(scaled, support, strict=True)))
            for weight, support in zip(model["weights"], model["support"], strict=True)
        )
    else:
        score = model["intercept"] + math.fsum(value * weight for value, weight in
                                               zip(scaled, model["weights"], strict=True))
    if not math.isfinite(score):
        raise ValueError("Điểm dự đoán không hữu hạn.")
    return {"status": "PREDICTED", "has_coffee": score > 0, "model": model["version"]}


def predict_trial(rows):
    try:
        model = load_model()
        signals = tuple((key, AVAILABLE_SIGNALS[key]) for key in model.get("signals", dict(SIGNALS)))
        features = extract_features(rows, signals, kinetics=model.get("feature_set") == "kinetics")
        return {**predict_features(features, model), "signals": [key for key, _ in signals]}
    except (OSError, ValueError, TypeError, KeyError, ArithmeticError) as error:
        return {"status": "UNAVAILABLE", "reason": f"Không kiểm tra được mùi cà phê. {error}"}
