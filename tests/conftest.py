from pathlib import Path
import pytest

@pytest.fixture(autouse=True)
def offline_menu_startup(monkeypatch, tmp_path):
    # Unit/workflow tests never contact the real server. Probe tests inject their
    # own opener into connectivity.probe_server and exercise the actual logic.
    monkeypatch.setattr("smash_hcm_databank_client.menu.probe_server", lambda: {"available": False, "detail": "Offline test"})
    # Existing workflow cases exercise individual menu actions. Startup update
    # networking/prompts are covered explicitly in test_updates.py.
    monkeypatch.setattr("smash_hcm_databank_client.menu.startup_updates", lambda *args, **kwargs: None)
    monkeypatch.setattr("smash_hcm_databank_client.menu.check_login", lambda *args, **kwargs: None)
    # No prompt test may create/write the real operating-system Downloads folder.
    monkeypatch.setattr("smash_hcm_databank_client.workspace.default_download_directory", lambda: tmp_path / "Downloads")


@pytest.fixture
def omop_path(tmp_path):
    # Recognizable signature fixture, not a restorable clinical database.
    path = tmp_path / "OMOP.db"
    path.write_bytes(b"PGDMP\x01\x0e\x00\x04\x08\x01\x01synthetic dump fixture")
    return path
