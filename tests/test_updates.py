import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from omop_exporter.manifest import validate_manifest
from omop_exporter.nextcloud import NextcloudError
from omop_exporter.updates import apply_update, check_updates, refresh_manifest, startup_updates, update_candidates
from omop_exporter.workspace import Workspace, default_state_dir, default_env_file
from test_manifest_workspace import FakeClient, entry, env_file, manifest_file


class Server(FakeClient):
    def __init__(self, payloads):
        super().__init__(payloads)
        self.etag = '"v1"'
        self.failed = False
        self.authentication = True

    def check(self):
        self.calls.append("check")
        if not self.authentication:
            raise NextcloudError("Synthetic login failure", status_code=401)
        return {"status": "PASS"}

    def stat(self, remote):
        self.calls.append("stat:" + remote)
        return {"etag": self.etag, "is_directory": False, "size_bytes": len(self.payloads[remote])}

    def download(self, remote, destination, *args, **kwargs):
        if self.failed:
            raise NextcloudError("Synthetic transfer failure")
        result = super().download(remote, destination, *args, **kwargs)
        result["etag"] = self.etag
        (Path(destination) / "download_receipt.json").write_text(json.dumps(result))
        return result


def configured(tmp_path, old=b"old", path="cohort.zip", **tags):
    old_entry = entry(path, old, artifact_id="cohort-ecg", **tags)
    manifest = {"schema_version": 1, "release": "v1", "files": [old_entry]}
    server = Server({path: old, "manifest.json": json.dumps(manifest).encode()})
    workspace = Workspace(tmp_path / "state", env_file(tmp_path), client_factory=lambda config: server)
    workspace.set_download_root(tmp_path / "data")
    workspace.retrieve_manifest()
    workspace.download_entry(workspace.manifest()["files"][0])
    return workspace, server


def publish(workspace, server, payload=b"new", path="cohort.zip", **tags):
    new_entry = entry(path, payload, artifact_id="cohort-ecg", **tags)
    server.payloads[path] = payload
    server.payloads["manifest.json"] = json.dumps({"schema_version": 1, "release": "v2", "files": [new_entry]}).encode()
    server.etag = '"v2"'
    refresh_manifest(workspace)
    return update_candidates(workspace)[0]


@pytest.mark.parametrize("retention", ["keep", "archive", "replace"])
def test_changed_artifact_path_is_matched_and_old_retention_is_explicit(tmp_path, retention):
    workspace, server = configured(tmp_path)
    old = Path(workspace.state["downloads"]["cohort.zip"]["local_path"])
    candidate = publish(workspace, server, path="v2/cohort.zip")
    result = apply_update(workspace, candidate, retention)
    assert Path(result["local_path"]).read_bytes() == b"new"
    assert "cohort.zip" not in workspace.state["downloads"]
    assert not update_candidates(workspace)
    history = workspace.state["download_history"][0]
    if retention == "keep":
        assert old.read_bytes() == b"old" and history["status"] == "kept"
    elif retention == "archive":
        assert not old.exists() and Path(history["record"]["local_path"]).read_bytes() == b"old"
        assert history["status"] == "archived"
        assert any(row["reference"] == "version history" and row["status"] == "PASS" for row in workspace.verify_local())
    else:
        assert not old.exists() and history["status"] == "deleted"
    assert (old.parent / "download_receipt.json").exists()  # No directory deletion.


def test_failed_download_preserves_old_file_receipt_and_manifest(tmp_path):
    workspace, server = configured(tmp_path)
    candidate = publish(workspace, server)
    original = dict(workspace.state["downloads"])
    server.failed = True
    with pytest.raises(NextcloudError):
        apply_update(workspace, candidate, "replace")
    assert workspace.state["downloads"] == original
    assert Path(candidate["old_record"]["local_path"]).read_bytes() == b"old"
    assert workspace.state["download_history"][0]["status"] == "kept"


def test_modified_local_file_cannot_be_deleted_but_can_be_archived(tmp_path):
    workspace, server = configured(tmp_path)
    candidate = publish(workspace, server)
    old = Path(candidate["old_record"]["local_path"])
    old.write_bytes(b"user-modified")
    with pytest.raises(NextcloudError, match="modified"):
        apply_update(workspace, candidate, "replace")
    assert old.read_bytes() == b"user-modified"
    apply_update(workspace, candidate, "archive")
    assert Path(workspace.state["download_history"][0]["record"]["local_path"]).read_bytes() == b"user-modified"


def test_outside_file_is_never_retired(tmp_path):
    workspace, server = configured(tmp_path)
    candidate = publish(workspace, server)
    external = tmp_path / "external.zip"
    external.write_bytes(b"old")
    candidate["old_record"]["local_path"] = str(external)
    workspace.state["downloads"][candidate["old_remote"]] = candidate["old_record"]
    with pytest.raises(NextcloudError, match="outside"):
        apply_update(workspace, candidate, "replace")
    assert external.read_bytes() == b"old"


