"""Local menu state, manifest cache, file verification and active database."""
import json
import os
import re
import sqlite3
import sys
from pathlib import Path
import uuid

from .credentials import env_credentials, load_vault
from .assets import validate_asset
from .database import OmopDatabase, sha256
from .manifest import is_database, load_manifest
from .nextcloud import NextcloudClient, NextcloudConfig, NextcloudError, origin, remote_path
from .output import write_json
from .settings import SMASH_MANIFEST, SMASH_REMOTE_ROOT, SMASH_URL


def default_state_dir():
    if not getattr(sys, "frozen", False) and Path(".smash/state.json").is_file():
        return Path(".smash")  # Preserve existing checkout profiles.
    return Path.home() / ".smash" / "omop-exporter"


def default_env_file(state_dir=None):
    if not getattr(sys, "frozen", False) and Path(".env").is_file():
        return Path(".env")
    return Path(state_dir or default_state_dir()) / ".env"


class Workspace:
    def __init__(self, state_dir=".smash", env_file=".env", db_path=None, client_factory=None):
        self.root = Path(state_dir).expanduser().resolve()
        self.env_file = Path(env_file).expanduser().resolve()
        self.client_factory = client_factory or NextcloudClient
        self.session = None
        self.connection_status = None  # Last explicit root check in this process only.
        self.server_status = None  # Credential-free startup HTTPS check, never persisted.
        self.discovery_message = ""
        self.state = {"schema_version": 1, "profile": {}, "downloads": {}, "manifest_path": "", "manifest_remote_path": SMASH_MANIFEST, "manifest_version": {}, "download_history": [], "active_db": "", "download_root": "", "download_roots": []}
        path = self.root / "state.json"
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if data.get("schema_version") != 1 or not isinstance(data.get("downloads", {}), dict) or not isinstance(data.get("profile", {}), dict):
                    raise ValueError()
                profile = data.get("profile", {})
                if any(key in profile for key in ("password", "NEXTCLOUD_PASSWORD")):
                    raise ValueError()
                if profile.get("credential_storage") not in (None, "vault", "env", "session"):
                    raise ValueError()
                if any(not isinstance(profile.get(key, ""), str) for key in ("username", "webdav_url")):
                    raise ValueError()
                if profile.get("credential_storage") and not profile.get("username"):
                    raise ValueError()
                if any(not isinstance(data.get(key, ""), str) for key in ("active_db", "manifest_path", "manifest_remote_path", "download_root")):
                    raise ValueError()
                roots = data.get("download_roots", [])
                if not isinstance(data.get("manifest_version", {}), dict) or not isinstance(data.get("download_history", []), list):
                    raise ValueError()
                for historical in data.get("download_history", []):
                    if not isinstance(historical, dict) or not isinstance(historical.get("record"), dict) or not isinstance(historical.get("status"), str):
                        raise ValueError()
                    record = historical["record"]
                    if not isinstance(record.get("local_path"), str) or not isinstance(record.get("sha256"), str) or type(record.get("size_bytes")) is not int:
                        raise ValueError()
                if not isinstance(roots, list) or any(not isinstance(root, str) or not Path(root).is_absolute() for root in roots):
                    raise ValueError()
                if data.get("download_root") and (not Path(data["download_root"]).is_absolute() or data["download_root"] not in roots):
                    raise ValueError()
                for record in data.get("downloads", {}).values():
                    if not isinstance(record, dict) or not isinstance(record.get("local_path"), str) or not isinstance(record.get("sha256"), str) or type(record.get("size_bytes")) is not int:
                        raise ValueError()
                self.state.update({key: data[key] for key in self.state if key in data})
            except (ValueError, TypeError, AttributeError):
                raise NextcloudError("Local SMASH settings are invalid; inspect the state.json file") from None
        candidate = db_path or os.environ.get("OMOP_EXPORTER_DB")
        if candidate:
            self.state["active_db"] = str(Path(candidate).expanduser().resolve())
        elif not self.state["active_db"]:
            config = Path("config.json")
            if config.exists():
                try:
                    configured = json.loads(config.read_text(encoding="utf-8")).get("db")
                    if configured:
                        self.state["active_db"] = str((config.parent / configured).resolve())
                except (ValueError, AttributeError):
                    pass
            if not self.state["active_db"]:
                # Only discover this application's download locations, never scan drives.
                candidates = list((self.root / "downloads").glob("*/*.db")) + list(Path("downloads").glob("*/*.db"))
                if len(candidates) == 1:
                    self.state["active_db"] = str(candidates[0].resolve())

    def save(self):
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self.root / ("state-" + uuid.uuid4().hex + ".part")
        try:
            write_json(temporary, self.state)
            os.replace(temporary, self.root / "state.json")
        finally:
            if temporary.exists():
                temporary.unlink()

    def database_available(self):
        """Check schema/readability without hashing or reading patient records."""
        try:
            with OmopDatabase(self.state["active_db"]) as database:
                return "person_id" in database.columns("person")
        except (OSError, ValueError, sqlite3.Error):
            return False

    def refresh_local(self):
        """Recover a unique database in confirmed download locations at startup.

        Inspect only receipts and the fixed download layout, never whole drives.
        Multiple valid candidates require an explicit user choice.
        """
        directory = self.state["download_root"]
        if directory:
            try:
                Path(directory).mkdir(parents=True, exist_ok=True)
            except OSError:
                self.discovery_message = "The saved download directory is currently unavailable."
        if self.database_available():
            return
        candidates = set()
        for record in self.state["downloads"].values():
            try:
                candidates.add(str(self._cached_path(record)))
            except (OSError, ValueError):
                pass
        roots = [self.root / "downloads"] + ([Path(directory)] if directory else [])
        for root in roots:
            for suffix in ("db", "sqlite", "sqlite3"):
                for pattern in ("*." + suffix, "*/*." + suffix, "*/*/*." + suffix):
                    try:
                        candidates.update(str(path.resolve()) for path in root.glob(pattern)
                                          if path.is_file() and not path.is_symlink() and root.resolve() in path.resolve().parents)
                    except OSError:
                        pass
        valid = []
        for candidate in sorted(candidates):
            try:
                with OmopDatabase(candidate) as database:
                    if "person_id" in database.columns("person"):
                        valid.append(str(database.path))
            except (OSError, ValueError, sqlite3.Error):
                pass
        valid = sorted(set(valid))
        if len(valid) == 1:
            self.register_database(valid[0])
            self.discovery_message = "Found the local OMOP database: " + Path(valid[0]).name
        elif len(valid) > 1:
            self.discovery_message = "Multiple local OMOP databases found; use Validate > Select a local OMOP database."

    def client(self):
        if self.session is not None:
            config = self.session
        else:
            profile = self.state["profile"]
            if profile.get("credential_storage") == "vault":
                config = NextcloudConfig(SMASH_URL, profile["username"], load_vault(profile["username"]), SMASH_REMOTE_ROOT, profile.get("webdav_url", ""))
            elif profile.get("credential_storage") == "session":
                raise NextcloudError("The previous session password was not retained; select Set up / change login")
            else:
                env = env_credentials(self.env_file)
                if not env.get("NEXTCLOUD_USERNAME") or not env.get("NEXTCLOUD_PASSWORD"):
                    raise NextcloudError("No credentials are available. Select Set up / change login first.")
                config = NextcloudConfig(env.get("NEXTCLOUD_URL", SMASH_URL).rstrip("/"), env["NEXTCLOUD_USERNAME"], env["NEXTCLOUD_PASSWORD"], SMASH_REMOTE_ROOT, env.get("NEXTCLOUD_WEBDAV_URL", "").rstrip("/"))
        if origin(config.server_url) != origin(SMASH_URL):
            raise NextcloudError("This menu connects only to the SMASH databank server")
        return self.client_factory(config)

    def login_configured(self):
        """Inspect configuration without retrieving a vault password."""
        profile = self.state["profile"]
        if self.session is not None or (profile.get("credential_storage") == "vault" and profile.get("username")):
            return True
        if profile.get("credential_storage") == "session":
            return False
        try:
            env = env_credentials(self.env_file)
            return bool(env.get("NEXTCLOUD_USERNAME") and env.get("NEXTCLOUD_PASSWORD"))
        except (OSError, ValueError):
            return False

    def manifest(self):
        if not self.state["manifest_path"]:
            raise NextcloudError("Retrieve or load a manifest first. Single-file downloads and local database tools remain available.")
        path = Path(self.state["manifest_path"]).resolve()
        if self.root not in path.parents:
            raise NextcloudError("Manifest cache path is outside this workspace")
        return load_manifest(path)

    def retrieve_manifest(self, remote=None, progress=None):
        remote = remote_path(remote or self.state["manifest_remote_path"])
        destination = self.root / "manifests" / uuid.uuid4().hex
        self.client().download(remote, destination, max_bytes=8 * 1024 * 1024, **({"progress": progress} if progress else {}))
        path = destination / Path(remote).name
        manifest = load_manifest(path)
        self.state.update(manifest_path=str(path), manifest_remote_path=remote)
        receipt_path = destination / "download_receipt.json"
        receipt = json.loads(receipt_path.read_text()) if receipt_path.is_file() else {}
        self.state["manifest_version"] = {"etag": receipt.get("etag"), "remote_path": remote, "cache_sha256": sha256(path)}
        self.save()
        return manifest

    def use_manifest(self, source):
        manifest = load_manifest(source)
        destination = self.root / "manifests" / uuid.uuid4().hex
        destination.mkdir(parents=True)
        path = destination / "manifest.json"
        write_json(path, manifest)
        self.state["manifest_path"] = str(path)
        self.state["manifest_version"] = {}
        self.save()
        return manifest

    def _cached_path(self, record):
        path = Path(record["local_path"]).resolve()
        roots = [(self.root / "downloads").resolve()] + [Path(root).resolve() for root in self.state["download_roots"]]
        if not any(root in path.parents for root in roots) or not path.is_file():
            raise NextcloudError("Cached file is missing or outside this workspace")
        return path

    def suggested_download_root(self):
        return Path(self.state["download_root"]) if self.state["download_root"] else Path.home() / "SMASH-HCM"

    def set_download_root(self, path):
        if not str(path).strip():
            raise NextcloudError("Choose a download folder")
        root = Path(path).expanduser().resolve()
        if root.exists() and not root.is_dir():
            raise NextcloudError("Download location must be a folder")
        # Called only after the user confirms this choice; persist nonsecret state.
        root.mkdir(parents=True, exist_ok=True)
        self.state["download_root"] = str(root)
        if str(root) not in self.state["download_roots"]:
            self.state["download_roots"].append(str(root))
        self.save()
        return root

    def _destination(self, remote, release="files"):
        if not self.state["download_root"]:
            return self.root / "downloads" / uuid.uuid4().hex
        def slug(value):
            return re.sub(r"[^a-zA-Z0-9_-]", "-", value)[:70].strip("-") or "files"
        return Path(self.state["download_root"]) / slug(release) / (slug(Path(remote).stem) + "-" + uuid.uuid4().hex[:8])

    def download_entry(self, entry, progress=None):
        manifest = self.manifest()
        # Resolve against the loaded manifest, never trust a caller's replacement hash.
        matches = [item for item in manifest["files"] if item["path"] == entry["path"] and item["sha256"] == entry["sha256"]]
        if len(matches) != 1:
            raise NextcloudError("Selected file does not match the current manifest")
        entry = matches[0]
        old = self.state["downloads"].get(entry["path"])
        same_root = not self.state["download_root"] or (old and Path(self.state["download_root"]).resolve() in Path(old["local_path"]).resolve().parents)
        if old and old.get("sha256") == entry["sha256"] and same_root:
            try:
                path = self._cached_path(old)
                if path.stat().st_size == entry["size_bytes"] and sha256(path) == entry["sha256"]:
                    if is_database(entry):
                        self.register_database(path)
                    if progress:
                        progress(entry["size_bytes"], entry["size_bytes"], "cached")
                    return {"status": "CACHED", "local_path": str(path), "size_bytes": entry["size_bytes"]}
            except (OSError, ValueError):
                pass  # An explicit download action creates a fresh verified copy.
        destination = self._destination(entry["path"], manifest["release"])
        self.client().download(entry["path"], destination, expected_sha256=entry["sha256"], max_bytes=max(1, entry["size_bytes"]), expected_size=entry["size_bytes"], **({"progress": progress} if progress else {}))
        path = destination / Path(entry["path"]).name
        if is_database(entry):
            with OmopDatabase(path) as database:
                if not database.capabilities()["persons"]:
                    raise NextcloudError("Downloaded file does not contain an OMOP person table; the previous database remains selected")
        record = {"local_path": str(path), "sha256": entry["sha256"], "size_bytes": entry["size_bytes"], "release": manifest["release"], "checksum_source": "manifest",
                  "artifact_id": entry.get("artifact_id"), "version": entry.get("version"), "kind": entry.get("kind")}
        self.state["downloads"][entry["path"]] = record
        self.save()
        if is_database(entry):
            self.register_database(path)
        return {"status": "DOWNLOADED", **record}

    def download_file(self, remote, progress=None):
        remote = remote_path(remote)
        destination = self._destination(remote)
        receipt = self.client().download(remote, destination, **({"progress": progress} if progress else {}))
        record = {"local_path": str(destination / Path(remote).name), "sha256": receipt["sha256"], "size_bytes": receipt["size_bytes"], "checksum_source": "download_receipt"}
        self.state["downloads"][remote] = record
        self.save()
        return record

    def verify_local(self):
        try:
            current = {entry["path"]: entry for entry in self.manifest()["files"]} if self.state["manifest_path"] else {}
        except (ValueError, OSError):
            current = {}  # Recorded download hashes still allow offline checks.
        rows = []
        for remote, record in sorted(self.state["downloads"].items()):
            expected = current.get(remote) or record
            status, detail = "FAIL", "Missing, unreadable or outside registered download locations"
            try:
                path = self._cached_path(record)
                status = "PASS" if path.stat().st_size == expected["size_bytes"] and sha256(path) == expected["sha256"] else "FAIL"
                detail = "Present; size and checksum match" if status == "PASS" else "File size or SHA-256 differs from the reference"
            except (OSError, ValueError, KeyError):
                pass
            rows.append({"path": remote, "status": status, "detail": detail, "reference": "manifest" if remote in current else record.get("checksum_source", "unknown")})
        for historical in self.state["download_history"]:
            if historical.get("status") not in ("kept", "archived", "update-pending", "replacement-verified-pending-delete"):
                continue
            record = historical.get("record", {})
            if any(current_record["local_path"] == record.get("local_path") for current_record in self.state["downloads"].values()):
                continue
            try:
                path = self._cached_path(record)
                valid = path.stat().st_size == record["size_bytes"] and sha256(path) == record["sha256"]
            except (OSError, ValueError, KeyError):
                valid = False
            rows.append({"path": historical.get("remote_path", "") + " [" + historical["status"] + "]", "status": "PASS" if valid else "FAIL",
                         "detail": "Historical version checked against its recorded hash", "reference": "version history"})
        active = self.state["active_db"]
        if active and not any(record.get("local_path") == active for record in self.state["downloads"].values()):
            path = Path(active)
            expected = [entry for entry in current.values() if Path(entry["path"]).name == path.name and is_database(entry)]
            if len(expected) == 1 and path.is_file():
                item = expected[0]
                rows.append({"path": path.name, "status": "PASS" if path.stat().st_size == item["size_bytes"] and sha256(path) == item["sha256"] else "FAIL", "reference": "manifest"})
            else:
                rows.append({"path": path.name, "status": "NO EXPECTED CHECKSUM", "reference": "unregistered external database"})
        return rows

    def register_database(self, path):
        path = Path(path).expanduser().resolve(strict=True)
        with OmopDatabase(path) as database:
            if not database.capabilities()["persons"]:
                raise NextcloudError("This file does not contain an OMOP person table")
        self.state["active_db"] = str(path)
        self.save()

    def verify_folder(self, root):
        rows = []
        for entry in self.manifest()["files"]:
            try:
                validate_asset(root, {"relative_path": entry["path"], "size_bytes": entry["size_bytes"], "sha256": entry["sha256"]})
                status = "PASS"
            except (OSError, ValueError):
                status = "FAIL"
            rows.append({"path": entry["path"], "status": status, "reference": "manifest"})
        return rows

    def database_info(self):
        path = self.state["active_db"]
        if not path:
            return "Not downloaded or selected"
        try:
            with OmopDatabase(path) as database:
                release = database.release_metadata().get("release")
            if not release:
                for record in self.state["downloads"].values():
                    if record.get("local_path") == path:
                        release = record.get("release")
                        break
            return str(release or "version not recorded") + " | " + Path(path).name
        except (OSError, ValueError, sqlite3.Error):
            return "Selected database is unavailable: " + Path(path).name
