import hashlib
import json
from pathlib import Path
from os import terminal_size

import pytest

from smash_hcm_databank_client.download_flow import download, folder
from smash_hcm_databank_client.manifest import artifact_type, select_downloads, validate_manifest
from menu_helpers import dispatch_menu as run_menu
from smash_hcm_databank_client.nextcloud import NextcloudError
from smash_hcm_databank_client.settings import SMASH_URL, terminal_logo
from smash_hcm_databank_client.workspace import Workspace, default_env_file, default_state_dir


def item(path, cohorts=(), modalities=(), **metadata):
    payload = ("synthetic published file: " + path).encode()
    return {"path": path, "size_bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest(),
            "cohorts": list(cohorts), "modalities": list(modalities), **metadata}


class Server:
    def __init__(self, entries):
        self.payloads = {entry["path"]: ("synthetic published file: " + entry["path"]).encode() for entry in entries}
        self.payloads["manifest.json"] = json.dumps({"schema_version": 1, "release": "fixture", "files": entries}).encode()
        self.calls = []

    def check(self):
        self.calls.append("check")
        return {"status": "PASS"}

    def download(self, remote, destination, expected_sha256=None, expected_size=None, max_bytes=None, progress=None):
        self.calls.append(remote)
        content = self.payloads[remote]
        checksum = hashlib.sha256(content).hexdigest()
        assert expected_sha256 is None or checksum == expected_sha256
        assert expected_size is None or len(content) == expected_size
        assert max_bytes is None or len(content) <= max_bytes
        destination.mkdir(parents=True)
        (destination / Path(remote).name).write_bytes(content)
        if progress:
            progress(len(content), len(content), "complete")
        return {"sha256": checksum, "size_bytes": len(content)}


def workspace(tmp_path, entries):
    server = Server(entries)
    env = tmp_path / ".env"
    env.write_text("NEXTCLOUD_URL=" + SMASH_URL + "\nNEXTCLOUD_USERNAME=fixture\nNEXTCLOUD_PASSWORD=fake-password")
    state = Workspace(tmp_path / "state", env, client_factory=lambda config: server)
    source = tmp_path / "manifest.json"
    source.write_bytes(server.payloads["manifest.json"])
    state.use_manifest(source)
    return state, server


def answers(*values):
    values = iter(values)
    return lambda prompt: next(values)


def test_three_selected_cohorts_download_only_their_ecg_archives(tmp_path):
    entries = [item(cohort + ".zip", [cohort], ["ecg"], representation="npz") for cohort in ("FLORENCE-TRAIN", "FLORENCE-TEST", "RENNES-TEST", "RENNES-ALL")]
    entries += [item("mri.zip", ["FLORENCE-TRAIN"], ["mri"], representation="nifti"),
                item("raw-dicom.zip", ["FLORENCE-TRAIN"], ["mri"], representation="dicom")]
    state, server = workspace(tmp_path, entries)
    destination, output = tmp_path / "chosen-data", []
    results = download(state, "curated", read=answers("1,2,4", "1", "c", str(destination), "y"), write=output.append)
    assert set(server.calls) == {"FLORENCE-TRAIN.zip", "FLORENCE-TEST.zip", "RENNES-TEST.zip"}
    assert len(results) == 3
    assert all(destination in Path(result["local_path"]).parents for result in results)
    assert all(row["status"] == "PASS" for row in state.verify_local())
    assert any("3 files" in line for line in output)
    assert "raw-dicom.zip" not in server.calls


def test_download_published_core_csvs_without_local_omop(tmp_path):
    entries = [item(cohort + ".csv", [cohort], kind="tabular-export", variable_groups=["core"]) for cohort in ("FLORENCE-TRAIN", "FLORENCE-TEST")]
    entries.append(item("all-vars.csv", ["FLORENCE-TRAIN"], kind="tabular-export", variable_groups=["all"]))
    state, server = workspace(tmp_path, entries)
    results = download(state, "tables", read=answers("3", "all", "c", str(tmp_path / "csvs"), "y"), write=lambda value: None)
    assert len(results) == 2 and "all-vars.csv" not in server.calls
    assert not state.state["active_db"]


def test_shared_bundle_is_downloaded_once_and_missing_cohort_is_not_inferred():
    data = validate_manifest({"schema_version": 1, "release": "fixture", "files": [
        item("shared.zip", ["florence_train", "florence_test"], ["ecg"]),
        item("rennes_all.zip", ["rennes_all"], ["ecg"]),
    ]})
    assert len(select_downloads(data, "curated", ["FLORENCE-TRAIN", "FLORENCE-TEST"], "ECG")) == 1
    with pytest.raises(NextcloudError, match="rennes-test"):
        select_downloads(data, "curated", ["FLORENCE-TRAIN", "RENNES-TEST"], "ECG")


