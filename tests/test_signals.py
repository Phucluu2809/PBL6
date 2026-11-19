import math

import pytest

from robonose_s3.signals import flag, number, validity


@pytest.mark.parametrize("value", [None, "", "abc", math.nan, math.inf, -math.inf])
def test_number_rejects_missing_invalid_and_nonfinite(value):
    assert number(value) is None


@pytest.mark.parametrize("value", ["true", "1", "YES", " on "])
def test_flag_true_spellings(value):
    assert flag(value) is True


@pytest.mark.parametrize("value", ["false", "0", "NO", " off "])
def test_flag_false_spellings(value):
    assert flag(value) is False


def modern_row(sensor="tgs2602"):
    return {"value": "1.25", f"{sensor}_status": "OK",
            f"{sensor}_fresh": "true", f"{sensor}_valid": "true"}


def test_modern_validity_preserves_true_false_and_unknown():
    row = modern_row()
    assert validity(row, "value", "tgs2602", True) is True
    row["tgs2602_valid"] = "false"
    assert validity(row, "value", "tgs2602", True) is False
    row["tgs2602_valid"] = ""
    assert validity(row, "value", "tgs2602", True) is None


@pytest.mark.parametrize("quality", ["NEGATIVE", "ADC_LIMIT", "OK;ADC_LIMIT"])
def test_quality_faults_are_invalid(quality):
    row = modern_row(); row["tgs2602_quality"] = quality
    assert validity(row, "value", "tgs2602", True) is False


def test_modern_bme_gas_requires_all_source_flags():
    row = {"value": "20000", "bme688_status": "OK", "bme688_fresh": "true",
           "bme688_valid": "true", "gas_valid": "true", "heater_stable": "true",
           "new_data": "true"}
    assert validity(row, "value", "gas", True) is True
    row["heater_stable"] = "false"
    assert validity(row, "value", "gas", True) is False


def test_legacy_bme_uses_bme_prefix_and_does_not_require_valid_flag():
    row = {"value": "40", "bme_status": "OK", "bme_fresh": "true"}
    assert validity(row, "value", "environment", False) is True
