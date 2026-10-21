import json
from types import SimpleNamespace

import pytest

from smash_hcm_databank_client import credentials
from smash_hcm_databank_client.credentials import load_vault, native_vault, save_env, save_vault
from smash_hcm_databank_client.menu import banner, setup
from menu_helpers import dispatch_menu as run_menu
from smash_hcm_databank_client.nextcloud import NextcloudError, read_dotenv
from smash_hcm_databank_client.settings import SMASH_URL
from smash_hcm_databank_client.workspace import Workspace


def answers(*values):
    values = iter(values)
    return lambda prompt: next(values)


def test_banner_has_ascii_smash_url_and_local_version(tmp_path, omop_path):
    workspace = Workspace(tmp_path / "state", tmp_path / "missing.env", db_path=omop_path)
    output = []
    banner(workspace, output.append)
    rendered = "\n".join(output)
    assert "SMASH-HCM DATABANK CLIENT" in rendered
    assert SMASH_URL in rendered
    assert rendered.index("SMASH-HCM OMOP database:") > rendered.index("SMASH-HCM DATABANK CLIENT")
    assert "OMOP.db" in rendered


def test_menu_exits_without_credentials_or_network(tmp_path):
    output = []
    assert run_menu(Workspace(tmp_path / "state", tmp_path / "missing.env"), read=answers("0"), write=output.append) == 0
    assert any("Download OMOP" in line for line in output)


def test_menu_missing_manifest_keeps_other_options_available(tmp_path):
    output = []
    assert run_menu(Workspace(tmp_path / "state", tmp_path / "missing.env"), read=answers("5", "0"), write=output.append) == 0
    assert any("Retrieve or load a manifest first" in line for line in output)


def test_setup_session_never_persists_password(tmp_path, monkeypatch):
    monkeypatch.setattr("smash_hcm_databank_client.menu.native_vault", lambda: None)
    workspace = Workspace(tmp_path / "state", tmp_path / ".env")
    output = []
    setup(workspace, read=answers("fixture-user", "2"), password_read=answers("fake-password"), write=output.append)
    assert workspace.session.password == "fake-password"
    assert "fake-password" not in (workspace.root / "state.json").read_text()
    assert "fake-password" not in "\n".join(output)
    assert not workspace.env_file.exists()
    reopened = Workspace(workspace.root, workspace.env_file)
    with pytest.raises(NextcloudError, match="not retained"):
        reopened.client()


def test_setup_vault_stores_only_reference_in_profile(tmp_path, monkeypatch):
    stored = []
    monkeypatch.setattr("smash_hcm_databank_client.menu.native_vault", lambda: None)
    monkeypatch.setattr("smash_hcm_databank_client.menu.save_vault", lambda username, password: stored.append((username, password)))
    workspace = Workspace(tmp_path / "state", tmp_path / ".env")
    setup(workspace, read=answers("fixture", "1"), password_read=answers("fake-password"), write=lambda value: None)
    assert stored == [("fixture", "fake-password")]
    assert workspace.state["profile"]["credential_storage"] == "vault"
    assert "fake-password" not in (workspace.root / "state.json").read_text()


def test_plaintext_env_is_explicit_and_preserves_other_settings(tmp_path):
    path = tmp_path / ".env"
    path.write_text("OTHER=value\nNEXTCLOUD_PASSWORD=old\n")
    save_env(path, "fixture", "a'quoted$#password")
    data = read_dotenv(path)
    assert data["OTHER"] == "value"
    assert data["NEXTCLOUD_PASSWORD"] == "a'quoted$#password"
    assert data["NEXTCLOUD_URL"] == SMASH_URL
    assert "old" not in path.read_text()


def test_unsafe_vault_backend_does_not_fall_back_to_plaintext(monkeypatch):
    backend = SimpleNamespace(priority=10)
    monkeypatch.setattr(credentials.importlib, "import_module", lambda name: SimpleNamespace(get_keyring=lambda: backend))
    with pytest.raises(NextcloudError, match="supported OS"):
        native_vault()


def test_vault_errors_do_not_echo_secret():
    class Broken:
        def set_password(self, *args):
            raise RuntimeError("fake-password")
        def get_password(self, *args):
            raise RuntimeError("fake-password")
    for action in (lambda: save_vault("fixture", "fake-password", Broken()), lambda: load_vault("fixture", Broken())):
        with pytest.raises(NextcloudError) as exc:
            action()
        assert "fake-password" not in str(exc.value)