def test_default_downloads_location_is_not_saved_or_created_without_confirmation(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "user-home"))
    state, server = workspace(tmp_path, [])
    assert state.suggested_download_root() == tmp_path / "Downloads"
    assert folder(state, read=answers("n"), write=lambda value: None) is None
    assert state.state["download_root"] == ""
    assert not (tmp_path / "user-home").exists() and not server.calls


def test_cancelled_batch_does_not_save_changed_directory_or_transfer_files(tmp_path):
    state, server = workspace(tmp_path, [item("ecg.zip", ["rennes_test"], ["ecg"])])
    destination = tmp_path / "chosen-data"
    assert not download(state, "curated", read=answers("1", "1", "c", str(destination), "n"), write=lambda value: None)
    assert not server.calls and not destination.exists() and not state.state["download_root"]


def test_changed_location_preserves_old_files_and_uses_new_location_on_request(tmp_path):
    state, server = workspace(tmp_path, [item("ecg.zip", ["rennes_test"], ["ecg"])])
    selected = state.manifest()["files"][0]
    state.set_download_root(tmp_path / "first")
    original = state.download_entry(selected)
    state.set_download_root(tmp_path / "second")
    assert state.verify_local()[0]["status"] == "PASS"
    replacement = state.download_entry(selected)
    assert (tmp_path / "second") in Path(replacement["local_path"]).parents
    assert Path(original["local_path"]).is_file() and server.calls == ["ecg.zip", "ecg.zip"]
    reopened = Workspace(state.root, state.env_file)
    assert reopened.verify_local()[0]["status"] == "PASS"


def test_verification_identifies_missing_and_modified_files(tmp_path):
    state, _ = workspace(tmp_path, [item("one.zip", ["rennes_test"], ["ecg"]), item("two.zip", ["rennes_test"], ["ecg"])])
    state.set_download_root(tmp_path / "files")
    first, second = [state.download_entry(entry) for entry in state.manifest()["files"]]
    Path(first["local_path"]).unlink()
    Path(second["local_path"]).write_bytes(b"corrupt")
    rows = state.verify_local()
    assert [row["status"] for row in rows] == ["FAIL", "FAIL"]
    assert "Missing" in rows[0]["detail"] and "differs" in rows[1]["detail"]


def test_verification_can_use_saved_hash_when_manifest_copy_is_missing(tmp_path):
    state, _ = workspace(tmp_path, [item("ecg.zip", ["rennes_test"], ["ecg"])])
    state.download_entry(state.manifest()["files"][0])
    Path(state.state["manifest_path"]).unlink()
    assert state.verify_local()[0]["status"] == "PASS"


def test_partial_failure_does_not_discard_successful_downloads(tmp_path, monkeypatch):
    entries = [item("one.zip", ["rennes_test"], ["ecg"]), item("two.zip", ["rennes_test"], ["ecg"])]
    state, server = workspace(tmp_path, entries)
    original = server.download
    def interrupted(remote, destination, **kwargs):
        if remote == "one.zip":
            raise NextcloudError("Synthetic transfer interruption")
        return original(remote, destination, **kwargs)
    monkeypatch.setattr(server, "download", interrupted)
    output = []
    results = download(state, "curated", read=answers("1", "1", "c", str(tmp_path / "data"), "y"), write=output.append)
    assert len(results) == 1 and state.verify_local()[0]["status"] == "PASS"
    assert "Finished: 1 verified, 1 failed." in output


def test_connection_and_manifest_are_retrieved_in_one_guided_step(tmp_path):
    state, server = workspace(tmp_path, [item("train.csv", ["florence_train"], kind="table")])
    state.state["manifest_path"] = ""
    run_menu(state, read=answers("15", "0"), write=lambda value: None)
    assert server.calls == ["check", "manifest.json"]
    assert len(state.manifest()["files"]) == 1


def test_failed_connection_does_not_start_manifest_download(tmp_path, monkeypatch):
    state, server = workspace(tmp_path, [])
    monkeypatch.setattr(server, "check", lambda: {"status": "FAIL"})
    output = []
    run_menu(state, read=answers("15", "0"), write=output.append)
    assert not server.calls
    assert any("manifest retrieval was not started" in line for line in output)


def test_missing_manifest_is_not_reported_as_failed_connection(tmp_path, monkeypatch):
    state, server = workspace(tmp_path, [])
    state.state["manifest_path"] = ""
    def missing(*args, **kwargs):
        raise NextcloudError("Synthetic not found (HTTP 404)", status_code=404)
    monkeypatch.setattr(server, "download", missing)
    output = []
    run_menu(state, read=answers("15", "0"), write=output.append)
    assert server.calls == ["check"]
    assert state.connection_status is True
    assert any("Manifest: NOT AVAILABLE (HTTP 404) at /databank/manifest.json" in line for line in output)
    assert any("Connection: SUCCESS (verified HTTPS WebDAV)" in line for line in output)
    assert not any("Could not complete" in line for line in output)
    assert not state.state["manifest_path"]


