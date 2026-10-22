from threading import Event
import time
from types import SimpleNamespace
from urllib.error import HTTPError, URLError

import pytest

from smash_hcm_databank_client.connectivity import probe_server
from smash_hcm_databank_client.menu import run_menu
from smash_hcm_databank_client.presentation import status_panel, write_status
from smash_hcm_databank_client.settings import SMASH_URL
from smash_hcm_databank_client.workspace import Workspace


class Opener:
    def __init__(self, status=200, error=None):
        self.status, self.error, self.calls = status, error, []

    def open(self, req, timeout):
        self.calls.append((req, timeout))
        if self.error:
            raise self.error
        owner = self
        class Response:
            status = owner.status
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
        return Response()


def test_startup_probe_only_checks_fixed_https_without_credentials():
    opener = Opener()
    result = probe_server(opener=opener)
    assert result == {"available": True, "detail": "HTTPS reachable; login not checked"}
    req, timeout = opener.calls[0]
    assert req.full_url == SMASH_URL + "/status.php" and req.method == "HEAD"
    assert not req.has_header("Authorization") and req.data is None and timeout == 3


@pytest.mark.parametrize("failure", [URLError("private-proxy-details"), OSError("secret"), HTTPError(SMASH_URL, 503, "private body", {}, None)], ids=["dns-or-proxy", "socket", "http-503"])
def test_offline_or_http_error_is_red_and_does_not_disclose_details(failure):
    result = probe_server(opener=Opener(error=failure))
    assert not result["available"]
    assert all(token not in result["detail"] for token in ("private", "secret"))


def test_startup_wait_is_bounded_and_late_result_cannot_change_returned_status():
    release, finished = Event(), Event()
    class SlowOpener(Opener):
        def open(self, req, timeout):
            release.wait(2)
            try:
                return super().open(req, timeout)
            finally:
                finished.set()
    start = time.monotonic()
    result = probe_server(timeout=0.03, opener=SlowOpener())
    assert time.monotonic() - start < 0.75
    assert not result["available"] and "timed out" in result["detail"]
    release.set()
    assert finished.wait(1)
    assert not result["available"]


def test_panel_checks_directory_presence_and_does_not_create_it(tmp_path, omop_path):
    state = Workspace(tmp_path / "state", tmp_path / "absent.env", db_path=omop_path)
    state.server_status = {"available": True, "detail": "HTTPS reachable; login not checked"}
    missing = tmp_path / "missing-data"
    state.state["download_root"] = str(missing)
    rows = status_panel(state, 100).splitlines()
    assert "[OK]" in next(row for row in rows if "Databank:" in row)
    assert "[NO]" in next(row for row in rows if "Download location:" in row)
    assert not any("OMOP database:" in row for row in rows)
    assert "[NO]" in next(row for row in rows if "SMASH-HCM Manifest:" in row)
    assert not missing.exists()
    missing.mkdir()
    assert "[OK]" in next(row for row in status_panel(state, 100).splitlines() if "Download location:" in row)
    omop_path.unlink()
    assert "OMOP database:" not in status_panel(state, 100)


def test_authenticated_failure_does_not_override_server_reachability(tmp_path):
    state = Workspace(tmp_path / "state", tmp_path / "absent.env")
    state.server_status = {"available": True, "detail": "HTTPS reachable; login not checked"}
    state.connection_status = False
    rendered = status_panel(state, 100)
    assert "[OK]" in next(row for row in rendered.splitlines() if "SMASH-HCM Databank:" in row)
    assert "[NO]" in next(row for row in rendered.splitlines() if "Databank login:" in row)
    assert "Login/access failed" in rendered
    state.connection_status = True
    assert "[OK]" in next(row for row in status_panel(state, 100).splitlines() if "Databank login:" in row)


def test_successful_login_establishes_connectivity_after_probe_timeout(tmp_path):
    state = Workspace(tmp_path / "state", tmp_path / "absent.env")
    state.server_status = {"available": False, "detail": "HTTPS check timed out"}
    state.connection_status = True
    rows = status_panel(state, 100).splitlines()
    assert "[OK]" in next(row for row in rows if "SMASH-HCM Databank:" in row)
    assert "[OK]" in next(row for row in rows if "Databank login:" in row)
    assert "timed out" not in "\n".join(rows)
    assert all(len(row) == 100 for row in rows)


def test_real_menu_probes_once_before_first_status_and_offline_still_exits(tmp_path, monkeypatch):
    calls, output = [], []
    def probe():
        calls.append(True)
        return {"available": False, "detail": "HTTPS check timed out"}
    monkeypatch.setattr("smash_hcm_databank_client.menu.probe_server", probe)
    state = Workspace(tmp_path / "state", tmp_path / "absent.env")
    assert run_menu(state, read=lambda _: "5", write=output.append, plain=True) == 0
    assert len(calls) == 1 and "timed out" in "\n".join(output)
    assert not state.root.exists()  # Startup never saves credentials/state or creates folders.


def test_native_status_uses_green_red_styles_and_honors_no_color(tmp_path, monkeypatch):
    import prompt_toolkit
    import smash_hcm_databank_client.presentation as presentation
    state = Workspace(tmp_path / "state", tmp_path / "absent.env")
    state.server_status = {"available": True, "detail": "HTTPS reachable; login not checked"}
    captured = []
    monkeypatch.setattr(presentation.sys, "stdout", SimpleNamespace(isatty=lambda: True))
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(prompt_toolkit, "print_formatted_text", lambda parts, **kwargs: captured.append(parts))
    write_status(state)
    assert ("fg:ansigreen bold", "[OK]") in captured[0]
    assert ("fg:ansired bold", "[NO]") in captured[0]
    output = []
    write_status(state, output.append)
    assert "\x1b" not in output[0] and "[NO]" in output[0]
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setattr(presentation.sys, "stdout", SimpleNamespace(isatty=lambda: True, write=lambda s: None, flush=lambda: None))
    write_status(state)
    assert len(captured) == 1
