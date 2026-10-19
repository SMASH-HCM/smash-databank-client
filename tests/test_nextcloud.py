import hashlib
import io
import json
from http.client import IncompleteRead
from urllib import error, request

import pytest

from omop_exporter.cli import main
from omop_exporter.nextcloud import NextcloudClient, NextcloudConfig, NextcloudError, NoRedirect, read_dotenv, remote_path


class Response(io.BytesIO):
    def __init__(self, body, headers=None):
        super().__init__(body)
        self.headers = headers or {}


class FakeOpener:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def open(self, req, timeout):
        self.calls.append(req)
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


def metadata(path="/remote.php/dav/files/test-user/databank/README.md", content=b"# Fixture\n", directory=False, etag='"fixture"'):
    kind = "<d:collection/>" if directory else ""
    return Response(('''<d:multistatus xmlns:d="DAV:"><d:response><d:href>''' + path + '''</d:href><d:propstat><d:prop><d:resourcetype>''' + kind + '''</d:resourcetype><d:getcontentlength>''' + str(len(content)) + '''</d:getcontentlength><d:getetag>''' + etag + '''</d:getetag></d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response></d:multistatus>''').encode())


@pytest.fixture
def config():
    return NextcloudConfig("https://cloud.example.org", "test-user", "fake-password", "databank")


def test_env_literals_quotes_comments_and_no_secret_repr(tmp_path):
    env = tmp_path / ".env"
    env.write_text("NEXTCLOUD_URL=https://cloud.example.org\nNEXTCLOUD_USERNAME=test-user\nNEXTCLOUD_PASSWORD='fake$pass#word=42' # comment\nNEXTCLOUD_REMOTE_ROOT=databank\n")
    config = NextcloudConfig.from_env(env, environ={})
    assert config.password == "fake$pass#word=42"
    assert config.remote_root == "databank"
    assert "fake$pass" not in repr(config) and "test-user" not in repr(config)
    assert "${PASSWORD}" == read_dotenv(write_env(tmp_path, "TEST=${PASSWORD}"))["TEST"]


def write_env(tmp_path, text):
    p = tmp_path / "test.env"
    p.write_text(text)
    return p


@pytest.mark.parametrize("text", ["PASSWORD='super-secret", "PASSWORD='super-secret' unexpected", "not-an-assignment-super-secret", "PASSWORD=super-secret\nPASSWORD=again"])
def test_bad_env_does_not_echo_values(tmp_path, text):
    with pytest.raises(NextcloudError) as exc:
        read_dotenv(write_env(tmp_path, text))
    assert "super-secret" not in str(exc.value)


def test_missing_settings_report_names_only(tmp_path):
    with pytest.raises(NextcloudError, match="NEXTCLOUD_PASSWORD"):
        NextcloudConfig.from_env(write_env(tmp_path, "NEXTCLOUD_URL=https://cloud.example.org\nNEXTCLOUD_USERNAME=test-user"), environ={})


@pytest.mark.parametrize("server", ["http://cloud.example.org", "https://name:secret@cloud.example.org", "https://cloud.example.org/?token=secret", "https://cloud.example.org/#fragment"])
def test_insecure_or_credential_urls_rejected(tmp_path, server):
    with pytest.raises(NextcloudError):
        NextcloudConfig.from_env(write_env(tmp_path, "NEXTCLOUD_URL=" + server + "\nNEXTCLOUD_USERNAME=user\nNEXTCLOUD_PASSWORD=secret"), environ={})


def test_override_cannot_change_server(tmp_path):
    with pytest.raises(NextcloudError, match="same HTTPS server"):
        NextcloudConfig.from_env(write_env(tmp_path, "NEXTCLOUD_URL=https://cloud.example.org\nNEXTCLOUD_USERNAME=user\nNEXTCLOUD_PASSWORD=secret\nNEXTCLOUD_WEBDAV_URL=https://other.example.org/remote.php/dav/files/user/"), environ={})