def test_etag_unchanged_uses_verified_cache_and_corrupt_cache_refetches(tmp_path):
    workspace, server = configured(tmp_path)
    downloads = server.calls.count("manifest.json")
    assert refresh_manifest(workspace)["status"] == "UNCHANGED"
    assert server.calls.count("manifest.json") == downloads
    Path(workspace.state["manifest_path"]).write_text("invalid")
    assert refresh_manifest(workspace)["status"] == "FIRST"
    assert server.calls.count("manifest.json") == downloads + 1


def test_invalid_manifest_keeps_previous_cache(tmp_path):
    workspace, server = configured(tmp_path)
    previous = workspace.state["manifest_path"]
    server.etag = '"bad"'
    server.payloads["manifest.json"] = b'{"schema_version":99}'
    with pytest.raises(NextcloudError):
        refresh_manifest(workspace)
    assert workspace.state["manifest_path"] == previous and workspace.manifest()["release"] == "v1"


def test_changed_checksum_is_detected_even_with_unchanged_release_name(tmp_path):
    workspace, server = configured(tmp_path)
    publish(workspace, server)
    manifest = json.loads(server.payloads["manifest.json"])
    manifest["release"] = "v1"
    server.payloads["manifest.json"] = json.dumps(manifest).encode()
    server.etag = '"v3"'
    refresh_manifest(workspace)
    assert len(update_candidates(workspace)) == 1


def test_missing_file_is_offered_for_repair(tmp_path):
    workspace, server = configured(tmp_path)
    Path(workspace.state["downloads"]["cohort.zip"]["local_path"]).unlink()
    candidate = update_candidates(workspace)[0]
    assert candidate["reason"] == "missing or size changed"
    assert apply_update(workspace, candidate, "archive")["retention"] == "missing"


def test_no_guessed_match_for_renamed_legacy_artifact(tmp_path):
    workspace, server = configured(tmp_path)
    workspace.state["downloads"]["cohort.zip"].pop("artifact_id")
    server.payloads["manifest.json"] = json.dumps({"schema_version": 1, "release": "v2", "files": [entry("different/cohort.zip", b"new")]}).encode()
    server.etag = '"v2"'
    refresh_manifest(workspace)
    assert not update_candidates(workspace)


def test_startup_checks_login_but_declining_update_fetches_no_manifest(tmp_path):
    workspace, server = configured(tmp_path)
    server.calls.clear()
    messages = []
    startup_updates(workspace, read=lambda prompt: "n", write=messages.append, plain=True)
    assert server.calls == ["check"] and workspace.connection_status is True
    assert any("PASS" in line for line in messages)


def test_invalid_login_does_not_fetch_manifest_or_prompt(tmp_path):
    workspace, server = configured(tmp_path)
    server.authentication = False
    server.calls.clear()
    startup_updates(workspace, read=lambda prompt: pytest.fail("Unexpected prompt"), write=lambda value: None)
    assert server.calls == ["check"] and workspace.connection_status is False


def test_no_login_keeps_local_tools_available_without_network(tmp_path):
    workspace = Workspace(tmp_path / "state", tmp_path / "absent.env", client_factory=lambda config: pytest.fail("Unexpected network"))
    startup_updates(workspace, read=lambda prompt: pytest.fail("Unexpected prompt"), write=lambda value: None)


def test_startup_404_retains_cache_and_reports_access_separately(tmp_path, monkeypatch):
    workspace, server = configured(tmp_path)
    previous = workspace.state["manifest_path"]
    monkeypatch.setattr("omop_exporter.updates.refresh_manifest", lambda *args, **kwargs: (_ for _ in ()).throw(NextcloudError("Missing", status_code=404)))
    messages = []
    startup_updates(workspace, read=lambda prompt: "y", write=messages.append, plain=True)
    assert workspace.connection_status is True and workspace.state["manifest_path"] == previous
    assert any("HTTP 404" in line for line in messages)


def test_cancel_update_selection_never_downloads_data(tmp_path):
    workspace, server = configured(tmp_path)
    publish(workspace, server)
    server.calls.clear()
    check_updates(workspace, read=lambda prompt: "0", write=lambda value: None, plain=True)
    assert "cohort.zip" not in server.calls


def test_update_flow_requires_final_replace_confirmation(tmp_path):
    workspace, server = configured(tmp_path)
    publish(workspace, server)
    supplied = iter(["all", "3", "n"])
    server.calls.clear()
    check_updates(workspace, read=lambda prompt: next(supplied), write=lambda value: None, plain=True)
    assert "cohort.zip" not in server.calls
    assert Path(workspace.state["downloads"]["cohort.zip"]["local_path"]).read_bytes() == b"old"


