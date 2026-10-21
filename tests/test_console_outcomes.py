import io

import pytest

from smash_hcm_databank_client.console import STYLES, message_level, write_message
from smash_hcm_databank_client.progress import DownloadProgress


@pytest.mark.parametrize("message,level", [
    ("FAILED | archive.zip | hash mismatch", "failure"),
    ("FAILURE: database invalid", "failure"),
    ("manifest.json | FAILED; check the error", "failure"),
    ("Could not complete that option: unavailable", "failure"),
    ("Finished: 1 verified, 1 failed.", "failure"),
    ("Finished: 2 verified, 0 failed.", "success"),
    ("Connection: PASS (verified HTTPS WebDAV)", "success"),
    ("DOWNLOADED | size and SHA-256 verified", "success"),
    ("Download cancelled; no files were transferred.", "cancel"),
    ("CANCELLED; download stopped by user", "cancel"),
    ("SMASH menu closed.", "cancel"),
])
def test_log_outcomes(message, level):
    assert message_level(message) == level


def test_terminal_colors_and_plain_redirected_output(monkeypatch):
    import prompt_toolkit
    captured = []
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(prompt_toolkit, "print_formatted_text", lambda parts, **kwargs: captured.append(list(parts)))
    stream = io.StringIO()
    stream.isatty = lambda: True
    for level in ("failure", "success", "cancel"):
        write_message(level, level=level, stream=stream)
    assert captured == [[(style, level)] for level, style in [
        ("failure", "fg:ansired bold"), ("success", "fg:#006400 bold"), ("cancel", "fg:#ff8c00 bold")]]
    monkeypatch.setenv("NO_COLOR", "1")
    write_message("FAILED", stream=stream)
    assert stream.getvalue() == "FAILED\n"
    monkeypatch.delenv("NO_COLOR")
    stream.isatty = lambda: False
    write_message("PASS", stream=stream)
    assert stream.getvalue() == "FAILED\nPASS\n"
    assert len(captured) == 3


@pytest.mark.parametrize("exception", [KeyboardInterrupt, EOFError])
def test_user_stop_reports_orange_cancellation_without_failed_or_complete(monkeypatch, exception):
    captured = []
    monkeypatch.setattr("smash_hcm_databank_client.progress.write_message", lambda message, **kw: captured.append((message, kw["level"])))
    with pytest.raises(exception):
        with DownloadProgress("ecg.zip", stream=io.StringIO()):
            raise exception()
    assert len(captured) == 1
    message, level = captured[0]
    assert "CANCELLED" in message and "FAILED" not in message and "complete" not in message
    assert STYLES[level] == "fg:#ff8c00 bold"


def test_transfer_failure_is_red_and_success_is_dark_green(monkeypatch):
    captured = []
    monkeypatch.setattr("smash_hcm_databank_client.progress.write_message", lambda message, **kw: captured.append((message, kw["level"])))
    with pytest.raises(ValueError):
        with DownloadProgress("ecg.zip", stream=io.StringIO()):
            raise ValueError("hash mismatch")
    with DownloadProgress("ecg.zip", stream=io.StringIO()) as progress:
        progress(10, 10, "complete")
    assert "FAILED" in captured[0][0] and captured[0][1] == "failure"
    assert "complete" in captured[1][0] and captured[1][1] == "success"