def test_paths_encoded_and_traversal_rejected(config):
    client = NextcloudClient(config, opener=FakeOpener([]))
    assert client.url("with spaces/README.md").endswith("databank/with%20spaces/README.md")
    for path in ("../secret", "/absolute", "https://other.example.org/", "C:\\secret"):
        with pytest.raises(NextcloudError):
            remote_path(path)


def test_redirects_never_forward_credentials():
    req = request.Request("https://cloud.example.org/file", headers={"Authorization": "Basic fake-secret"})
    with pytest.raises(NextcloudError, match="redirected"):
        NoRedirect().redirect_request(req, None, 302, "redirect", {}, "https://other.example.org/")


def test_check_only_reads_configured_root(config):
    opener = FakeOpener([metadata(path="/remote.php/dav/files/test-user/databank/", directory=True)])
    assert NextcloudClient(config, opener=opener).check()["status"] == "PASS"
    assert opener.calls[0].get_method() == "PROPFIND"
    assert opener.calls[0].get_header("Depth") == "0"
    assert opener.calls[0].full_url == "https://cloud.example.org/remote.php/dav/files/test-user/databank/"


def test_manifest_url_has_no_display_separator_and_http_status_is_structured(config):
    url = "https://cloud.example.org/remote.php/dav/files/test-user/databank/manifest.json"
    opener = FakeOpener([error.HTTPError(url, 404, "Not Found", {}, io.BytesIO(b"private server body"))])
    client = NextcloudClient(config, opener=opener)
    assert client.url("manifest.json") == url
    assert not any(char.isspace() for char in client.url("manifest.json"))
    with pytest.raises(NextcloudError) as exc:
        client.stat("manifest.json")
    assert exc.value.status_code == 404
    assert "private server body" not in str(exc.value)


def test_download_and_credential_free_receipt(config, tmp_path):
    content = b"# Fixture\n"
    opener = FakeOpener([metadata(content=content), Response(content, {"Content-Length": str(len(content)), "Content-Type": "text/markdown", "ETag": '"fixture"'})])
    out = tmp_path / "download"
    result = NextcloudClient(config, opener=opener).download("README.md", out, hashlib.sha256(content).hexdigest())
    assert (out / "README.md").read_bytes() == content
    assert result["expected_sha256_verified"]
    receipt = (out / "download_receipt.json").read_text()
    assert "fake-password" not in receipt and "Authorization" not in receipt and "test-user" not in receipt
    assert json.loads(receipt)["size_bytes"] == len(content)
    assert opener.calls[1].get_header("If-match") == '"fixture"'
    assert all(req.get_method() in ("PROPFIND", "GET") for req in opener.calls)


def test_progress_reports_bytes_and_completes_only_after_publication(config, tmp_path):
    content = b"a" * (1024 * 1024 + 50)
    opener = FakeOpener([metadata(content=content), Response(content)])
    output, events = tmp_path / "download", []
    def progress(count, total, phase):
        if phase == "complete":
            assert (output / "README.md").is_file()
        events.append((count, total, phase))
    NextcloudClient(config, opener=opener).download("README.md", output, hashlib.sha256(content).hexdigest(), progress=progress)
    assert events[0] == (0, len(content), "transfer")
    assert events[-1] == (len(content), len(content), "complete")
    assert [count for count, _, _ in events] == sorted(count for count, _, _ in events)


def test_hash_failure_never_reports_progress_complete(config, tmp_path):
    content = b"wrong"
    opener = FakeOpener([metadata(content=content), Response(content)])
    events = []
    with pytest.raises(NextcloudError, match="SHA-256"):
        NextcloudClient(config, opener=opener).download("README.md", tmp_path / "download", "0" * 64, progress=lambda *args: events.append(args))
    assert not (tmp_path / "download").exists() and not any(event[2] == "complete" for event in events)


