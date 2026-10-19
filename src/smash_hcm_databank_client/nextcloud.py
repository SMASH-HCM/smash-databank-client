"""Read-only Nextcloud WebDAV access, with local dotenv credentials.

No shell expansion, credential logging, cross-origin redirects, or server writes.
"""
from __future__ import annotations

import base64
import hashlib
import os
import re
import ssl
from dataclasses import dataclass, field
from http.client import HTTPException
from pathlib import Path, PurePosixPath
from urllib import error, parse, request
from xml.etree import ElementTree

from .output import bundle, write_json


class NextcloudError(ValueError):
    """Safe user-facing error: never includes response bodies or credentials."""

    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


def read_dotenv(path):
    values = {}
    try:
        lines = Path(path).read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        raise NextcloudError("Cannot read the selected .env file") from None
    for number, line in enumerate(lines, 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:]
        key, separator, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not separator or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise NextcloudError("Invalid .env assignment on line " + str(number))
        if key in values:
            raise NextcloudError("Duplicate .env variable on line " + str(number))
        if value.startswith(("'", '"')):
            closing = value.rfind(value[0])
            if closing == 0 or (value[closing + 1:].strip() and not value[closing + 1:].strip().startswith("#")):
                raise NextcloudError("Invalid quoted .env value on line " + str(number))
            value = value[1:closing]
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0].rstrip()
        # Deliberately literal: no eval, interpolation, backslash or shell expansion.
        values[key] = value
    return values


def remote_path(value):
    clean = str(value).replace("\\", "/")
    path = PurePosixPath(clean)
    if path.is_absolute() or ".." in path.parts or ":" in clean or any(ord(c) < 32 for c in clean):
        raise NextcloudError("Remote paths must be relative to the configured Nextcloud folder")
    return "/".join(part for part in path.parts if part != ".")


def https_url(value):
    if any(ord(c) < 32 for c in value):
        raise NextcloudError("Invalid Nextcloud URL")
    parts = parse.urlsplit(value)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise NextcloudError("Nextcloud URL must be an HTTPS server URL without embedded credentials, query or fragment")
    try:
        parts.port
    except ValueError:
        raise NextcloudError("Invalid Nextcloud URL port") from None
    return parts


def origin(url):
    parts = https_url(url)
    return parts.scheme, parts.hostname.casefold(), parts.port or 443


@dataclass(frozen=True, repr=False)
class NextcloudConfig:
    server_url: str
    username: str = field(repr=False)
    password: str = field(repr=False)
    remote_root: str = ""
    webdav_url: str = field(default="", repr=False)

    def __post_init__(self):
        https_url(self.server_url)
        remote_path(self.remote_root)
        if not isinstance(self.username, str) or not isinstance(self.password, str) or not self.username or not self.password or ":" in self.username or "/" in self.username or "\\" in self.username or any(ord(c) < 32 for c in self.username + self.password):
            raise NextcloudError("Invalid or empty username/password in local Nextcloud settings")
        if self.webdav_url and origin(self.webdav_url) != origin(self.server_url):
            raise NextcloudError("WebDAV override must use the same HTTPS server as NEXTCLOUD_URL")

    @classmethod
    def from_env(cls, env_file=".env", remote_root=None, environ=None):
        # An explicitly selected file takes precedence over process variables.
        values = dict(os.environ if environ is None else environ)
        values.update(read_dotenv(env_file))
        required = ("NEXTCLOUD_URL", "NEXTCLOUD_USERNAME", "NEXTCLOUD_PASSWORD")
        missing = [key for key in required if not values.get(key)]
        if missing:
            raise NextcloudError("Missing Nextcloud settings: " + ", ".join(missing))
        config = cls(values[required[0]].rstrip("/"), values[required[1]], values[required[2]],
                     remote_path(remote_root if remote_root is not None else values.get("NEXTCLOUD_REMOTE_ROOT", "")),
                     values.get("NEXTCLOUD_WEBDAV_URL", "").rstrip("/"))
        https_url(config.server_url)
        if ":" in config.username or "/" in config.username or "\\" in config.username or any(ord(c) < 32 for c in config.username + config.password):
            raise NextcloudError("Invalid username/password characters in local Nextcloud settings")
        if config.webdav_url and origin(config.webdav_url) != origin(config.server_url):
            raise NextcloudError("WebDAV override must use the same HTTPS server as NEXTCLOUD_URL")
        return config

    @property
    def base_url(self):
        if self.webdav_url:
            return self.webdav_url + "/"
        return self.server_url + "/remote.php/dav/files/" + parse.quote(self.username, safe="") + "/"


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # urllib otherwise forwards the explicit Authorization header.
        raise NextcloudError("Nextcloud redirected the request; set the canonical HTTPS server/WebDAV URL")


