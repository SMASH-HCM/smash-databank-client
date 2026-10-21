"""Portable published-catalogue fixtures; no clinical files or local drives."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from smash_hcm_databank_client.manifest import ManifestError, is_database, validate_manifest
from smash_hcm_databank_client.updates import refresh_manifest, startup_updates
from smash_hcm_databank_client.workspace import Workspace
from test_manifest_workspace import FakeClient, entry, env_file
from test_updates import Server


def catalogue(version="1.0"):
    return {"schema_version": version, "generated_utc": "2026-01-01T00:00:00Z",
            "hash_algorithm": "SHA-256", "manifest_profile": "core",
            "file_count": 1, "entries": [
                {**entry("readme/README.md"), "type": "file", "hash_source": "full_file_read"},
                {**entry("readme"), "type": "directory", "hash_scope": "sorted_direct_child_records_v1"},
            ]}


@pytest.mark.parametrize("version,expected", [(1, "1.0"), (1.0, "1.0"), ("1", "1.0"), ("1.0", "1.0"),
    ("1.0.0", "1.0.0"), ("1.1", "1.1"), ("1.10", "1.10"), ("2.0", "2.0"), (99, "99.0")])
def test_legacy_current_and_newer_compatible_versions(version, expected):
    for data in (catalogue(version), {"schema_version": version, "release": "example", "files": [entry()]}):
        assert validate_manifest(data)["schema_version"] == expected


def test_inventory_files_are_adapted_and_directory_digests_are_not_downloads():
    data = catalogue()
    db = {**entry("releases/OMOP-v2.db"), "type": "file"}
    data["entries"].append(db)
    data["database"] = {key: db[key] for key in ("path", "size_bytes", "sha256")}
    original = copy.deepcopy(data)
    result = validate_manifest(data)
    assert len(result["files"]) == 2 and len(result["directories"]) == 1
    assert result["release"] == "OMOP-v2" and is_database(result["files"][1])
    assert result["files"][0]["cohorts"] == []  # Never infer membership from paths.
    assert data == original
    assert validate_manifest(result) == result  # Canonical local-cache round trip.


@pytest.mark.parametrize("change", ["sha", "size", "algorithm", "type", "path", "layout", "hash_scope", "database"])
def test_newer_version_still_requires_compatible_integrity_fields(change):
    data = catalogue("2.0")
    if change == "sha": data["entries"][0]["sha256"] = "invalid"
    if change == "size": data["entries"][0]["size_bytes"] = True
    if change == "algorithm": data["hash_algorithm"] = "SHA-512"
    if change == "type": data["entries"][0]["type"] = "symlink"
    if change == "path": data["entries"][0]["path"] = "../escape"
    if change == "layout": data["files"] = []
    if change == "hash_scope": data["entries"][0]["hash_scope"] = "sorted_direct_child_records_v1"
    if change == "database": data["database"] = {"path": "missing.db"}
    with pytest.raises(ManifestError):
        validate_manifest(data)


def test_successful_retrieval_publishes_visible_raw_copy_after_validation(tmp_path):
    raw = json.dumps(catalogue()).encode()
    client = FakeClient({"manifest.json": raw})
    workspace = Workspace(tmp_path / "state", env_file(tmp_path), client_factory=lambda _: client)
    root = workspace.set_download_root(tmp_path / "data")
    phases = []
    result = workspace.retrieve_manifest(progress=lambda n, t, phase: phases.append(phase))
    assert result["schema_version"] == "1.0"
    assert (root / "manifest.json").read_bytes() == raw  # Preserve publisher metadata/bytes.
    assert workspace.state["manifest_version"]["cache_sha256"] == hashlib.sha256(raw).hexdigest()
    assert phases == ["validating", "complete"]
    assert workspace.manifest()["files"] == result["files"]


def test_newer_manifest_refreshes_automatically_without_changing_old_downloads(tmp_path):
    server = Server({"manifest.json": json.dumps(catalogue()).encode()})
    workspace = Workspace(tmp_path / "state", env_file(tmp_path), client_factory=lambda _: server)
    root = workspace.set_download_root(tmp_path / "data")
    refresh_manifest(workspace)
    updated = catalogue("1.1")
    updated["generated_utc"] = "2026-02-01T00:00:00Z"
    server.payloads["manifest.json"] = json.dumps(updated).encode()
    server.etag = '"new"'
    assert refresh_manifest(workspace)["status"] == "UPDATED"
    assert json.loads((root / "manifest.json").read_text())["schema_version"] == "1.1"
    assert workspace.state["downloads"] == {}  # No unconfirmed clinical transfers.
    (root / "manifest.json").unlink()
    requests = server.calls.count("manifest.json")
    assert refresh_manifest(workspace)["status"] == "UNCHANGED"
    assert server.calls.count("manifest.json") == requests and (root / "manifest.json").is_file()


def test_failed_validation_retains_both_previous_cache_and_visible_copy(tmp_path):
    server = Server({"manifest.json": json.dumps(catalogue()).encode()})
    workspace = Workspace(tmp_path / "state", env_file(tmp_path), client_factory=lambda _: server)
    root = workspace.set_download_root(tmp_path / "data")
    workspace.retrieve_manifest()
    previous = workspace.state["manifest_path"]
    raw = (root / "manifest.json").read_bytes()
    invalid = catalogue("2.0")
    invalid["entries"][0]["sha256"] = "bad"
    server.payloads["manifest.json"] = json.dumps(invalid).encode()
    server.etag = '"invalid-new-version"'
    phases = []
    with pytest.raises(ManifestError):
        workspace.retrieve_manifest(progress=lambda n, t, phase: phases.append(phase))
    assert phases == ["validating"] and workspace.state["manifest_path"] == previous
    assert (root / "manifest.json").read_bytes() == raw
    messages = []
    startup_updates(workspace, read=lambda _: "y", write=messages.append, plain=True)
    assert any("Manifest validation failed:" in message and "SHA-256" in message for message in messages)


def test_selecting_directory_after_retrieval_copies_existing_valid_manifest(tmp_path):
    raw = json.dumps(catalogue()).encode()
    workspace = Workspace(tmp_path / "state", env_file(tmp_path), client_factory=lambda _: FakeClient({"manifest.json": raw}))
    workspace.retrieve_manifest()
    root = workspace.set_download_root(tmp_path / "data")
    assert (root / "manifest.json").read_bytes() == raw


def test_unwritable_manifest_copy_does_not_discard_valid_cache(tmp_path):
    workspace = Workspace(tmp_path / "state", env_file(tmp_path), client_factory=lambda _: FakeClient({"manifest.json": json.dumps(catalogue()).encode()}))
    root = workspace.set_download_root(tmp_path / "data")
    (root / "manifest.json").mkdir()  # A directory cannot be atomically replaced with a file.
    workspace.retrieve_manifest()
    assert workspace.manifest()["schema_version"] == "1.0"
    assert workspace.manifest_copy_notice and not list(root.glob(".manifest-*.part"))
