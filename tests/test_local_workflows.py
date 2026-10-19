import csv
import io
import json
from pathlib import Path
import shutil
import sqlite3

import pytest

from smash_hcm_databank_client.cli import main
from smash_hcm_databank_client.database import OmopDatabase
from smash_hcm_databank_client.features import load_variable_set, resolve_variables, save_variable_set
from smash_hcm_databank_client.local_tools import export_cohorts, select_variables
from smash_hcm_databank_client.menu import run_menu
from smash_hcm_databank_client.menu_ui import actions
from smash_hcm_databank_client.presentation import status_panel
from smash_hcm_databank_client.progress import DownloadProgress
from smash_hcm_databank_client.reports import summary_report, write_report
from smash_hcm_databank_client.workspace import Workspace
from test_download_flow import answers


def test_confirmed_directory_is_created_and_persisted_without_secrets(tmp_path):
    state = Workspace(tmp_path / "state", tmp_path / "absent.env")
    state.refresh_local()
    assert "<unset>" in status_panel(state) and not state.root.exists()
    chosen = tmp_path / "data"
    state.set_download_root(chosen)
    restored = Workspace(state.root, state.env_file)
    restored.refresh_local()
    assert restored.state["download_root"] == str(chosen) and chosen.is_dir()
    assert "[OK]" in next(row for row in status_panel(restored).splitlines() if "Local directory:" in row)
    assert "password" not in (state.root / "state.json").read_text()


def test_startup_recovers_old_confirmed_but_uncreated_directory(tmp_path):
    state = Workspace(tmp_path / "state", tmp_path / "absent.env")
    state.state["download_root"] = str(tmp_path / "not-yet-created")
    state.state["download_roots"] = [state.state["download_root"]]
    state.save()
    restored = Workspace(state.root, state.env_file)
    restored.refresh_local()
    assert Path(restored.state["download_root"]).is_dir()


def test_startup_discovers_only_valid_unique_db_in_saved_download_layout(tmp_path, omop_path):
    state = Workspace(tmp_path / "state", tmp_path / "absent.env")
    data = state.set_download_root(tmp_path / "data")
    destination = data / "v1.4" / "OMOP-123"
    destination.mkdir(parents=True)
    candidate = destination / "OMOP.db"
    shutil.copyfile(omop_path, candidate)
    (data / "corrupt.db").write_text("bad")
    unrelated = data / "unrelated.sqlite"
    with sqlite3.connect(unrelated) as db:
        db.execute("CREATE TABLE harmless (value TEXT)")
    restored = Workspace(state.root, state.env_file)
    restored.refresh_local()
    assert restored.database_available() and restored.state["active_db"] == str(candidate)
    assert Workspace(state.root, state.env_file).database_available()


def test_multiple_databases_require_choice_and_do_not_enable_local_tools(tmp_path, omop_path):
    state = Workspace(tmp_path / "state", tmp_path / "absent.env")
    root = state.set_download_root(tmp_path / "data")
    for name in ("a.db", "b.db"):
        shutil.copyfile(omop_path, root / name)
    state.refresh_local()
    assert not state.database_available() and "Multiple" in state.discovery_message
    assert all(not item.enabled for item in actions(state) if item.group == "Local OMOP")
    state.register_database(root / "a.db")
    assert all(item.enabled for item in actions(state) if item.group == "Local OMOP")
    (root / "a.db").write_text("corrupt")
    assert all(not item.enabled for item in actions(state) if item.group == "Local OMOP")


def test_summary_reports_are_aggregate_and_missing_endpoints_are_explicit(database, tmp_path):
    cohorts = summary_report(database, "cohorts")
    assert cohorts["cohorts"][0]["patients"] == 2
    endpoints = summary_report(database, "endpoints")
    assert endpoints["status"] == "PASS"
    assert any(row["status"] == "not_ascertained" for row in endpoints["endpoints"])
    assert all("person_id" not in row for row in endpoints["endpoints"])
    write_report(database, "inventory", tmp_path / "report")
    assert (tmp_path / "report/columns.csv").exists() and (tmp_path / "report/cohorts.csv").exists()
    with sqlite3.connect(database.path) as writer:
        # Close the read transaction before changing the fixture.
        database.connection.rollback()
        writer.execute("DELETE FROM smash_endpoint_event")
    assert summary_report(database, "endpoints")["status"] == "UNAVAILABLE"


def test_distributions_use_observations_and_keep_units_separate(omop_path):
    with sqlite3.connect(omop_path) as writer:
        writer.executescript("INSERT INTO measurement VALUES (80,1,10,'2020-02-01',30,NULL,8582),(81,1,10,'2020-03-01',100,NULL,999);")
    with OmopDatabase(omop_path) as database:
        report = summary_report(database, "distributions")
    florence = [row for row in report["distributions"] if row["concept_id"] == 10 and row["site"] == "FLORENCE"]
    assert len(florence) == 2
    known = next(row for row in florence if row["unit_concept_id"] == 8582)
    assert known["n"] == 2 and known["mean"] == 20 and known["iqr"] == 10
    assert known["min"] == 10 and known["max"] == 30