class NextcloudClient:
    def __init__(self, config, timeout=30, opener=None):
        self.config = config
        self.timeout = timeout
        self.opener = opener or request.build_opener(NoRedirect(), request.HTTPSHandler(context=ssl.create_default_context()))

    def url(self, relative="", folder=False):
        relative = remote_path(relative)
        joined = "/".join(part for part in (self.config.remote_root, relative) if part)
        suffix = "/".join(parse.quote(part, safe="") for part in joined.split("/") if part)
        return self.config.base_url + suffix + ("/" if folder and suffix else "")

    def _open(self, url, method="GET", data=None, headers=None):
        if origin(url) != origin(self.config.server_url):
            raise NextcloudError("Refusing credentials to a different server")
        token = base64.b64encode((self.config.username + ":" + self.config.password).encode("utf-8")).decode("ascii")
        req = request.Request(url, data=data, method=method, headers={
            "Authorization": "Basic " + token, "User-Agent": "smash-hcm-databank-client/0.12", **(headers or {})})
        try:
            return self.opener.open(req, timeout=self.timeout)
        except error.HTTPError as exc:
            status = exc.code
            exc.close()
            detail = {401: "Authentication failed; check the login and app password", 403: "Account does not have download/read permission", 404: "Folder or file not found; check the mounted folder path and WebDAV account ID", 429: "Server rate limit reached; retry later"}.get(status, "Nextcloud request failed")
            raise NextcloudError(detail + " (HTTP " + str(status) + ")", status_code=status) from None
        except (error.URLError, TimeoutError, OSError, HTTPException) as exc:
            reason = getattr(exc, "reason", exc)
            if getattr(reason, "winerror", None) == 10013:
                message = "Network access was blocked by the local execution environment"
            else:
                message = "Cannot establish a verified HTTPS connection to Nextcloud; check network/VPN, server URL and certificate trust"
            raise NextcloudError(message) from None

    @staticmethod
    def _read(response, size):
        try:
            return response.read(size)
        except (HTTPException, OSError) as exc:
            raise NextcloudError("Network transfer was interrupted; no completed download was published") from None

    def _properties(self, relative="", depth=0):
        url = self.url(relative, folder=not relative)
        body = b'<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop><d:resourcetype/><d:getcontentlength/><d:getcontenttype/><d:getetag/></d:prop></d:propfind>'
        with self._open(url, method="PROPFIND", data=body, headers={"Depth": str(depth), "Content-Type": "application/xml; charset=utf-8"}) as response:
            content = self._read(response, 2 * 1024 * 1024 + 1)
        if len(content) > 2 * 1024 * 1024 or b"<!DOCTYPE" in content.upper() or b"<!ENTITY" in content.upper():
            raise NextcloudError("Unsafe or oversized WebDAV response")
        try:
            root = ElementTree.fromstring(content)
        except ElementTree.ParseError:
            raise NextcloudError("Server did not return a valid WebDAV response; check server URL/app password") from None
        if root.tag != "{DAV:}multistatus":
            raise NextcloudError("Server did not return a WebDAV multistatus response")
        rows = []
        for item in root.findall("{DAV:}response"):
            href = item.findtext("{DAV:}href", "")
            absolute = parse.urljoin(url, href)
            if origin(absolute) != origin(self.config.server_url):
                raise NextcloudError("WebDAV response refers to a different server")
            prop = None
            for status in item.findall("{DAV:}propstat"):
                if re.search(r"\s200(?:\s|$)", status.findtext("{DAV:}status", "")):
                    prop = status.find("{DAV:}prop")
                    if prop is not None:
                        break
            if prop is None:
                continue
            size = prop.findtext("{DAV:}getcontentlength")
            if size and (not size.isdigit()):
                raise NextcloudError("Invalid WebDAV file size")
            rows.append({"path": parse.unquote(parse.urlsplit(absolute).path).rstrip("/"),
                         "is_directory": prop.find("{DAV:}resourcetype/{DAV:}collection") is not None,
                         "size_bytes": int(size) if size else None, "etag": prop.findtext("{DAV:}getetag"),
                         "content_type": prop.findtext("{DAV:}getcontenttype")})
        return rows

    def stat(self, relative=""):
        target = parse.unquote(parse.urlsplit(self.url(relative)).path).rstrip("/")
        matches = [row for row in self._properties(relative) if row["path"] == target]
        if len(matches) != 1:
            raise NextcloudError("WebDAV metadata does not identify the requested file/folder")
        return matches[0]

    def check(self):
        info = self.stat()
        if not info["is_directory"]:
            raise NextcloudError("Configured remote root is not a folder")
        return {"status": "PASS", "protocol": "HTTPS WebDAV", "remote_root": self.config.remote_root or "/", "access": "read"}

    def list(self, relative=""):
        target = parse.unquote(parse.urlsplit(self.url(relative)).path).rstrip("/")
        rows = self._properties(relative, depth=1)
        result = []
        for row in rows:
            if row["path"] == target:
                continue
            prefix = target + "/"
            if not row["path"].startswith(prefix) or "/" in row["path"][len(prefix):]:
                raise NextcloudError("WebDAV listing contained an unexpected path")
            result.append({"name": row["path"][len(prefix):], "is_directory": row["is_directory"], "size_bytes": row["size_bytes"]})
        return sorted(result, key=lambda row: row["name"])

    def download(self, relative, destination, expected_sha256=None, max_bytes=16 * 1024 * 1024, expected_size=None, progress=None):
        relative = remote_path(relative)
        if not relative or max_bytes <= 0:
            raise NextcloudError("Specify a file and a positive download size limit")
        if expected_sha256 and not re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha256):
            raise NextcloudError("Expected SHA-256 must contain 64 hexadecimal characters")
        info = self.stat(relative)
        if info["is_directory"]:
            raise NextcloudError("Download selects one file, not a folder/archive")
        if info["size_bytes"] is not None and info["size_bytes"] > max_bytes:
            raise NextcloudError("Remote file exceeds the configured download size limit")
        if expected_size is not None and info["size_bytes"] is not None and expected_size != info["size_bytes"]:
            raise NextcloudError("Remote file size does not match the selected manifest entry")
        filename = PurePosixPath(relative).name
        if filename == "download_receipt.json":
            raise NextcloudError("This filename is reserved for the local download receipt")
        headers = {"Accept-Encoding": "identity"}
        if info["etag"]:
            if any(ord(c) < 32 for c in info["etag"]):
                raise NextcloudError("Invalid WebDAV version marker")
            headers["If-Match"] = info["etag"]
        digest, count = hashlib.sha256(), 0
        with bundle(destination) as stage:
            with self._open(self.url(relative), headers=headers) as response:
                content_type = response.headers.get("Content-Type", "").lower()
                if content_type.startswith("text/html") or content_type.startswith("application/xhtml"):
                    raise NextcloudError("Server returned HTML rather than the requested file; check the WebDAV URL/authentication")
                length = response.headers.get("Content-Length")
                if length is not None and not length.isdigit():
                    raise NextcloudError("Invalid download Content-Length")
                total = expected_size if expected_size is not None else info["size_bytes"] if info["size_bytes"] is not None else int(length) if length is not None else None
                if progress:
                    progress(0, total, "transfer")
                with (stage / filename).open("wb") as handle:
                    while True:
                        block = self._read(response, min(1024 * 1024, max_bytes - count + 1))
                        if not block:
                            break
                        count += len(block)
                        if count > max_bytes:
                            raise NextcloudError("Download exceeded the configured size limit")
                        digest.update(block)
                        handle.write(block)
                        if progress:
                            progress(count, total, "transfer")
                if (length is not None and int(length) != count) or (info["size_bytes"] is not None and info["size_bytes"] != count):
                    raise NextcloudError("Download was incomplete or remote size changed")
                if expected_size is not None and count != expected_size:
                    raise NextcloudError("Downloaded byte count does not match the manifest")
                returned_etag = response.headers.get("ETag")
                if returned_etag and info["etag"] and returned_etag != info["etag"]:
                    raise NextcloudError("Remote file changed during download")
            checksum = digest.hexdigest()
            if expected_sha256 and checksum != expected_sha256.lower():
                raise NextcloudError("Downloaded file SHA-256 does not match the expected checksum")
            receipt = {"status": "PASS", "remote_root": self.config.remote_root, "remote_path": relative,
                       "filename": filename, "size_bytes": count, "sha256": checksum,
                       "expected_sha256_verified": bool(expected_sha256), "etag": info["etag"],
                       "transport": "HTTPS WebDAV", "integrity_scope": "Local SHA-256; trusted-content verification requires an expected manifest hash."}
            write_json(stage / "download_receipt.json", receipt)
        if progress:
            progress(count, total, "complete")
        return receipt
