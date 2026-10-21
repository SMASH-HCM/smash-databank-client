import json

from smash_hcm_databank_client import __version__
from smash_hcm_databank_client.menu import run_menu
from smash_hcm_databank_client.presentation import status_panel
from smash_hcm_databank_client.settings import APP_TITLE, terminal_logo
from smash_hcm_databank_client.updates import check_login, check_updates, startup_updates
from smash_hcm_databank_client.workspace import Workspace
from test_manifest_workspace import env_file
from test_updates import Server, configured


def test_title_version_in_logo_and_panel_even_on_narrow_terminal(tmp_path):
    state = Workspace(tmp_path / "state", tmp_path / "absent.env")
    assert APP_TITLE + " " + __version__ in terminal_logo()
    panel = status_panel(state, 100)
    assert APP_TITLE + " " + __version__ in panel.splitlines()[0]
    assert all(len(line) == 100 for line in panel.splitlines())
    narrow = status_panel(state, 32)
    assert all(len(line) == 32 for line in narrow.splitlines())
    assert __version__ in narrow


def test_login_and_connectivity_complete_before_first_panel_and_not_repeated(tmp_path, monkeypatch):
    server = Server({"manifest.json": json.dumps({"schema_version": 1, "release": "fixture", "files": []}).encode()})
    state = Workspace(tmp_path / "state", env_file(tmp_path), client_factory=lambda config: server)
    monkeypatch.setattr("smash_hcm_databank_client.menu.check_login", check_login)
    monkeypatch.setattr("smash_hcm_databank_client.menu.startup_updates", startup_updates)
    monkeypatch.setattr("smash_hcm_databank_client.menu.probe_server", lambda: {"available": True, "detail": "HTTPS reachable"})
    messages, supplied = [], iter(["n", "6"])
    assert run_menu(state, read=lambda prompt: next(supplied), write=messages.append, plain=True) == 0
    panel_index = next(i for i, line in enumerate(messages) if line.startswith("|"))
    assert messages.index("Databank connectivity: SUCCESS") < panel_index
    assert messages.index("Login and databank access: SUCCESS") < panel_index
    panel = messages[panel_index]
    assert "[OK] Verified" in panel and "Not checked" not in panel
    assert server.calls == ["check"]
    assert not any("PASS" in line for line in messages)


def test_unchanged_manifest_has_one_success_line_and_still_offers_missing_file(tmp_path):
    state, server = configured(tmp_path)
    server.calls.clear()
    messages = []
    assert check_updates(state, write=messages.append, plain=True) == []
    assert messages == ["Checking Databank manifest ... SUCCESS"]
    assert server.calls == ["stat:manifest.json"]
    # Catalogue unchanged does not suppress repair of missing/corrupted-size files.
    from pathlib import Path
    Path(state.state["downloads"]["cohort.zip"]["local_path"]).unlink()
    messages.clear()
    check_updates(state, read=lambda prompt: "0", write=messages.append, plain=True)
    assert any("Updates/repairs available" in line for line in messages)
    assert not any("manifest.json | complete" in line for line in messages)
