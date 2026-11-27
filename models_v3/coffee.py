"""Coffee V3 inference, using the V2 feature contract on smoothed samples."""

from functools import lru_cache
import json

from models_v3 import COFFEE_ARTIFACT as ARTIFACT
from models_v3.smoothing import smooth
from robonose_s3 import coffee_detection as v2


def features(rows, signals, method):
    # Validate the untouched raw first, so smoothing cannot make a failed trial pass.
    original = v2.extract_features(rows, signals)
    if method == "none":
        return original
    copied = [row.copy() for row in rows]
    for phase in v2.PHASE_SPANS:
        phase_rows = [row for row in copied if row["phase"] == phase]
        times = [float(row["phase_elapsed_s"]) for row in phase_rows]
        for signal, device in signals:
            valid = [float(row[signal]) if row.get(f"{device}_status") == "OK"
                     and v2.valid_signal(row, signal)
                     and (device != "bme688" or all(row.get(flag) in v2.TRUE_FLAGS
                                                     for flag in ("heater_stable", "new_data")))
                     else None for row in phase_rows]
            for row, before, after in zip(phase_rows, valid, smooth(valid, method, times=times), strict=True):
                if after is not None and after != before:
                    row[signal] = after
    return v2.extract_features(copied, signals)


@lru_cache(maxsize=1)
def load_model():
    return json.loads(ARTIFACT.read_text(encoding="utf-8"))


def predict_trial(rows):
    try:
        model = load_model()
        signals = tuple((key, v2.AVAILABLE_SIGNALS[key]) for key in model["signals"])
        vector = features(list(rows), signals, model["smoothing"])
        return {**v2.predict_features(vector, model), "signals": model["signals"],
                "smoothing": model["smoothing"], "experimental": True}
    except (OSError, ValueError, TypeError, KeyError, ArithmeticError) as error:
        return {"status": "UNAVAILABLE", "reason": f"V3 không kiểm tra được mẫu. {error}"}