def test_new_database_is_validated_before_retiring_active_old_database(tmp_path, omop_path):
    workspace, server = configured(tmp_path, old=omop_path.read_bytes(), path="OMOP.db", kind="database")
    selected = workspace.state["active_db"]
    candidate = publish(workspace, server, b"not SQLite", "OMOP.db", kind="database")
    with pytest.raises(ValueError, match="SQLite"):
        apply_update(workspace, candidate, "replace")
    assert workspace.state["active_db"] == selected and Path(selected).exists()
    assert workspace.state["downloads"]["OMOP.db"] == candidate["old_record"]


def test_valid_database_update_activates_new_copy_and_keeps_archived_old(tmp_path, omop_path):
    workspace, server = configured(tmp_path, old=omop_path.read_bytes(), path="OMOP.db", kind="database")
    old = workspace.state["active_db"]
    with sqlite3.connect(omop_path) as connection:
        connection.execute("INSERT INTO concept VALUES (999,'new metadata')")
    candidate = publish(workspace, server, omop_path.read_bytes(), "v2/OMOP.db", kind="database")
    result = apply_update(workspace, candidate, "archive")
    assert workspace.state["active_db"] == result["local_path"] != old
    assert Path(workspace.state["download_history"][0]["record"]["local_path"]).exists()


@pytest.mark.parametrize("identity", ["../bad", "", "a b", None])
def test_bad_artifact_ids_rejected(identity):
    with pytest.raises(NextcloudError, match="artifact_id"):
        validate_manifest({"schema_version": 1, "release": "v1", "files": [entry(artifact_id=identity)]})


def test_duplicate_artifact_ids_rejected():
    with pytest.raises(NextcloudError, match="artifact_id"):
        validate_manifest({"schema_version": 1, "release": "v1", "files": [entry("a", artifact_id="same"), entry("b", artifact_id="same")]})


def test_python_default_state_uses_home_with_legacy_checkout_compatibility(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    assert default_state_dir() == tmp_path / "home/.smash/omop-exporter"
    assert default_env_file() == default_state_dir() / ".env"
    (tmp_path / ".smash").mkdir()
    (tmp_path / ".smash/state.json").write_text("{}")
    (tmp_path / ".env").write_text("OTHER=fixture")
    assert default_state_dir() == Path(".smash") and default_env_file() == Path(".env")


def test_interruption_after_new_receipt_keeps_durable_old_reference(tmp_path, monkeypatch):
    workspace, server = configured(tmp_path)
    candidate = publish(workspace, server)
    download = workspace.download_entry
    def interrupted(*args, **kwargs):
        download(*args, **kwargs)
        raise SystemExit("Synthetic interruption")
    monkeypatch.setattr(workspace, "download_entry", interrupted)
    with pytest.raises(SystemExit):
        apply_update(workspace, candidate, "replace")
    reopened = Workspace(workspace.root, workspace.env_file)
    journal = reopened.state["download_history"][0]
    assert journal["status"] == "update-pending"
    assert Path(journal["record"]["local_path"]).read_bytes() == b"old"
    assert Path(reopened.state["downloads"]["cohort.zip"]["local_path"]).read_bytes() == b"new"
    assert any("update-pending" in row["path"] for row in reopened.verify_local())


def test_first_successful_startup_downloads_manifest_after_yes(tmp_path):
    manifest = {"schema_version": 1, "release": "first", "files": []}
    server = Server({"manifest.json": json.dumps(manifest).encode()})
    workspace = Workspace(tmp_path / "state", env_file(tmp_path), client_factory=lambda config: server)
    startup_updates(workspace, read=lambda prompt: "y", write=lambda value: None, plain=True)
    assert workspace.manifest()["release"] == "first"
    assert server.calls[0] == "check" and server.calls.count("manifest.json") == 1


def test_menu_runs_startup_flow_after_initial_setup(tmp_path, monkeypatch):
    from omop_exporter.menu import run_menu
    monkeypatch.setattr("omop_exporter.menu.native_vault", lambda: (_ for _ in ()).throw(NextcloudError("No vault")))
    seen = []
    monkeypatch.setattr("omop_exporter.menu.startup_updates", lambda workspace, *args: seen.append(workspace.session.username))
    workspace = Workspace(tmp_path / "state", tmp_path / "missing.env")
    supplied = iter(["fixture", "2", "6"])
    assert run_menu(workspace, initial_setup=True, read=lambda prompt: next(supplied), password_read=lambda prompt: "fake-password", write=lambda value: None, plain=True) == 0
    assert seen == ["fixture"]