def test_ecg_preset_selects_measurements_and_excludes_ecg_diagnoses(omop_path):
    with sqlite3.connect(omop_path) as writer:
        writer.executescript("INSERT INTO concept VALUES (4088512,'QRS complex duration'),(900,'ECG diagnosis'); INSERT INTO measurement VALUES (90,1,4088512,'2020-01-01',80,NULL,8582); INSERT INTO condition_occurrence VALUES (90,1,900,'2020-01-01');")
    with OmopDatabase(omop_path) as database:
        assert resolve_variables(database, "ecg-derived") == [("measurement", 4088512)]
        assert all(table == "measurement" for table, _ in resolve_variables(database, "measurements"))


def test_custom_list_save_load_is_exact_deduplicated_and_never_overwritten(database, tmp_path):
    path = tmp_path / "chosen.json"
    save_variable_set(path, database, [("measurement", 11), ("measurement", 10), ("measurement", 10)], "My model")
    data = load_variable_set(path)
    assert data["name"] == "My model" and data["keys"] == [("measurement", 10), ("measurement", 11)]
    with pytest.raises(FileExistsError):
        save_variable_set(path, database, "all")


@pytest.mark.parametrize("row", [{"table": "person", "concept_id": 10}, {"table": "measurement", "concept_id": True}, {"table": "measurement", "concept_id": -1}, {"concept_id": 10}])
def test_invalid_saved_lists_are_rejected(tmp_path, row):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"schema_version": 1, "name": "bad", "variables": [row]}))
    with pytest.raises(ValueError):
        load_variable_set(path)


@pytest.mark.parametrize("fmt,filename", [("tabular", "data.csv"), ("events", "omop_events.csv")])
def test_multi_cohort_exports_share_frozen_features_and_use_memberships(database, tmp_path, fmt, filename):
    output = tmp_path / "batch"
    keys = [("measurement", 10), ("measurement", 11)]
    result = export_cohorts(database, output, [1, 2], keys, fmt)
    assert result["cohorts"] == 2
    expected = []
    for cohort, people in [(1, {"1", "4"}), (2, {"2"})]:
        folder = output / ("cohort-" + str(cohort))
        assert load_variable_set(folder / "variable_set.json")["keys"] == keys
        with (folder / filename).open() as handle:
            reader = csv.DictReader(handle)
            expected.append(reader.fieldnames)
            assert {row["person_id"] for row in reader}.issubset(people)
    assert expected[0] == expected[1]


def test_failed_batch_does_not_publish_partial_cohorts(database, tmp_path):
    output = tmp_path / "batch"
    with pytest.raises(ValueError, match="Unknown"):
        export_cohorts(database, output, [1, "imaginary"], "core", "tabular")
    assert not output.exists()


def test_custom_ui_saves_and_reuses_selection(database, tmp_path):
    state = Workspace(tmp_path / "state", tmp_path / "absent.env")
    output = []
    keys = select_variables(state, database, answers("1", "Common numeric", "2", "Chosen"), output.append, True, custom_only=True)
    assert keys == [("measurement", 10)]
    assert len(list((state.root / "variable_sets").glob("*.json"))) == 1
    from smash_hcm_databank_client.features import PRESETS
    restored = select_variables(state, database, answers(str(len(PRESETS) + 1)), output.append, True)
    assert resolve_variables(database, restored) == keys


def test_local_report_menu_works_offline_without_manifest(tmp_path, omop_path):
    state = Workspace(tmp_path / "state", tmp_path / "absent.env", db_path=omop_path)
    output = []
    assert run_menu(state, read=answers("3", "2", "2", "n", "6"), write=output.append, plain=True) == 0
    assert any("Cohort membership summary" in line for line in output)
    assert any("FLORENCE-TRAIN" in line for line in output)


def test_saved_features_work_through_installed_cli(database, tmp_path, capsys):
    path = tmp_path / "variables.json"
    save_variable_set(path, database, [("measurement", 10)])
    assert main(["export", "--db", str(database.path), "--format", "tabular", "--cohort", "FLORENCE-TRAIN", "--variables-file", str(path), "--out", str(tmp_path / "out")]) == 0
    assert load_variable_set(tmp_path / "out/variable_set.json")["keys"] == [("measurement", 10)]
    assert main(["report", "endpoints", "--db", str(database.path), "--out", str(tmp_path / "report")]) == 0


def test_progress_handles_unknown_total_and_failure_without_false_completion():
    stream = io.StringIO()
    with DownloadProgress("manifest.json", stream=stream, clock=lambda: 1) as progress:
        progress(0, None)
        progress(100, None, "complete")
    assert "size unknown" in stream.getvalue() and "complete" in stream.getvalue()
    stream = io.StringIO()
    with pytest.raises(ValueError):
        with DownloadProgress("ecg.zip", stream=stream) as progress:
            progress(10, 100)
            raise ValueError("incomplete")
    assert "FAILED" in stream.getvalue() and " complete" not in stream.getvalue()