@pytest.mark.parametrize("mode", ["wrong-hash", "short", "oversized", "html", "changed-etag"])
def test_bad_download_not_published(config, tmp_path, mode):
    content = b"# Fixture\n"
    headers = {"Content-Length": str(len(content)), "Content-Type": "text/plain", "ETag": '"fixture"'}
    if mode == "short":
        headers["Content-Length"] = str(len(content) + 1)
    if mode == "html":
        headers["Content-Type"] = "text/html"
    if mode == "changed-etag":
        headers["ETag"] = '"changed"'
    out = tmp_path / "failed"
    opener = FakeOpener([metadata(content=content), Response(content, headers)])
    with pytest.raises(NextcloudError):
        NextcloudClient(config, opener=opener).download("README.md", out, "0" * 64 if mode == "wrong-hash" else None, 1 if mode == "oversized" else 100)
    assert not out.exists()
    assert not list(tmp_path.glob(".omop-exporter-*"))


def test_authentication_error_does_not_echo_server_body(config):
    failure = error.HTTPError("https://cloud.example.org/private-user", 401, "fake-password", {}, io.BytesIO(b"fake-password"))
    with pytest.raises(NextcloudError) as exc:
        NextcloudClient(config, opener=FakeOpener([failure])).check()
    assert "HTTP 401" in str(exc.value) and "fake-password" not in str(exc.value)


def test_unsafe_xml_is_rejected(config):
    with pytest.raises(NextcloudError, match="Unsafe"):
        NextcloudClient(config, opener=FakeOpener([Response(b'<!DOCTYPE test [<!ENTITY x "secret">]><root/>')])).check()


def test_cli_check_does_not_require_omop_database(tmp_path, monkeypatch, capsys):
    env = write_env(tmp_path, "NEXTCLOUD_URL=https://cloud.example.org\nNEXTCLOUD_USERNAME=user\nNEXTCLOUD_PASSWORD=secret")
    monkeypatch.setattr(NextcloudClient, "check", lambda self: {"status": "PASS"})
    assert main(["nextcloud", "check", "--env-file", str(env), "--remote-root", "databank"]) == 0
    assert "secret" not in capsys.readouterr().out


def test_interrupted_transfer_is_sanitized_and_not_published(config, tmp_path):
    class Interrupted(Response):
        def read(self, size):
            raise IncompleteRead(b"fake-password-response-content", 100)
    opener = FakeOpener([metadata(), Interrupted(b"", {"Content-Type": "text/plain"})])
    out = tmp_path / "interrupted"
    with pytest.raises(NextcloudError) as exc:
        NextcloudClient(config, opener=opener).download("README.md", out)
    assert "fake-password" not in str(exc.value)
    assert not out.exists()


def test_reserved_receipt_filename_is_rejected(config, tmp_path):
    path = "/remote.php/dav/files/test-user/databank/download_receipt.json"
    with pytest.raises(NextcloudError, match="reserved"):
        NextcloudClient(config, opener=FakeOpener([metadata(path=path)])).download("download_receipt.json", tmp_path / "reserved")


def test_dotenv_explicit_file_and_remote_root_override(tmp_path):
    env = write_env(tmp_path, "NEXTCLOUD_URL=https://cloud.example.org\nNEXTCLOUD_USERNAME=file-user\nNEXTCLOUD_PASSWORD=file-password\nNEXTCLOUD_REMOTE_ROOT=old-folder")
    config = NextcloudConfig.from_env(env, remote_root="databank", environ={"NEXTCLOUD_USERNAME": "process-user"})
    assert config.username == "file-user"
    assert config.remote_root == "databank"


def test_listing_is_nonrecursive_and_only_reports_children(config):
    own = metadata(path="/remote.php/dav/files/test-user/databank/", directory=True).getvalue().decode()
    child = metadata().getvalue().decode()
    combined = own.replace("</d:multistatus>", "") + child.split(">", 1)[1]
    opener = FakeOpener([Response(combined.encode())])
    assert NextcloudClient(config, opener=opener).list() == [{"name": "README.md", "is_directory": False, "size_bytes": 10}]
    assert opener.calls[0].get_header("Depth") == "1"
