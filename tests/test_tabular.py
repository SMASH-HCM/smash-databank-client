import csv
import json
import sqlite3

import pytest

from smash_hcm_databank_client.database import OmopDatabase
from smash_hcm_databank_client.exports import export_events
from smash_hcm_databank_client.tabular import export_wide as _export_wide
from functools import partial

# This suite retains the explicit historical/as-of contract. Exact-day defaults
# are exercised separately in test_snapshot_contract.py.
export_wide = partial(_export_wide, tabular_mode="latest-history", lookback_days=1826)


def rows(path):
    with path.open() as handle:
        return list(csv.DictReader(handle))


def test_core_baseline_retains_missing_people_and_separates_metadata(database, tmp_path):
    result = export_wide(database, tmp_path / "wide", "florence_train")
    data = rows(tmp_path / "wide/data.csv")
    assert result == {"format": "tabular", "rows": 2, "variables": 1}
    assert data[0]["measurement__10"] == "10.0"
    assert data[1]["measurement__10"] == ""
    assert not {"event_date", "event_observed", "censor_date"}.intersection(data[0])
    manifest = json.loads((tmp_path / "wide/dataset_manifest.json").read_text())
    assert len(manifest["variable_set_sha256"]) == 64
    assert manifest["availability_policy"] == "post-assessment"


def test_strict_before_control_excludes_same_day_and_future(omop_path, tmp_path):
    with sqlite3.connect(omop_path) as connection:
        connection.execute("INSERT INTO measurement VALUES(90,1,10,'2021-01-01',999,NULL,8582)")
        connection.execute("INSERT INTO measurement VALUES(91,1,10,'2021-01-02',888,NULL,8582)")
    with OmopDatabase(omop_path) as database:
        export_wide(database, tmp_path / "wide", 1, availability_policy="strict-before")
    assert rows(tmp_path / "wide/data.csv")[0]["measurement__10"] == "10.0"


@pytest.mark.parametrize("value,unit,reason", [(20, 0, "unknown_unit"), (20, 8583, "unit_conflict"), (99, 8582, "conflicting_latest_values")])
def test_unsafe_numeric_values_are_blank_with_qc_reason(omop_path, tmp_path, value, unit, reason):
    with sqlite3.connect(omop_path) as connection:
        connection.execute("INSERT INTO measurement VALUES(90,1,10,'2020-01-01',?,NULL,?)", (value, unit))
    with OmopDatabase(omop_path) as database:
        export_wide(database, tmp_path / "wide", 1)
    assert rows(tmp_path / "wide/data.csv")[0]["measurement__10"] == ""
    assert rows(tmp_path / "wide/feature_provenance.csv")[0]["qc_reason"] == reason


def test_cross_site_unit_conflict_is_not_refitted_per_export(omop_path, tmp_path):
    with sqlite3.connect(omop_path) as connection:
        connection.execute("UPDATE measurement SET unit_concept_id=8583 WHERE person_id=2 AND measurement_concept_id=10")
    with OmopDatabase(omop_path) as database:
        export_wide(database, tmp_path / "wide", 1)
    assert rows(tmp_path / "wide/data.csv")[0]["measurement__10"] == ""


def test_presence_only_features_do_not_manufacture_negative_answers(database, tmp_path):
    export_wide(database, tmp_path / "wide", 1, variables=[("condition_occurrence", 10)])
    data = rows(tmp_path / "wide/data.csv")
    assert data[0]["condition_occurrence__10"] == "1"
    assert data[1]["condition_occurrence__10"] == ""


def test_partial_database_without_anchors_fails_without_output(omop_path, tmp_path):
    with sqlite3.connect(omop_path) as connection:
        connection.execute("DELETE FROM smash_endpoint_censor")
    with OmopDatabase(omop_path) as database:
        with pytest.raises(ValueError, match="baseline anchors"):
            export_wide(database, tmp_path / "out", 1)
    assert not (tmp_path / "out").exists()


def test_event_export_core_filter_is_table_specific(database, tmp_path):
    result = export_events(database, tmp_path / "events", "florence_train", variables="core")
    data = rows(tmp_path / "events/omop_events.csv")
    assert result["rows"] == 1
    assert data[0]["domain"] == "measurement" and data[0]["concept_id"] == "10"


def test_annual_indexes_are_explicitly_unsupported(database, tmp_path):
    with pytest.raises(ValueError, match="Annual training indexes"):
        export_wide(database, tmp_path / "out", 1, index="annual")
