import hashlib
import json
from pathlib import Path

import pytest

from smash_hcm_databank_client.manifest import select_files, validate_manifest
from smash_hcm_databank_client.nextcloud import NextcloudError
from smash_hcm_databank_client.settings import SMASH_URL
from smash_hcm_databank_client.workspace import Workspace


def entry(path="README.md", payload=b"fixture", **tags):
    return {"path": path, "size_bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest(), **tags}


def manifest_file(tmp_path, files):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"schema_version": 1, "release": "fixture-v1", "files": files}))
    return path


def env_file(tmp_path):
    path = tmp_path / ".env"
    path.write_text("NEXTCLOUD_URL=" + SMASH_URL + "\nNEXTCLOUD_USERNAME=fixture\nNEXTCLOUD_PASSWORD='fake-password'\n")
    return path


class FakeClient:
    def __init__(self, payloads):
        self.payloads = payloads
        self.calls = []

    def download(self, remote, destination, expected_sha256=None, max_bytes=None, expected_size=None, progress=None):
        payload = self.payloads[remote]
        checksum = hashlib.sha256(payload).hexdigest()
        assert expected_sha256 is None or checksum == expected_sha256
        assert expected_size is None or len(payload) == expected_size
        assert max_bytes is None or len(payload) <= max_bytes
        destination = Path(destination)
        destination.mkdir(parents=True)
        (destination / Path(remote).name).write_bytes(payload)
        self.calls.append(remote)
        if progress:
            progress(len(payload), len(payload), "complete")
        return {"sha256": checksum, "size_bytes": len(payload)}


@pytest.mark.parametrize("change", [
    {"path": "../secret"}, {"path": "https://other.example/file"}, {"size_bytes": -1},
    {"size_bytes": True}, {"sha256": "missing"}, {"cohorts": [None]}, {"modalities": 1},
])
def test_invalid_manifest_entry_rejected(change):
    with pytest.raises(NextcloudError):
        validate_manifest({"schema_version": 1, "release": "fixture", "files": [{**entry(), **change}]})


def test_exclusive_filters_do_not_infer_test_subset_from_all_archive():
    data = validate_manifest({"schema_version": 1, "release": "v1", "files": [
        entry("rennes-all.zip", cohorts=["rennes_all"], modality="ecg"),
        entry("rennes-test.npz", cohort="rennes_test", modality="ecg", variable_groups=["core"]),
        entry("OMOP.db", kind="database"),
    ]})
    assert [item["path"] for item in select_files(data, cohort="RENNES-TEST", modality="ecg")] == ["rennes-test.npz"]
    assert len(select_files(data, variable_group="core")) == 1
    assert select_files(data, databases=True)[0]["path"] == "OMOP.db"
    assert not select_files(data, cohort="florence_test")


def test_duplicate_manifest_paths_rejected():
    with pytest.raises(NextcloudError):
        validate_manifest({"schema_version": 1, "release": "v1", "files": [entry(), entry()]})


def test_manifest_download_cache_integrity_and_repair(tmp_path):
    payload = b"fixture"
    data = {"schema_version": 1, "release": "fixture-v1", "files": [entry(payload=payload)]}
    client = FakeClient({"manifest.json": json.dumps(data).encode(), "README.md": payload})
    workspace = Workspace(tmp_path / "state", env_file(tmp_path), client_factory=lambda config: client)
    manifest = workspace.retrieve_manifest()
    result = workspace.download_entry(manifest["files"][0])
    path = Path(result["local_path"])
    assert path.read_bytes() == payload
    assert workspace.verify_local()[0]["status"] == "PASS"
    assert workspace.download_entry(manifest["files"][0])["status"] == "CACHED"
    assert client.calls.count("README.md") == 1
    path.write_bytes(b"tampered")
    assert workspace.verify_local()[0]["status"] == "FAIL"
    repaired = workspace.download_entry(manifest["files"][0])
    assert repaired["local_path"] != str(path)
    assert path.read_bytes() == b"tampered"  # Original damaged file was not overwritten.
    assert workspace.verify_local()[0]["status"] == "PASS"


