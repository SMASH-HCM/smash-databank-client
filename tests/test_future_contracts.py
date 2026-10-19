"""Baseline contracts promoted from planned specifications to passing tests."""
import csv

import pytest


def future_export_wide():
    try:
        from smash_hcm_databank_client.tabular import export_wide
    except ModuleNotFoundError as exc:
        if exc.name != "smash_hcm_databank_client.tabular":
            raise RuntimeError("A dependency of the planned exporter is missing") from exc
        raise
    return export_wide


def test_future_wide_export_retains_all_missing_people(database, tmp_path):
    export_wide = future_export_wide()
    out = tmp_path / "wide"
    export_wide(database, out, cohort="florence_train", variables=[("measurement", 10)], index="baseline")
    with (out / "data.csv").open() as handle:
        rows = list(csv.DictReader(handle))
    assert {row["person_id"] for row in rows} == {"1", "4"}
    assert next(row for row in rows if row["person_id"] == "4")["measurement__10"] == ""
    assert "event_date" not in rows[0]  # One baseline row, rather than a long fact table.


def test_future_wide_schema_does_not_shrink_on_absent_site_variable(database, tmp_path):
    export_wide = future_export_wide()
    out = tmp_path / "rennes"
    export_wide(database, out, cohort="rennes_all", variables=[("measurement", 10), ("measurement", 12)], index="baseline", tabular_mode="latest-history", lookback_days=1826)
    with (out / "data.csv").open() as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["measurement__12"] == ""
    assert rows[0]["measurement__10"] == "20.0"


def test_future_rolling_export_rejects_pilot_holdout(database, tmp_path):
    export_wide = future_export_wide()
    with pytest.raises(ValueError, match="training"):
        export_wide(database, tmp_path / "holdout", cohort="tampere_pilot", variables=[("measurement", 10)], index="annual")