def test_existing_env_login_is_compatible_and_bound_to_smash(tmp_path):
    path = tmp_path / ".env"
    path.write_text("NEXTCLOUD_URL=" + SMASH_URL + "\nNEXTCLOUD_USERNAME=fixture\nNEXTCLOUD_PASSWORD=fake-password")
    client = Workspace(tmp_path / "state", path, client_factory=lambda config: config).client()
    assert client.server_url == SMASH_URL and client.remote_root == "databank"
    path.write_text("NEXTCLOUD_URL=https://other.example.org\nNEXTCLOUD_USERNAME=fixture\nNEXTCLOUD_PASSWORD=fake-password")
    with pytest.raises(NextcloudError, match="only to the SMASH"):
        Workspace(tmp_path / "state", path).client()


def test_menu_connection_uses_injected_client_and_no_secret_output(tmp_path, monkeypatch):
    workspace = Workspace(tmp_path / "state", tmp_path / ".env")
    workspace.state["profile"] = {"credential_storage": "vault", "username": "fixture"}
    monkeypatch.setattr(workspace, "client", lambda: SimpleNamespace(check=lambda: {"status": "PASS"}))
    output = []
    assert run_menu(workspace, read=answers("2", "0"), write=output.append) == 0
    assert any("Connection: SUCCESS" in line for line in output)


def test_partial_database_can_export_core_events_without_cohort_catalog(tmp_path, omop_path):
    import sqlite3
    with sqlite3.connect(omop_path) as connection:
        connection.executescript("DELETE FROM cohort; DELETE FROM cohort_definition; DELETE FROM smash_endpoint_censor;")
    workspace = Workspace(tmp_path / "state", tmp_path / "missing.env", db_path=omop_path)
    output = tmp_path / "events"
    assert run_menu(workspace, read=answers("9", "1", "2", "1", "all", "", "", "n", str(output), "y", "0"), write=lambda value: None) == 0
    manifest = json.loads((output / "event_stream/ALL-PEOPLE/dataset_manifest.json").read_text())
    assert manifest["cohort_id"] is None and manifest["rows"] == 3


def test_password_prompt_never_falls_back_to_echo(monkeypatch):
    import getpass
    import warnings
    from smash_hcm_databank_client.menu import secret_prompt
    monkeypatch.setattr("smash_hcm_databank_client.menu.sys.stdin", SimpleNamespace(isatty=lambda: True))
    def cannot_hide(prompt):
        warnings.warn("cannot hide", getpass.GetPassWarning)
        raise AssertionError("Unprotected input must not happen")
    monkeypatch.setattr("smash_hcm_databank_client.menu.getpass.getpass", cannot_hide)
    with pytest.raises(NextcloudError, match="cannot hide"):
        secret_prompt("Password: ")


def test_plaintext_storage_never_writes_public_template(tmp_path):
    path = tmp_path / ".env.example"
    with pytest.raises(NextcloudError, match="not a template"):
        save_env(path, "fixture", "fake-password")
    assert not path.exists()


def test_noninteractive_nextcloud_command_uses_saved_vault_profile(tmp_path, monkeypatch, capsys):
    from smash_hcm_databank_client.cli import main
    workspace = Workspace(tmp_path / "state", tmp_path / "missing.env")
    workspace.state["profile"] = {"username": "fixture", "credential_storage": "vault", "webdav_url": ""}
    workspace.save()
    monkeypatch.setattr("smash_hcm_databank_client.workspace.load_vault", lambda username: "fake-password")
    monkeypatch.setattr("smash_hcm_databank_client.nextcloud.NextcloudClient.check", lambda self: {"status": "PASS"})
    assert main(["nextcloud", "check", "--state-dir", str(workspace.root)]) == 0
    assert "fake-password" not in capsys.readouterr().out


def test_explicit_dotenv_command_is_independent_of_menu_state(tmp_path, monkeypatch):
    from smash_hcm_databank_client.cli import main
    state = tmp_path / "state"
    state.mkdir()
    (state / "state.json").write_text("invalid")
    env = tmp_path / ".env"
    env.write_text("NEXTCLOUD_URL=" + SMASH_URL + "\nNEXTCLOUD_USERNAME=fixture\nNEXTCLOUD_PASSWORD=fake-password\nNEXTCLOUD_REMOTE_ROOT=databank")
    monkeypatch.setattr("smash_hcm_databank_client.nextcloud.NextcloudClient.check", lambda self: {"status": "PASS"})
    assert main(["nextcloud", "check", "--state-dir", str(state), "--env-file", str(env)]) == 0


@pytest.mark.parametrize("profile", [{"credential_storage": "unknown"}, {"credential_storage": "vault"}, {"username": []}])
def test_invalid_login_profiles_fail_cleanly(tmp_path, profile):
    (tmp_path / "state.json").write_text(json.dumps({"schema_version": 1, "profile": profile}))
    with pytest.raises(NextcloudError, match="settings are invalid"):
        Workspace(tmp_path)
