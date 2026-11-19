import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from robonose_s3.rescnn64 import MODEL_CHANNELS, ResCNN64Predictor, TrialResolver, prepare_trial


def write_trial(folder, trial_id="11111111-1111-4111-8111-111111111111", *, exposure_rows=120):
    folder.mkdir(parents=True)
    metadata = {
        "schema": "robonose.dataset.v1",
        "status": "COMPLETE",
        "trial_id": trial_id,
        "session_id": "22222222-2222-4222-8222-222222222222",
        "started_at": "2026-11-19T08:00:00+07:00",
    }
    (folder / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    fields = ["schema", "mono_s", "phase", "context_straddled",
              *(key for key, _ in MODEL_CHANNELS),
              *(f"{sensor}_{suffix}" for sensor in ("tgs2602", "mq3_1", "mq135_2", "mq3_2", "bme688")
                for suffix in ("status", "fresh", "valid")),
              "gas_valid", "heater_stable", "new_data"]
    bases = [1.0, 2.0, 3.0, 4.0, 10000.0, 55.0]
    with (folder / "raw.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fields)
        writer.writeheader()
        for index in range(60 + exposure_rows):
            phase = "BASELINE" if index < 60 else "EXPOSURE"
            offset = 0 if phase == "BASELINE" else index - 60
            values = bases if phase == "BASELINE" else [
                base * (1.1 + offset / 10000) for base in bases]
            row = {"schema": "robonose.dataset.v1", "mono_s": index, "phase": phase,
                   "context_straddled": False, "gas_valid": True,
                   "heater_stable": True, "new_data": True}
            row.update(dict(zip((key for key, _ in MODEL_CHANNELS), values)))
            for sensor in ("tgs2602", "mq3_1", "mq135_2", "mq3_2", "bme688"):
                row.update({f"{sensor}_status": "OK", f"{sensor}_fresh": True,
                            f"{sensor}_valid": True})
            writer.writerow(row)
    return folder


def test_prepare_trial_reproduces_six_by_120_contract_without_mutating_raw(tmp_path):
    folder = write_trial(tmp_path / "trial")
    raw = folder / "raw.csv"
    before = hashlib.sha256(raw.read_bytes()).hexdigest()
    tensor, info = prepare_trial(folder)
    assert tensor.shape == (6, 120) and tensor.dtype == np.float32
    assert np.isclose(tensor[0, 0], 0.1)
    assert np.isclose(tensor[4, 0], np.log(1.1))
    assert info["trial_id"] == "11111111-1111-4111-8111-111111111111"
    assert info["warnings"] == []
    assert hashlib.sha256(raw.read_bytes()).hexdigest() == before


def test_prepare_trial_rejects_wrong_phase_count(tmp_path):
    folder = write_trial(tmp_path / "trial", exposure_rows=119)
    with pytest.raises(ValueError, match="expected 120 rows"):
        prepare_trial(folder)


def test_prepare_trial_does_not_infer_missing_model_compatibility(tmp_path):
    folder = write_trial(tmp_path / "trial")
    with pytest.raises(ValueError, match="metadata.config is missing"):
        prepare_trial(folder, compatibility={"sampling_hz": 1})


def test_trial_resolver_accepts_only_unique_full_uuid_inside_root(tmp_path):
    trial_id = "11111111-1111-4111-8111-111111111111"
    folder = write_trial(tmp_path / "root" / "person" / "trial", trial_id)
    resolver = TrialResolver([tmp_path / "root"])
    assert resolver.resolve(trial_id) == folder.resolve()
    with pytest.raises(ValueError, match="full trial UUID"):
        resolver.resolve("../trial")
    write_trial(tmp_path / "root" / "duplicate", trial_id)
    with pytest.raises(ValueError, match="duplicated"):
        resolver.resolve(trial_id)


def test_imported_model_artifact_hashes_and_uncalibrated_status():
    model_dir = Path(__file__).resolve().parents[1] / "models/rescnn64/20261119_053351_6b8717"
    artifact = json.loads((model_dir / "artifact.json").read_text(encoding="utf-8"))
    assert artifact["unknown_calibration"]["status"] == "NOT_CALIBRATED"
    for name, expected in artifact["files"].items():
        assert hashlib.sha256((model_dir / name).read_bytes()).hexdigest().upper() == expected


def test_real_predictor_refuses_one_sided_threshold_before_loading_torch(tmp_path):
    model_dir = Path(__file__).resolve().parents[1] / "models/rescnn64/20261119_053351_6b8717"
    with pytest.raises(ValueError, match="supplied together"):
        ResCNN64Predictor(model_dir, [tmp_path], similarity_threshold=0.5)