def test_database_download_registers_and_displays_release(tmp_path, omop_path):
    payload = omop_path.read_bytes()
    source = manifest_file(tmp_path, [entry("OMOP.db", payload, kind="database")])
    client = FakeClient({"OMOP.db": payload})
    workspace = Workspace(tmp_path / "state", env_file(tmp_path), client_factory=lambda config: client)
    workspace.use_manifest(source)
    workspace.download_entry(workspace.manifest()["files"][0])
    assert "fixture-v1" in workspace.database_info()
    assert "OMOP.db" in workspace.database_info()
    reopened = Workspace(tmp_path / "state", tmp_path / "missing.env")
    assert reopened.state["active_db"] == workspace.state["active_db"]
    assert reopened.verify_local()[0]["status"] == "PASS"


def test_local_database_and_manifest_do_not_need_credentials(tmp_path, omop_path):
    workspace = Workspace(tmp_path / "state", tmp_path / "missing.env")
    workspace.register_database(omop_path)
    assert "OMOP.db" in workspace.database_info()
    assert workspace.verify_local()[0]["status"] == "NO EXPECTED CHECKSUM"
    with pytest.raises(NextcloudError, match="No credentials"):
        workspace.client()


def test_cache_reference_cannot_escape_workspace(tmp_path):
    workspace = Workspace(tmp_path / "state", tmp_path / "missing.env")
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"private")
    workspace.state["downloads"]["file"] = {"local_path": str(outside), "size_bytes": 7, "sha256": hashlib.sha256(b"private").hexdigest()}
    assert workspace.verify_local()[0]["status"] == "FAIL"


def test_manifest_selection_cannot_replace_trusted_hash(tmp_path):
    workspace = Workspace(tmp_path / "state", tmp_path / "missing.env")
    workspace.use_manifest(manifest_file(tmp_path, [entry()]))
    with pytest.raises(NextcloudError, match="does not match"):
        workspace.download_entry({**entry(), "sha256": "0" * 64})


def test_verify_existing_folder_against_manifest_without_login(tmp_path):
    workspace = Workspace(tmp_path / "state", tmp_path / "missing.env")
    workspace.use_manifest(manifest_file(tmp_path, [entry()]))
    folder = tmp_path / "existing-data"
    folder.mkdir()
    (folder / "README.md").write_bytes(b"fixture")
    assert workspace.verify_folder(folder)[0]["status"] == "PASS"
    (folder / "README.md").write_bytes(b"tampered")
    assert workspace.verify_folder(folder)[0]["status"] == "FAIL"


def test_menu_download_database_then_export_core_baseline(tmp_path, omop_path):
    from menu_helpers import dispatch_menu as run_menu
    payload = omop_path.read_bytes()
    client = FakeClient({"OMOP.db": payload})
    workspace = Workspace(tmp_path / "state", env_file(tmp_path), client_factory=lambda config: client)
    workspace.use_manifest(manifest_file(tmp_path, [entry("OMOP.db", payload, kind="database")]))
    output, selected = [], iter(["5", "1", "c", str(tmp_path / "data"), "y", "9", "1", "1", "1", "1", str(tmp_path / "export"), "y", "0"])
    assert run_menu(workspace, read=lambda prompt: next(selected), write=output.append) == 0
    assert (tmp_path / "export/FLORENCE/train.csv").exists()
    assert any("Export complete: 2 rows" in line for line in output)
    assert any("fixture-v1" in line for line in output)


def test_menu_cohort_modality_download_does_not_extract_archive(tmp_path):
    from menu_helpers import dispatch_menu as run_menu
    payload = b"synthetic archive bytes"
    client = FakeClient({"rennes_ecg.zip": payload})
    workspace = Workspace(tmp_path / "state", env_file(tmp_path), client_factory=lambda config: client)
    workspace.use_manifest(manifest_file(tmp_path, [entry("rennes_ecg.zip", payload, cohorts=["rennes_all"], modality="ecg")]))
    selected = iter(["6", "1", "1", "c", str(tmp_path / "data"), "y", "0"])
    assert run_menu(workspace, read=lambda prompt: next(selected), write=lambda value: None) == 0
    assert client.calls == ["rennes_ecg.zip"]
    assert len(list((tmp_path / "data").rglob("rennes_ecg.zip"))) == 1


@pytest.mark.parametrize("version", [True, False, 0, 0.9, "v1.0", "1..0", None])
def test_invalid_manifest_versions_are_rejected(version):
    with pytest.raises(NextcloudError):
        validate_manifest({"schema_version": version, "release": "fixture", "files": []})
