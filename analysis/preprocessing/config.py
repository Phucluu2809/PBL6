from __future__ import annotations

from dataclasses import dataclass


CORE_PHASES = ("BASELINE", "EXPOSURE", "RECOVERY")
PHASE_LENGTHS = {"BASELINE": 60, "EXPOSURE": 120, "RECOVERY": 60}
PHASE_OFFSETS = {"BASELINE": 0, "EXPOSURE": 60, "RECOVERY": 180}


@dataclass(frozen=True)
class SignalConfig:
    key: str
    label: str
    unit: str
    color: str
    status_prefix: str
    kind: str
    smooth_window: int


SIGNALS = (
    SignalConfig("tgs2602_voltage_v", "A0 — TGS2602", "V", "#2563eb", "tgs2602", "gas", 7),
    SignalConfig("mq3_1_voltage_v", "A1 — MQ3-1", "V", "#dc2626", "mq3_1", "gas", 7),
    SignalConfig("mq135_2_voltage_v", "A2 — MQ135-2", "V", "#16a34a", "mq135_2", "gas", 7),
    SignalConfig("mq3_2_voltage_v", "A3 — MQ3-2", "V", "#9333ea", "mq3_2", "gas", 7),
    SignalConfig("gas_resistance_ohm", "BME688 gas", "kΩ", "#ea580c", "bme688", "gas", 7),
    SignalConfig("temperature_c", "BME688 nhiệt độ", "°C", "#b91c1c", "bme688", "environment", 11),
    SignalConfig("humidity_pct", "BME688 độ ẩm", "%", "#7c3aed", "bme688", "environment", 11),
    SignalConfig("pressure_hpa", "BME688 áp suất", "hPa", "#0891b2", "bme688", "environment", 11),
)

HAMPEL_WINDOW = 7
HAMPEL_THRESHOLD = 3.5
SAVGOL_POLYORDER = 2
MAX_INTERPOLATION_GAP = 3

MIN_COVERAGE_PASS = 0.95
MIN_COVERAGE_REVIEW = 0.90
MAX_GAP_PASS = 2.0
MAX_GAP_REVIEW = 3.0
MAX_BASELINE_CV_PASS = 1.0
MAX_BASELINE_CV_REVIEW = 2.0
MAX_BASELINE_DRIFT_PASS = 2.0
MAX_BASELINE_DRIFT_REVIEW = 5.0
MAX_OUTLIER_FRACTION_PASS = 0.02
MAX_OUTLIER_FRACTION_REVIEW = 0.05
