import math

import pytest

from omop_exporter.assets import resolve_asset, validate_asset
from omop_exporter.database import sha256
from omop_exporter.policies import eligible_history, ensure_disjoint_partitions, numeric_summary, safe_numeric_mean


def test_strict_boundary_lookback_and_missing_dates():
    rows = [{"event_date": day} for day in ("2020-01-01", "2020-12-31", "2021-01-01", "2021-01-02", "")]
    assert eligible_history(rows, "2021-01-01", lookback_days=1) == [{"event_date": "2020-12-31"}]
    assert len(eligible_history(rows, "2021-01-01", lookback_days=1, include_index_day=True)) == 2
    with pytest.raises(ValueError):
        eligible_history(rows, "2021-01-01", lookback_days=0)


@pytest.mark.parametrize("units,reason", [([8582, 0], "unknown_unit"), ([8582, 8583], "unit_conflict"), ([None, None], "unknown_unit")])
def test_unit_ambiguity_suppresses_mean(units, reason):
    result = safe_numeric_mean([{"value_as_number": value, "unit_concept_id": unit} for value, unit in zip([10, 100], units)])
    assert result == {"value": None, "reason": reason}


def test_valid_zero_and_explicit_dimensionless_values():
    assert safe_numeric_mean([{"value_as_number": 0, "unit_concept_id": 8582}])["value"] == 0
    assert safe_numeric_mean([{"value_as_number": 2}], dimensionless=True)["value"] == 2
    assert safe_numeric_mean([{"value_as_number": math.inf, "unit_concept_id": 8582}])["reason"] == "nonfinite_value"


def test_iqr_is_not_min_max_and_missingness_is_counted():
    result = numeric_summary([0, 1, 2, 3, 100, None, math.nan])
    assert (result["q1"], result["median"], result["q3"], result["iqr"]) == (1, 2, 3, 2)
    assert result["min"] == 0 and result["max"] == 100
    assert result["n"] == 5 and result["missing"] == 2
    assert result["mean"] == 21.2
    assert numeric_summary([1])["sd"] is None
    assert numeric_summary([])["iqr"] is None


def test_repeated_landmarks_stay_with_patient():
    ensure_disjoint_partitions({"train": [1, 1, 2], "test": [3]})
    with pytest.raises(ValueError, match="more than one"):
        ensure_disjoint_partitions({"train": [1, 2], "test": [2]})


@pytest.mark.parametrize("relative", ["../escape", "/absolute", "C:/escape", "C:escape", "\\\\server\\share", "", ".", "folder/../../escape"])
def test_unsafe_asset_paths_fail(tmp_path, relative):
    with pytest.raises(ValueError):
        resolve_asset(tmp_path, relative)


def test_asset_bytes_size_and_hash(tmp_path):
    path = tmp_path / "signal.bin"
    path.write_bytes(b"synthetic signal")
    row = {"asset_id": "fixture", "relative_path": path.name, "size_bytes": path.stat().st_size, "sha256": sha256(path)}
    assert validate_asset(tmp_path, row)["checksum_verified"]
    with pytest.raises(ValueError, match="checksum"):
        validate_asset(tmp_path, {**row, "sha256": "0" * 64})
    with pytest.raises(ValueError, match="size"):
        validate_asset(tmp_path, {**row, "size_bytes": 1})


def test_missing_asset_fails(tmp_path):
    with pytest.raises(FileNotFoundError):
        resolve_asset(tmp_path, "missing.bin")
