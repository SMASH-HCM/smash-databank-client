from pathlib import Path

import pytest

from omop_exporter.manifest import select_downloads
from omop_exporter.manifest_browser import ManifestTree, browse
from omop_exporter.menu import run_menu
from omop_exporter.menu_ui import actions, navigate
from omop_exporter.nextcloud import NextcloudError
from omop_exporter.presentation import status_panel
from omop_exporter.settings import DATA_ACCESS_URL, SMASH_DATABANK_URL
from test_download_flow import answers, item, workspace


@pytest.fixture
def catalog(tmp_path):
    return workspace(tmp_path, [
        item("README.md"), item("site/ecg/train.zip"), item("site/ecg/test.zip"),
        item("site/ecg/docs/schema.json"), item("site/echo/train.zip"), item("site2/ecg/other.zip"),
    ])


def test_manifest_tree_lists_real_children_and_keeps_sibling_prefixes_separate(catalog):
    state, server = catalog
    tree = ManifestTree(state.manifest())
    folders, files = tree.list_folder()
    assert folders == ["site", "site2"] and [entry["path"] for entry in files] == ["README.md"]
    assert [entry["path"] for entry in tree.select_folder("site/ecg")] == ["site/ecg/test.zip", "site/ecg/train.zip"]
    nested = tree.select_folder("site", recursive=True)
    assert len(nested) == 4 and not any(entry["path"].startswith("site2/") for entry in nested)
    assert not server.calls  # Navigation does not query the remote server.


@pytest.mark.parametrize("folder", ["../secret", "/absolute", "site/../../secret", "https://other.example/", "unlisted"])
def test_manifest_browser_rejects_escapes_and_unlisted_folders(catalog, folder):
    state, _ = catalog
    with pytest.raises(NextcloudError):
        ManifestTree(state.manifest()).select_folder(folder, recursive=True)


def test_manifest_file_folder_collision_is_rejected(tmp_path):
    state, _ = workspace(tmp_path, [item("same"), item("same/nested.txt")])
    with pytest.raises(NextcloudError, match="both a file and a folder"):
        ManifestTree(state.manifest())


@pytest.mark.parametrize("selection,expected", [
    ("2", {"site/ecg/test.zip", "site/ecg/train.zip"}),
    ("3", {"site/ecg/test.zip", "site/ecg/train.zip", "site/ecg/docs/schema.json"}),
    ("6", {"site/ecg/test.zip"}),
])
def test_browser_downloads_direct_recursive_or_one_file(catalog, tmp_path, selection, expected):
    state, server = catalog
    output = []
    results = browse(state, read=answers("4", "5", selection, str(tmp_path / "data"), "y", "y"), write=output.append)
    assert set(server.calls) == expected and len(results) == len(expected)
    assert all(row["status"] == "PASS" for row in state.verify_local())
    assert any("Download review:" in line for line in output)


def test_browser_multiselect_and_parent_navigation(catalog, tmp_path):
    state, server = catalog
    # Root -> site -> parent -> site -> ecg -> select both immediate files.
    results = browse(state, read=answers("4", "1", "4", "5", "4", "1,2", str(tmp_path / "data"), "y", "y"), write=lambda value: None)
    assert len(results) == 2 and set(server.calls) == {"site/ecg/test.zip", "site/ecg/train.zip"}


def test_cancelled_browser_does_not_select_location_or_transfer(catalog):
    state, server = catalog
    assert not browse(state, read=answers("0"), write=lambda value: None)
    assert not server.calls and not state.state["download_root"]


def test_root_and_setup_have_the_requested_options(catalog):
    state, _ = catalog
    seen = []
    responses = iter(["group:Setup", "back", "0"])
    def selector(message, entries):
        seen.append((message, entries))
        return next(responses)
    assert navigate(actions(state), selector) == "0"
    assert seen[0][0] == "SMASH-HCM Databank Menu"
    assert [entry[1] for entry in seen[0][1]] == ["1. > Setup", "2. > Download", "3. > Local OMOP", "4. > Validate", "5. > Data Access Request", "6. > Exit"]
    assert [entry[1] for entry in seen[1][1]][:4] == ["Setup / Change User Login", "Check Databank Connection", "Retrieve manifest", "Select Download location"]
    assert seen[1][1][4][1] == "Check for data updates"
    assert len(seen[1][1]) == 6  # Five setup actions plus Back.


def test_actual_plain_menu_uses_same_root_numbers_and_confirms_location(catalog, tmp_path):
    state, server = catalog
    output = []
    assert run_menu(state, read=answers("1", "4", str(tmp_path / "chosen"), "y", "6"), write=output.append, plain=True) == 0
    assert state.state["download_root"] == str(tmp_path / "chosen")
    assert not server.calls
    assert any("SMASH-HCM DATABANK EXPORTER" in line for line in output)


def test_plain_root_access_request_is_option_five(catalog, monkeypatch):
    state, _ = catalog
    opened = []
    monkeypatch.setattr("omop_exporter.menu.webbrowser.open", lambda url, new: opened.append(url) or True)
    run_menu(state, read=answers("5", "6"), write=lambda value: None, plain=True)
    assert opened == [DATA_ACCESS_URL]


@pytest.mark.parametrize("width", [54, 80, 100])
def test_status_box_stays_aligned_with_long_directory_and_shows_release(catalog, width):
    state, _ = catalog
    state.state["download_root"] = str(Path("K:/SMASH_DATA") / ("long-folder-" * 12))
    rendered = status_panel(state, width)
    assert all(len(line) == width and line.startswith("|") and line.endswith("|") for line in rendered.splitlines())
    assert "Local directory:" in rendered and "Local OMOP database:" in rendered and "Databank manifest:" in rendered
    assert "<unavailable>" in rendered and "fixture" in rendered
    assert "SMASH-HCM Databank:" in rendered
    if width >= 80:
        assert SMASH_DATABANK_URL in rendered


def test_cohorts_then_multiple_data_types_download_every_published_pair(tmp_path):
    from omop_exporter.download_flow import download
    entries = [item(cohort + "-" + modality + ".zip", [cohort], [modality])
               for cohort in ("FLORENCE-TRAIN", "RENNES-TEST") for modality in ("ECG", "ECHO")]
    state, server = workspace(tmp_path, entries)
    results = download(state, "curated", read=answers("all", "all", str(tmp_path / "data"), "y", "y"), write=lambda value: None)
    assert len(results) == 4 and len(server.calls) == 4


def test_partial_modality_is_disabled_and_no_requested_pair_is_silently_missing(tmp_path):
    from omop_exporter.download_flow import download
    entries = [item("florence-ecg.zip", ["FLORENCE-TRAIN"], ["ECG"]),
               item("rennes-ecg.zip", ["RENNES-TEST"], ["ECG"]), item("florence-mri.zip", ["FLORENCE-TRAIN"], ["MRI"])]
    state, server = workspace(tmp_path, entries)
    with pytest.raises(NextcloudError, match="Not published for: RENNES-TEST"):
        download(state, "curated", read=answers("all", "2"), write=lambda value: None)
    assert not server.calls
    with pytest.raises(NextcloudError, match="rennes-test/mri"):
        select_downloads(state.manifest(), "curated", ["FLORENCE-TRAIN", "RENNES-TEST"], modalities=["ECG", "MRI"])
