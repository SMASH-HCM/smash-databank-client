import subprocess
import sys

import pytest

from smash_hcm_databank_client.cli import main
from smash_hcm_databank_client.database_artifacts import database_format
from smash_hcm_databank_client.download_flow import download
from smash_hcm_databank_client.manifest import artifact_type
from smash_hcm_databank_client.menu_ui import actions
from test_download_flow import answers, item, workspace


def test_published_event_and_report_bundles_are_downloadable_without_database(tmp_path):
    entries = [
        item("releases/events.zip", ["FLORENCE-TRAIN"], kind="event-stream", variable_groups=["shared-clinical"]),
        item("releases/reports.zip", kind="report"),
    ]
    state, server = workspace(tmp_path, entries)
    assert not state.database_available()
    selected = {action.key: action for action in actions(state)}
    assert selected["22"].enabled and selected["23"].enabled
    assert not any(action.group == "Local OMOP" for action in selected.values())
    events = download(state, "events", answers("2", "all", "c", str(tmp_path / "data"), "y"), lambda _: None, True)
    reports = download(state, "reports", answers("all", "y"), lambda _: None, True)
    assert len(events) == len(reports) == 1
    assert server.calls == ["releases/events.zip", "releases/reports.zip"]
    assert all(row["status"] == "PASS" for row in state.verify_local())


def test_individual_dataset_companions_do_not_duplicate_default_bundle_selection():
    assert artifact_type({**item("train.csv"), "kind": "dataset-file"}) == "other"


@pytest.mark.parametrize("command", ["export", "report", "cohorts", "publish"])
def test_analysis_commands_have_moved_out_of_client(command):
    with pytest.raises(SystemExit) as exc:
        main([command])
    assert exc.value.code == 2


def test_client_imports_no_database_drivers_or_analysis_modules():
    code = "import smash_hcm_databank_client.cli,sys; assert 'sqlite3' not in sys.modules; assert 'psycopg' not in sys.modules; assert 'smash_hcm_databank_client.database' not in sys.modules"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_sqlite_release_is_explicitly_unsupported(tmp_path):
    path = tmp_path / "temporary.db"
    path.write_bytes(b"SQLite format 3\x00" + b"0" * 50)
    with pytest.raises(ValueError, match="SQLite is unsupported"):
        database_format(path)