def test_standalone_manifest_404_checks_root_and_preserves_cached_manifest(tmp_path, monkeypatch):
    state, server = workspace(tmp_path, [item("train.csv", ["florence_train"], kind="table")])
    previous = state.state["manifest_path"]
    def missing(*args, **kwargs):
        raise NextcloudError("Synthetic not found", status_code=404)
    monkeypatch.setattr(server, "download", missing)
    output = []
    run_menu(state, read=answers("3", "0"), write=output.append)
    assert server.calls == ["check"] and state.connection_status is True
    assert state.state["manifest_path"] == previous
    assert len(state.manifest()["files"]) == 1
    assert any("previously loaded manifest" in line for line in output)
    assert any("SMASH-HCM Databank:" in line and SMASH_URL + "/databank" in line for line in output)
    assert not any(SMASH_URL + " / " in line for line in output)


def test_missing_root_is_still_a_connection_failure(tmp_path, monkeypatch):
    state, server = workspace(tmp_path, [])
    def missing(*args, **kwargs):
        raise NextcloudError("Synthetic not found", status_code=404)
    monkeypatch.setattr(server, "download", missing)
    monkeypatch.setattr(server, "check", missing)
    output = []
    run_menu(state, read=answers("3", "0"), write=output.append)
    assert state.connection_status is False
    assert not any("The databank connection works" in line for line in output)
    assert any("Could not complete" in line for line in output)


def test_manifest_authentication_failure_is_not_mislabeled_missing(tmp_path, monkeypatch):
    state, server = workspace(tmp_path, [])
    def denied(*args, **kwargs):
        raise NextcloudError("Synthetic authentication failure", status_code=401)
    monkeypatch.setattr(server, "download", denied)
    output = []
    run_menu(state, read=answers("15", "0"), write=output.append)
    assert any("authentication failure" in line for line in output)
    assert not any("NOT AVAILABLE (HTTP 404)" in line for line in output)


def test_frozen_profile_uses_home_independently_of_launch_directory(tmp_path, monkeypatch):
    monkeypatch.setattr("smash_hcm_databank_client.workspace.sys.frozen", True, raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "user-home"))
    assert default_state_dir() == tmp_path / "user-home/.smash/omop-exporter"
    assert default_env_file() == default_state_dir() / ".env"
    assert not (tmp_path / "user-home").exists()


def test_new_logo_fits_regular_terminal_without_reusing_letter_fill(tmp_path, monkeypatch):
    # Match the real tuple contract; pytest also reads this shared module while
    # reporting the call result, before monkeypatch teardown has run.
    monkeypatch.setattr("smash_hcm_databank_client.settings.shutil.get_terminal_size", lambda fallback: terminal_size((80, 24)))
    logo = terminal_logo()
    assert "SMASH-HCM DATABANK CLIENT" in logo and "SMASHHCMSMASH" not in logo
    assert max(map(len, logo.splitlines())) <= 80
    assert len(logo.splitlines()) <= 24


def test_questionary_checkboxes_select_multiple_cohorts(monkeypatch):
    questionary = pytest.importorskip("questionary")
    from prompt_toolkit.input import DummyInput
    from prompt_toolkit.key_binding import KeyPress
    from prompt_toolkit.keys import Keys
    from prompt_toolkit.output import DummyOutput
    from smash_hcm_databank_client.menu_ui import checkbox
    original = questionary.checkbox
    def terminal(*args, **kwargs):
        question = original(*args, **kwargs, input=DummyInput(), output=DummyOutput())
        def press_keys():
            question.application.key_processor.feed_multiple([
                KeyPress(" "), KeyPress(Keys.Down), KeyPress(" "), KeyPress(Keys.Down), KeyPress(" "), KeyPress(Keys.ControlM)])
            question.application.key_processor.process_keys()
        question.application.pre_run_callables.append(press_keys)
        return question
    monkeypatch.setattr(questionary, "checkbox", terminal)
    cohorts = ["FLORENCE-TRAIN", "FLORENCE-TEST", "RENNES-TEST"]
    assert checkbox("Cohorts", [(value, value) for value in cohorts]) == cohorts


@pytest.mark.parametrize("metadata,expected", [
    ({"kind": "database"}, "database"), ({"kind": "tabular-export"}, "tables"),
    ({"representation": "npz"}, "curated"), ({"representation": "dicom"}, "other"),
    ({"representation": "raw"}, "other"),
])
def test_artifact_categories_keep_raw_dicom_separate(metadata, expected):
    assert artifact_type({**item("data.zip", ["rennes_test"], ["ecg"]), **metadata}) == expected
