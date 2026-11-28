"""Three coffee classifiers with a shared feature contract and JSON artifacts."""

from functools import lru_cache
import json
import math
import struct
from pathlib import Path
from statistics import fmean

from . import AVAILABLE_SIGNALS, extract_features, predict_features, _tree_score


MODEL_IDS = ("logistic", "random_forest", "svm")
SIGNAL_KEYS = ("mq3_1_voltage_v", "mq135_2_voltage_v", "mq3_2_voltage_v")
SIGNALS = tuple((key, AVAILABLE_SIGNALS[key]) for key in SIGNAL_KEYS)


def artifact_path(model):
    if model not in MODEL_IDS:
        raise ValueError("Unknown coffee classifier")
    return Path(__file__).with_name(f"ml_{model}.json")


@lru_cache(maxsize=3)
def load(model):
    return json.loads(artifact_path(model).read_text(encoding="utf-8"))


def predict_trial(rows, *, model):
    try:
        saved = load(model)
        vector = extract_features(rows, SIGNALS)
        if saved["kind"] == "random_forest":
            # Match scikit-learn's float32 input conversion for tree routing.
            vector = [struct.unpack("f", struct.pack("f", value))[0] for value in vector]
            probability = fmean(_tree_score(vector, tree) for tree in saved["trees"])
            if not math.isfinite(probability):
                raise ValueError("Non-finite forest score")
            result = {"status": "PREDICTED", "has_coffee": probability > .5,
                      "model": saved["version"]}
        else:
            result = predict_features(vector, saved)
        return {**result, "signals": list(SIGNAL_KEYS), "model_backend": saved["backend"]}
    except (OSError, ValueError, TypeError, KeyError, ArithmeticError) as error:
        return {"status": "UNAVAILABLE", "reason": str(error)}
