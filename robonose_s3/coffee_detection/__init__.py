"""Binary coffee detection from a completed RoboNose S3 sensor trial."""

from functools import lru_cache
import json
import math
from pathlib import Path
from statistics import fmean, median, quantiles

from ..schema import valid_signal


PHASE_SPANS = {"BASELINE": 50, "EXPOSURE": 105}
SIGNALS = (("gas_resistance_ohm", "bme688"), ("mq3_1_voltage_v", "mq3_1"))
TRUE_FLAGS = (True, "True", "true", 1, "1")


def extract_features(rows):
    phases = {phase: [] for phase in PHASE_SPANS}
    for row in rows:
        if row["phase"] in phases:
            phases[row["phase"]].append(row)

    features = []
    for signal, device in SIGNALS:
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
    return features


@lru_cache(maxsize=1)
def load_model():
    path = Path(__file__).with_name("model.json")
    return json.loads(path.read_text(encoding="utf-8"))


def predict_features(features, model=None):
    if not all(map(math.isfinite, features)):
        raise ValueError("Đặc trưng cảm biến không hữu hạn.")
    model = load_model() if model is None else model
    score = model["intercept"] + math.fsum(
        (value - center) / scale * weight for value, center, scale, weight in
        zip(features, model["mean"], model["scale"], model["weights"], strict=True)
    )
    if not math.isfinite(score):
        raise ValueError("Điểm dự đoán không hữu hạn.")
    return {"status": "PREDICTED", "has_coffee": score > 0, "model": model["version"]}


def predict_trial(rows):
    try:
        features = extract_features(rows)
    except (ValueError, TypeError, KeyError) as error:
        return {"status": "UNAVAILABLE", "reason": f"Dữ liệu cảm biến không hợp lệ. {error}"}
    try:
        return predict_features(features)
    except (OSError, ValueError, TypeError, KeyError, ArithmeticError) as error:
        return {"status": "UNAVAILABLE", "reason": f"Không chạy được model cà phê. {error}"}
