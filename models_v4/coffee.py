"""Coffee inference using an ensemble of logistic branches."""

from functools import lru_cache
import json
import math

from models_v3.coffee import features
from models_v4 import COFFEE_ARTIFACT
from robonose_s3.coffee_detection import AVAILABLE_SIGNALS, extract_features


BRANCHES = {
    "v1_channels": ("none", ("gas_resistance_ohm", "mq3_1_voltage_v"), False),
    "v2_channels": ("none", ("mq3_1_voltage_v", "mq135_2_voltage_v", "mq3_2_voltage_v"), False),
    "v3_smoothed": ("light3", ("mq3_1_voltage_v", "mq135_2_voltage_v", "mq3_2_voltage_v"), False),
    "v2_kinetics": ("none", ("tgs2602_voltage_v", "mq3_1_voltage_v", "mq135_2_voltage_v", "mq3_2_voltage_v"), True),
}


def extract(rows, branch):
    smoothing, keys, kinetics = BRANCHES[branch]
    signals = tuple((key, AVAILABLE_SIGNALS[key]) for key in keys)
    if kinetics:
        return extract_features(rows, signals, kinetics=True)
    return features(rows, signals, smoothing)


def logit(vector, model):
    return model["intercept"] + math.fsum(
        weight * (value - center) / scale
        for value, center, scale, weight in zip(vector, model["mean"], model["scale"], model["weights"], strict=True)
    )


@lru_cache(maxsize=1)
def load():
    saved = json.loads(COFFEE_ARTIFACT.read_text(encoding="utf-8"))
    if saved["schema"] != 1:
        raise ValueError("Schema model cà phê V4 không tương thích.")
    return saved


def predict_trial(rows):
    try:
        model = load()
        rows = list(rows)
        logits = {branch: logit(extract(rows, branch), model["branches"][branch])
                  for branch, weight in model["fusion_weights"].items() if weight}
        score = math.fsum(model["fusion_weights"][branch] * value for branch, value in logits.items())
        if not math.isfinite(score):
            raise ValueError("Điểm V4 không hữu hạn.")
        return {"status": "PREDICTED", "has_coffee": score > 0, "model": model["version"],
                "logit": score, "branch_logits": logits, "fusion_weights": model["fusion_weights"],
                "signals": list(dict.fromkeys(key for branch in logits for key in BRANCHES[branch][1])),
                "experimental": True}
    except (OSError, ValueError, TypeError, KeyError, ArithmeticError) as error:
        return {"status": "UNAVAILABLE", "reason": f"V4 không kiểm tra được mẫu. {error}"}
