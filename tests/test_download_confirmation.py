from pathlib import Path

import pytest

from smash_hcm_databank_client.console import console_write
from smash_hcm_databank_client.download_flow import confirm_location
from smash_hcm_databank_client import menu_ui, platform_paths
from smash_hcm_databank_client.prompts import location_choice
from smash_hcm_databank_client.workspace import Workspace


def test_enter_confirms_default_downloads_once_and_remembers_it(tmp_path):
    state = Workspace(tmp_path / "state", tmp_path / "absent.env")
    prompts = []
    def read(prompt):
        prompts.append(prompt)
        return ""
    expected = tmp_path / "Downloads"
    assert confirm_location(state, read, plain=True) == expected
    assert prompts == [f"Download these files to: {expected} [Y/n/change location]: "]
    assert expected.is_dir()
    loaded = Workspace(state.root, state.env_file)
    assert loaded.suggested_download_root() == expected


def test_change_then_decline_preserves_saved_folder_and_creates_nothing(tmp_path):
    state = Workspace(tmp_path / "state", tmp_path / "absent.env")
    previous = state.set_download_root(tmp_path / "selected")
    before = (state.root / "state.json").read_bytes()
    changed = tmp_path / "different"
    answers = iter(["c", str(changed), "n"])
    output = []
    assert confirm_location(state, lambda _: next(answers), output.append, plain=True) is None
    assert not changed.exists()
    assert state.suggested_download_root() == previous
    assert (state.root / "state.json").read_bytes() == before
    assert "Download cancelled" in output[-1]


def test_change_then_confirm_is_saved_for_next_launch(tmp_path):
    state = Workspace(tmp_path / "state", tmp_path / "absent.env")
    target = tmp_path / "chosen"
    answers = iter(["change", str(target), "yes"])
    assert confirm_location(state, lambda _: next(answers), plain=True) == target
    assert Workspace(state.root, state.env_file).suggested_download_root() == target
    assert not (tmp_path / "Downloads").exists()


def test_arrow_confirmation_has_yes_as_first_choice_and_cancel_is_interrupt(monkeypatch):
    monkeypatch.setattr(menu_ui, "arrow_ui", lambda *args: True)
    captured = []
    def select(message, choices):
        captured.append(choices)
        return None
    monkeypatch.setattr(menu_ui, "select", select)
    with pytest.raises(KeyboardInterrupt):
        location_choice("Download these files to: Downloads")
    assert [choice[:2] for choice in captured[0]] == [("yes", "Yes"), ("no", "No"), ("change", "Change location")]


def test_styled_log_writer_keeps_arrow_navigation(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(menu_ui.sys, "stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(menu_ui.sys, "stdout", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setenv("TERM", "xterm")
    assert menu_ui.arrow_ui(write=console_write)
    assert not menu_ui.arrow_ui(write=lambda _: None)


@pytest.mark.parametrize("platform,redirected", [("win32", True), ("win32", False), ("darwin", False)])
def test_platform_download_location_respects_windows_redirection_and_mac_default(tmp_path, monkeypatch, platform, redirected):
    custom = tmp_path / "relocated-downloads"
    monkeypatch.setattr(platform_paths.sys, "platform", platform)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(platform_paths, "_windows_downloads", lambda: custom if redirected else None)
    assert platform_paths.default_download_directory() == (custom if redirected else tmp_path / "Downloads")
    assert not custom.exists() and not (tmp_path / "Downloads").exists()


def test_windows_downloads_api_failure_falls_back_without_creating_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(platform_paths.sys, "platform", "win32")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    def unavailable():
        raise OSError("known folder unavailable")
    monkeypatch.setattr(platform_paths, "_windows_downloads", unavailable)
    assert platform_paths.default_download_directory() == tmp_path / "Downloads"
    assert not (tmp_path / "Downloads").exists()
