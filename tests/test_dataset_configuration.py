import csv
import json
import sqlite3

import pytest

from smash_hcm_databank_client.cli import main
from smash_hcm_databank_client.database import OmopDatabase
from smash_hcm_databank_client.datasets import export_dataset
from smash_hcm_databank_client.exports import export_events
from smash_hcm_databank_client.features import load_variable_set, resolve_variables
from smash_hcm_databank_client.reports import summary_report, write_data_report
from smash_hcm_databank_client.tabular import export_wide


def rows(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_standard_layout_shared_schema_split_membership_and_no_overwrite(omop_path, tmp_path):
    with sqlite3.connect(omop_path) as connection:
        connection.executescript("INSERT INTO cohort_definition VALUES (4,'SHaRe Pilot'); INSERT INTO cohort VALUES (4,4); UPDATE cohort SET subject_id=1 WHERE cohort_definition_id=1; UPDATE cohort_definition SET cohort_definition_name='SHaRe Training' WHERE cohort_definition_id=1;")
    with OmopDatabase(omop_path) as database:
        result = export_dataset(database, tmp_path / "data", [1, 4], "minimal-measurements")
        train, test = tmp_path / "data/FLORENCE/train.csv", tmp_path / "data/FLORENCE/test.csv"
        assert train.exists() and test.exists()
        assert {r["person_id"] for r in rows(train)} == {"1"}
        assert {r["person_id"] for r in rows(test)} == {"4"}
        assert list(rows(train)[0]) == list(rows(test)[0]) and len(rows(train)[0]) == 12
        manifest = json.loads((tmp_path / "data/FLORENCE/test/dataset_manifest.json").read_text())
        assert manifest["source_cohort_name"] == "SHaRe Pilot" and "../test.csv" in manifest["output_sha256"]
        before = train.read_bytes()
        with pytest.raises(FileExistsError):
            export_dataset(database, tmp_path / "data", [1], "core")
        assert train.read_bytes() == before
        assert result["rows"] == 2


def test_standard_event_paths_and_failed_batch_do_not_publish(database, tmp_path):
    root = tmp_path / "data"
    export_dataset(database, root, [1, 2], "core", "events", domains=["measurement"])
    assert (root / "event_stream/FLORENCE-TRAIN/omop_events.csv").exists()
    assert (root / "event_stream/RENNES-ALL/omop_events.csv").exists()
    with pytest.raises(ValueError):
        export_dataset(database, root / "failed", [1, "unknown"], "core")
    assert not list((root / "failed").rglob("*.csv"))


def test_distinct_pilot_and_test_are_never_merged(omop_path, tmp_path):
    with sqlite3.connect(omop_path) as connection:
        connection.executescript("INSERT INTO cohort_definition VALUES (4,'TAMPERE TEST'); INSERT INTO cohort VALUES (4,1);")
    with OmopDatabase(omop_path) as database:
        with pytest.raises(FileExistsError, match="collide"):
            export_dataset(database, tmp_path / "data", [3, 4], "core")
        assert not list((tmp_path / "data").rglob("*.csv"))


def test_history_features_use_distinct_valid_dates_never_future_or_categories(omop_path, tmp_path):
    with sqlite3.connect(omop_path) as connection:
        connection.executescript("""
          DELETE FROM measurement WHERE person_id=1;
          INSERT INTO measurement VALUES (101,1,10,'2021-01-01',30,NULL,8582), (102,1,10,'2020-12-30',20,NULL,8582),
          (103,1,10,'2020-12-30',20,NULL,8582), (104,1,10,'2020-12-20',10,NULL,8582),
          (105,1,10,'2021-01-02',999,NULL,8582), (106,1,11,'2020-12-30',NULL,123,NULL);
        """)
    with OmopDatabase(omop_path) as database:
        export_wide(database, tmp_path / "out", 1, [("measurement", 10), ("measurement", 11)],
                    tabular_mode="latest-history", lookback_days=30,
                    history_features=["previous-value", "previous-age-days", "last-age-days", "count", "mean", "min", "max"])
    row = rows(tmp_path / "out/data.csv")[0]
    assert row["measurement__10"] == "30.0"
    assert row["measurement__10__previous_value"] == "20.0" and row["measurement__10__previous_age_days"] == "2"
    assert row["measurement__10__last_age_days"] == "0" and row["measurement__10__count"] == "3"
    assert row["measurement__10__mean"] == "20.0" and row["measurement__10__max"] == "30.0"
    assert row["measurement__11__mean"] == "" and row["measurement__11"] == "123"


def test_conflicting_previous_day_is_not_replaced_by_an_older_valid_value(omop_path, tmp_path):
    with sqlite3.connect(omop_path) as connection:
        connection.executescript("INSERT INTO measurement VALUES (101,1,10,'2021-01-01',30,NULL,8582),(102,1,10,'2020-12-31',20,NULL,8582),(103,1,10,'2020-12-31',21,NULL,8582);")
    with OmopDatabase(omop_path) as database:
        export_wide(database, tmp_path / "out", 1, [("measurement", 10)], tabular_mode="latest-history", lookback_days=400, history_features=["previous-value", "mean"])
    row = rows(tmp_path / "out/data.csv")[0]
    assert row["measurement__10__previous_value"] == ""
    assert row["measurement__10__mean"] == "20.0"  # two valid dates: 10 and 30


def test_derived_history_is_explicit_only(database, tmp_path):
    with pytest.raises(ValueError, match="History features"):
        export_wide(database, tmp_path / "out", 1, "core", history_features=["mean"])
    assert not (tmp_path / "out").exists()


def test_family_union_preserves_rare_grades_unknowns_and_frozen_mapping(omop_path, tmp_path):
    with sqlite3.connect(omop_path) as connection:
        connection.executescript("""
          INSERT INTO concept VALUES (3654726,'Mild mitral valve regurgitation'),(3654728,'Severe mitral valve regurgitation');
          INSERT INTO condition_occurrence VALUES (101,1,3654726,'2020-11-01'),(102,2,3654726,'2020-11-01'),
          (103,3,3654726,'2020-11-01'),(104,1,3654728,'2020-12-01');
        """)
    with OmopDatabase(omop_path) as database:
        export_wide(database, tmp_path / "family", 1, "core-consolidated", tabular_mode="latest-history", lookback_days=90)
        saved = load_variable_set(tmp_path / "family/variable_set.json")
        export_wide(database, tmp_path / "reuse", 1, saved, tabular_mode="latest-history", lookback_days=90)
    assert (tmp_path / "family/data.csv").read_bytes() == (tmp_path / "reuse/data.csv").read_bytes()
    a, b = rows(tmp_path / "family/data.csv")
    assert a["mitral_regurgitation_grade"] == "severe" and b["mitral_regurgitation_grade"] == ""
    assert "condition_occurrence__3654726" not in a
    assert ("condition_occurrence", 3654728) in saved["keys"]


def test_family_does_not_bypass_same_day_mask_or_resolve_conflicts(omop_path, tmp_path):
    with sqlite3.connect(omop_path) as connection:
        connection.executescript("INSERT INTO condition_occurrence VALUES (101,1,3654726,'2021-01-01'),(102,1,3654728,'2021-01-01');")
    with OmopDatabase(omop_path) as database:
        export_wide(database, tmp_path / "same-day", 1, "core-consolidated")
    assert rows(tmp_path / "same-day/data.csv")[0]["mitral_regurgitation_grade"] == ""


def test_event_baseline_boundary_mask_domain_and_metadata(omop_path, tmp_path):
    with sqlite3.connect(omop_path) as connection:
        connection.executescript("""
          INSERT INTO measurement VALUES (101,1,10,'2021-01-01',30,NULL,8582),(102,1,10,'2021-01-02',999,NULL,8582);
          CREATE TABLE drug_exposure (drug_exposure_id INTEGER,person_id INTEGER,drug_concept_id INTEGER,drug_exposure_start_date TEXT);
          INSERT INTO drug_exposure VALUES (1,1,100,'2021-01-01'),(2,1,100,'2020-12-31');
        """)
    with OmopDatabase(omop_path) as database:
        export_events(database, tmp_path / "baseline", 1, time_scope="baseline", event_lookback_days=7, include_metadata=True)
        export_events(database, tmp_path / "full", 1, domains=["measurement"], date_start="2021-01-02")
    baseline = rows(tmp_path / "baseline/omop_events.csv")
    assert len(baseline) == 2 and {r["domain"] for r in baseline} == {"measurement", "drug"}
    assert all(float(r["days_before_baseline"]) >= 0 for r in baseline)
    assert {r["event_date"] for r in rows(tmp_path / "full/omop_events.csv")} == {"2021-01-02"}
    manifest = json.loads((tmp_path / "baseline/dataset_manifest.json").read_text())
    assert manifest["availability_policy"] and manifest["excluded_events"]


@pytest.mark.parametrize("options", [{"time_scope": "invalid"}, {"domains": ["death"]}, {"event_lookback_days": 1}, {"date_start": "2021-01-02", "date_end": "2020-01-01"}])
def test_invalid_event_configuration_creates_no_output(database, tmp_path, options):
    with pytest.raises(ValueError):
        export_events(database, tmp_path / "out", 1, **options)
    assert not (tmp_path / "out").exists()


def test_patient_report_rows_observation_ages_files_and_unknown_training_indices(omop_path, tmp_path):
    with sqlite3.connect(omop_path) as connection:
        connection.executescript("""
          CREATE TABLE observation_period (person_id INTEGER,observation_period_start_date TEXT,observation_period_end_date TEXT);
          INSERT INTO observation_period VALUES (1,'2020-01-02','2021-01-01'),(1,'2021-02-01','2022-01-01');
          CREATE TABLE visit_occurrence (person_id INTEGER,visit_occurrence_id INTEGER);
          INSERT INTO visit_occurrence VALUES (1,1),(1,2);
          CREATE TABLE associated_file (associated_file_id INTEGER,person_id INTEGER,modality TEXT,filepath TEXT);
          INSERT INTO associated_file VALUES (1,1,'ECG','private/ecg'),(2,1,'MR','private/mri'),(3,1,'ECHO','private/echo');
        """)
    with OmopDatabase(omop_path) as database:
        report = write_data_report(database, "patients", tmp_path / "data")
    assert len(report["patients"]) == 4
    row = report["patients"][0]
    assert row["observation_start_date"] == "2020-01-02" and row["observation_period_count"] == 2
    assert abs(row["observation_start_age"] - 49) < .01
    assert row["visit_count"] == 2 and row["logged_file_count"] == 3 and row["logged_mri_file_count"] == 1
    assert row["training_index_count"] is None and row["endpoint_overall_status"] == "positive"
    assert report["patients"][1]["logged_file_count"] == 0
    assert (tmp_path / "data/reports/patients.csv").exists() and (tmp_path / "data/reports/patients.txt").exists()
    assert "private/" not in json.dumps(report)
    with pytest.raises(FileExistsError):
        with OmopDatabase(omop_path) as database:
            write_data_report(database, "patients", tmp_path / "data")


def test_missing_catalogue_and_visits_are_unknown_not_zero(database):
    row = summary_report(database, "patients")["patients"][0]
    assert row["visit_count"] is None and row["logged_file_count"] is None


def test_cli_standard_paths_and_options(omop_path, tmp_path):
    root = tmp_path / "data"
    assert main(["export", "--db", str(omop_path), "--format", "tabular", "--cohort", "1", "--vars", "core", "--data-dir", str(root)]) == 0
    assert (root / "FLORENCE/train.csv").exists()
    assert main(["export", "--db", str(omop_path), "--format", "events", "--cohort", "2", "--event-scope", "baseline", "--event-lookback-days", "400", "--domains", "measurement", "--include-event-metadata", "--data-dir", str(root)]) == 0
    assert (root / "event_stream/RENNES-ALL/omop_events.csv").exists()
    assert main(["report", "features", "--db", str(omop_path), "--data-dir", str(root)]) == 0
    assert (root / "reports/features.csv").exists()


def test_named_measurement_sets_and_catalogue(database):
    assert resolve_variables(database, "core-measurements") == [("measurement", 10)]
    assert len(resolve_variables(database, "minimal-measurements")) == 8
    assert summary_report(database, "features")["sets"]


@pytest.mark.parametrize("fmt", ["snapshot", "history", "events"])
def test_menu_configuration_reaches_standard_output(omop_path, tmp_path, fmt):
    from smash_hcm_databank_client.local_tools import export_menu
    from smash_hcm_databank_client.workspace import Workspace
    root = tmp_path / "data"
    workspace = Workspace(tmp_path / "state", tmp_path / "absent.env", db_path=omop_path)
    if fmt == "snapshot":
        supplied = ["1", "1", "1", "1", str(root), "y"]
        output = root / "FLORENCE/train.csv"
    elif fmt == "history":
        supplied = ["1", "1", "1", "2", "400", "1,2,4,5", "1", str(root), "y"]
        output = root / "FLORENCE/train.csv"
    else:
        supplied = ["1", "1", "2", "2", "2", "400", "1", "", "", "y", str(root), "y"]
        output = root / "event_stream/FLORENCE-TRAIN/omop_events.csv"
    supplied = iter(supplied)
    messages = []
    export_menu(workspace, read=lambda prompt: next(supplied), write=messages.append, plain=True)
    assert output.exists() and any("Export complete" in line for line in messages)
    if fmt == "history":
        assert "measurement__10__mean" in rows(output)[0]
    elif fmt == "events":
        assert "source_value" in rows(output)[0]
