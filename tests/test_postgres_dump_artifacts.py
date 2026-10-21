import hashlib
import json
from pathlib import Path

import pytest

from smash_hcm_databank_client.cli import main
from smash_hcm_databank_client.database_artifacts import database_format, validate_dump
from smash_hcm_databank_client.menu_ui import actions
from smash_hcm_databank_client.presentation import status_panel
from smash_hcm_databank_client.updates import apply_update
from smash_hcm_databank_client.workspace import Workspace
from test_manifest_workspace import FakeClient, entry, env_file, manifest_file
from test_updates import configured, publish


# A signature fixture, deliberately not presented as a restorable clinical DB.
DUMP = b"PGDMP\x01\x0e\x00\x04\x08\x01\x01" + b"synthetic archive payload"


@pytest.mark.parametrize("payload,kind", [(DUMP, "postgres-custom"), (b"--\n-- PostgreSQL database dump\n--\n", "postgres-sql"), (b"--\r\n-- PostgreSQL database dump\r\n--\r\n", "postgres-sql")])
def test_dump_signature_is_independent_of_db_extension(tmp_path, payload, kind):
    path = tmp_path / "SMASH_v1.4_rc5.db"
    path.write_bytes(payload)
    assert database_format(path) == kind
    result = validate_dump(path, hashlib.sha256(payload).hexdigest(), len(payload))
    assert result["status"] == "PASS" and result["database_format"] == kind
    assert result["checks"][-1]["status"] == "NOT_CHECKED"
    assert "no restore" in result["scope"]


@pytest.mark.parametrize("payload", [b"PGDMP", b"unrecognized file", b""])
def test_invalid_or_truncated_dump_is_rejected(tmp_path, payload):
    path = tmp_path / "OMOP.db"
    path.write_bytes(payload)
    with pytest.raises(ValueError, match="PostgreSQL"):
        database_format(path)


def test_download_registers_and_caches_pg_dump_without_sqlite_or_psycopg(tmp_path, monkeypatch):
    server = FakeClient({"SMASH_v1.4_rc5.db": DUMP})
    workspace = Workspace(tmp_path / "state", env_file(tmp_path), client_factory=lambda config: server)
    workspace.use_manifest(manifest_file(tmp_path, [entry("SMASH_v1.4_rc5.db", DUMP, kind="database")]))
    def forbidden(*args):
        pytest.fail("PostgreSQL dump must never be opened as SQLite")
    phases = []
    downloaded = workspace.download_entry(workspace.manifest()["files"][0], lambda n, total, phase: phases.append(phase))
    assert phases == ["validating", "complete"]
    assert workspace.state["active_db"] == downloaded["local_path"]
    assert workspace.database_available() and workspace.database_is_dump()
    assert "PostgreSQL dump" in status_panel(workspace, 100)
    assert next(item for item in actions(workspace) if item.key == "12").enabled
    assert not any(item.group == "Local OMOP" for item in actions(workspace))
    assert workspace.verify_local()[0]["status"] == "PASS"
    assert workspace.download_entry(workspace.manifest()["files"][0])["status"] == "CACHED"
    assert server.calls == ["SMASH_v1.4_rc5.db"]


def test_startup_recovers_previous_successful_transfer_without_receipt(tmp_path):
    workspace = Workspace(tmp_path / "state", tmp_path / "absent.env")
    root = workspace.set_download_root(tmp_path / "data")
    directory = root / "release" / "artifact-123"
    directory.mkdir(parents=True)
    path = directory / "SMASH_v1.4_rc5.db"
    path.write_bytes(DUMP)
    reopened = Workspace(workspace.root, workspace.env_file)
    reopened.refresh_local()
    assert reopened.state["active_db"] == str(path)
    assert reopened.database_available()
    assert "SMASH_v1.4_rc5" in reopened.database_info()


def test_corrupt_dump_never_reports_complete_or_replaces_selected_db(tmp_path):
    workspace, server = configured(tmp_path, old=DUMP, path="OMOP.db", kind="database")
    old = workspace.state["active_db"]
    candidate = publish(workspace, server, b"PGDMP", "OMOP.db", kind="database")
    phases = []
    with pytest.raises(ValueError, match="truncated"):
        apply_update(workspace, candidate, "replace", lambda n, total, phase: phases.append(phase))
    assert "complete" not in phases
    assert workspace.state["active_db"] == old and Path(old).read_bytes() == DUMP
    assert workspace.state["downloads"]["OMOP.db"] == candidate["old_record"]


def test_dump_updates_archive_old_and_select_new_after_verification(tmp_path):
    workspace, server = configured(tmp_path, old=DUMP, path="OMOP.db", kind="database")
    candidate = publish(workspace, server, DUMP + b"new", "v2/OMOP.db", kind="database")
    result = apply_update(workspace, candidate, "archive")
    assert workspace.state["active_db"] == result["local_path"]
    history = workspace.state["download_history"][0]
    assert history["status"] == "archived" and Path(history["record"]["local_path"]).read_bytes() == DUMP


def test_dump_cli_validation_and_analysis_restore_message(tmp_path, capsys):
    path = tmp_path / "SMASH_v1.4_rc5.db"
    path.write_bytes(DUMP)
    assert main(["validate", "--db", str(path), "--sha256", hashlib.sha256(DUMP).hexdigest()]) == 0
    assert json.loads(capsys.readouterr().out)["database_format"] == "postgres-custom"
    assert main(["validate", "--db", str(path), "--sha256", "0" * 64]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "FAIL"
    with pytest.raises(SystemExit) as exc:
        main(["report", "inventory", "--db", str(path)])
    assert exc.value.code == 2


def test_validate_menu_uses_dump_receipt_without_opening_sqlite(tmp_path, monkeypatch):
    from menu_helpers import dispatch_menu
    workspace, server = configured(tmp_path, old=DUMP, path="OMOP.db", kind="database")
    def forbidden(*args):
        pytest.fail("Dump validation must not call SQLite")
    messages, supplied = [], iter(["12", "0"])
    dispatch_menu(workspace, read=lambda prompt: next(supplied), write=messages.append)
    assert "Database validation: PASS" in messages
    assert "PASS | expected_sha256" in messages and "PASS | expected_size" in messages
    assert any("NOT_CHECKED | restored_omop_schema" in line for line in messages)
