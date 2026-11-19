"""Shared signal definitions and validity rules used by model input filtering.

Kept behavior-compatible with processing/core/signals.py from the approved
feature/frontend-ui source. Invalid and UNKNOWN values remain distinct; this
module never repairs, fills, clips, or otherwise mutates sensor readings.
"""
from __future__ import annotations

import math


CHANNELS = (
    ("tgs2602_voltage_v", "TGS2602", "V", "tgs2602"),
    ("mq135_voltage_v", "MQ135", "V", "mq135"),
    ("mq3_voltage_v", "MQ3", "V", "mq3"),
    ("mq135_1_voltage_v", "MQ135 #1", "V", "mq135_1"),
    ("mq3_1_voltage_v", "MQ3 #1", "V", "mq3_1"),
    ("mq135_2_voltage_v", "MQ135 #2", "V", "mq135_2"),
    ("mq3_2_voltage_v", "MQ3 #2", "V", "mq3_2"),
    ("gas_resistance_ohm", "BME gas", "Ω", "gas"),
    ("temperature_c", "Nhiệt độ", "°C", "environment"),
    ("humidity_pct", "Độ ẩm", "%RH", "environment"),
    ("pressure_hpa", "Áp suất", "hPa", "environment"),
)


def number(value):
    """Return a finite float, otherwise None (including NaN and infinity)."""
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def flag(value):
    """Parse a boolean flag while preserving missing/unknown as None."""
    text = str(value).strip().lower()
    if text in ("true", "1", "yes", "on"):
        return True
    if text in ("false", "0", "no", "off"):
        return False
    return None


def validity(row, key, sensor, modern):
    """Return True, False, or None using the source dataset validity contract."""
    if number(row.get(key)) is None:
        return False
    prefix = ("bme688" if modern else "bme") if sensor in ("gas", "environment") else sensor
    status = row.get(prefix + "_status", "")
    flags = [flag(row.get(prefix + "_fresh"))]
    if modern:
        flags.append(flag(row.get(prefix + "_valid")))
    if status and status != "OK":
        return False
    if sensor == "gas":
        flags.extend(flag(row.get(name)) for name in ("gas_valid", "heater_stable", "new_data"))
    if any(word in row.get(prefix + "_quality", "") for word in ("NEGATIVE", "ADC_LIMIT")):
        return False
    if False in flags:
        return False
    if not status or None in flags:
        return None
    return True
