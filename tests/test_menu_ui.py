import json

import pytest

from smash_hcm_databank_client.menu import choose
from menu_helpers import dispatch_menu as run_menu
from smash_hcm_databank_client.menu_ui import actions, navigate, render_plain, select
from smash_hcm_databank_client.nextcloud import NextcloudError
from smash_hcm_databank_client.settings import DATA_ACCESS_URL
from smash_hcm_databank_client.workspace import Workspace


def indexed(workspace):
    return {item.key: item for item in actions(workspace)}


def test_prerequisites_change_without_network_or_vault_access(tmp_path, omop_path, monkeypatch):
    workspace = Workspace(tmp_path / "state", tmp_path / ".env")
    def forbidden(*args):
        raise AssertionError("Availability must not connect or read vault secrets")
    monkeypatch.setattr(workspace, "client", forbidden)
    monkeypatch.setattr("smash_hcm_databank_client.workspace.load_vault", forbidden)
    current = indexed(workspace)
    assert current["11"].enabled and current["1"].enabled and current["10"].enabled
    assert not current["2"].enabled and not current["5"].enabled and not current["12"].enabled
    workspace.state["profile"] = {"credential_storage": "vault", "username": "fixture"}
    assert indexed(workspace)["2"].enabled
    workspace.register_database(omop_path)
    assert indexed(workspace)["12"].enabled
    source = tmp_path / "manifest.json"
    source.write_text(json.dumps({"schema_version": 1, "release": "fixture", "files": [
        {"path": "OMOP.db", "kind": "database", "size_bytes": 10, "sha256": "0" * 64},
        {"path": "ecg.zip", "modalities": ["ecg"], "cohorts": ["rennes_all"], "size_bytes": 10, "sha256": "0" * 64},
    ]}))
    workspace.use_manifest(source)
    assert indexed(workspace)["5"].enabled and indexed(workspace)["6"].enabled
    # Missing/corrupt local manifest must disable downloads again, not trust saved flags.
    from pathlib import Path
    Path(workspace.state["manifest_path"]).write_text("corrupt")
    assert not indexed(workspace)["5"].enabled
    assert "valid manifest" in indexed(workspace)["5"].reason


def test_expired_session_does_not_reenable_network_from_old_dotenv(tmp_path):
    env = tmp_path / ".env"
    env.write_text("NEXTCLOUD_USERNAME=fixture\nNEXTCLOUD_PASSWORD=fake")
    workspace = Workspace(tmp_path / "state", env)
    assert indexed(workspace)["2"].enabled
    workspace.state["profile"] = {"credential_storage": "session", "username": "fixture"}
    assert not indexed(workspace)["2"].enabled


def test_disabled_numeric_action_does_not_start_download(tmp_path, monkeypatch):
    workspace = Workspace(tmp_path / "state", tmp_path / ".env")
    def forbidden(*args):
        raise AssertionError("Disabled download must not execute")
    monkeypatch.setattr(workspace, "download_entry", forbidden)
    output, answers = [], iter(["5", "0"])
    run_menu(workspace, read=lambda prompt: next(answers), write=output.append)
    assert "Unavailable: Retrieve or load a manifest first" in output


def test_access_form_opens_only_when_selected(tmp_path, monkeypatch):
    opened = []
    monkeypatch.setattr("smash_hcm_databank_client.menu.webbrowser.open", lambda url, new: opened.append(url) or True)
    workspace = Workspace(tmp_path / "state", tmp_path / ".env")
    run_menu(workspace, read=lambda prompt: "0", write=lambda value: None)
    assert not opened
    answers = iter(["11", "0"])
    run_menu(workspace, read=lambda prompt: next(answers), write=lambda value: None)
    assert opened == [DATA_ACCESS_URL]


def test_menu_validates_local_database_without_login(tmp_path, omop_path):
    workspace = Workspace(tmp_path / "state", tmp_path / ".env", db_path=omop_path)
    output, answers = [], iter(["12", "0"])
    run_menu(workspace, read=lambda prompt: next(answers), write=output.append)
    assert "Database validation: PASS" in output
    assert "NOT_REQUESTED | expected_sha256" in output


def test_grouped_navigation_back_and_cancel(tmp_path):
    items = actions(Workspace(tmp_path / "state", tmp_path / ".env"))
    answers = iter(["group:Download", "back", "group:Validate", "8"])
    seen = []
    def selector(message, entries):
        seen.append((message, entries))
        return next(answers)
    assert navigate(items, selector) == "8"
    assert any(key == "5" and reason for key, _, reason in seen[1][1])
    assert navigate(items, lambda message, entries: None) == "0"


def test_plain_output_has_status_without_requiring_color(tmp_path):
    output = []
    render_plain(actions(Workspace(tmp_path / "state", tmp_path / ".env")), output.append)
    assert any("Data Access Request" in line and "AVAILABLE" in line for line in output)
    assert any("Harmonized OMOP PostgreSQL dump (advanced)" in line and "UNAVAILABLE" in line for line in output)
    assert not any("\033" in line for line in output)


def test_disabled_format_cannot_be_selected_in_plain_mode():
    with pytest.raises(NextcloudError, match="Needs anchors"):
        choose(["tabular", "events"], str, read=lambda prompt: "1", write=lambda value: None, plain=True,
               disabled=lambda item: "Needs anchors" if item == "tabular" else "")


def test_actual_arrow_keys_skip_disabled_choices(monkeypatch):
    questionary = pytest.importorskip("questionary")
    from prompt_toolkit.input import DummyInput
    from prompt_toolkit.key_binding import KeyPress
    from prompt_toolkit.keys import Keys
    from prompt_toolkit.output import DummyOutput
    original = questionary.select
    def terminal(*args, **kwargs):
        question = original(*args, **kwargs, input=DummyInput(), output=DummyOutput())
        def press_keys():
            question.application.key_processor.feed_multiple([KeyPress(Keys.Down), KeyPress(Keys.ControlM)])
            question.application.key_processor.process_keys()
        question.application.pre_run_callables.append(press_keys)
        return question
    monkeypatch.setattr(questionary, "select", terminal)
    assert select("Fixture", [("one", "Available", ""), ("two", "Locked", "Needs manifest"), ("three", "Also available", "")]) == "three"


def test_native_windows_console_uses_questionary_even_with_dumb_term(monkeypatch):
    pytest.importorskip("questionary")
    from types import SimpleNamespace
    from smash_hcm_databank_client.menu_ui import arrow_ui, console_style
    monkeypatch.setattr("smash_hcm_databank_client.menu_ui.sys.platform", "win32")
    monkeypatch.setattr("smash_hcm_databank_client.menu_ui.sys.stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr("smash_hcm_databank_client.menu_ui.sys.stdout", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setenv("TERM", "dumb")
    assert arrow_ui()
    assert not arrow_ui(plain=True)
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("PROMPT_TOOLKIT_COLOR_DEPTH", raising=False)
    assert console_style()
    monkeypatch.setenv("NO_COLOR", "1")
    assert console_style() == {}
