"""Opt-in data updates; verified new copies precede any old-file retirement."""
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import uuid

from .database import sha256
from .download_flow import confirm_location, size_label
from .manifest import ManifestError, is_database
from .nextcloud import NextcloudError
from .output import bundle, write_json
from .progress import DownloadProgress
from .prompts import choose, choose_many, confirm, text


def refresh_manifest(workspace, progress=None):
    """Use an ETag only with an intact cache; otherwise fetch/validate small JSON."""
    try:
        previous = workspace.manifest()
    except (OSError, ValueError):
        previous = None
    remote = workspace.state["manifest_remote_path"]
    version = workspace.state["manifest_version"]
    client = workspace.client()
    if previous is not None and version.get("etag") and version.get("remote_path") == remote and hasattr(client, "stat"):
        info = client.stat(remote)
        if info.get("is_directory"):
            raise NextcloudError("The manifest path identifies a folder")
        path = Path(workspace.state["manifest_path"])
        if info.get("etag") == version["etag"] and version.get("cache_sha256") == sha256(path):
            workspace.publish_manifest_copy()
            return {"status": "UNCHANGED", "manifest": previous}
    manifest = workspace.retrieve_manifest(remote, progress=progress)
    return {"status": "FIRST" if previous is None else "UNCHANGED" if previous == manifest else "UPDATED", "manifest": manifest}


def update_candidates(workspace):
    """Track exact paths or publisher-declared IDs; never guess by filename."""
    candidates = []
    for entry in workspace.manifest()["files"]:
        matches = [(remote, record) for remote, record in workspace.state["downloads"].items()
                   if (entry.get("artifact_id") and entry["artifact_id"] == record.get("artifact_id")) or remote == entry["path"]]
        if not matches:
            continue  # New catalogue items remain selectable in Download.
        if len(matches) != 1:
            raise NextcloudError("Ambiguous tracked artifact identity; review download records before updating")
        remote, record = matches[0]
        try:
            path = workspace._cached_path(record)
            missing = path.stat().st_size != record["size_bytes"]
        except (OSError, ValueError):
            missing = True
        changed = entry["sha256"] != record["sha256"] or entry["size_bytes"] != record["size_bytes"]
        if changed or missing:
            candidates.append({"entry": entry, "old_remote": remote, "old_record": dict(record), "reason": "updated" if changed else "missing or size changed"})
    return candidates


def retention_path(workspace, record):
    """Resolve and check the exact managed file before copy/delete on Windows."""
    raw = Path(record["local_path"])
    if raw.is_symlink() or any(parent.is_symlink() for parent in raw.parents):
        raise NextcloudError("Refusing to retire a file reached through a symbolic link")
    path = workspace._cached_path(record)
    roots = [(workspace.root / "downloads").resolve()] + [Path(root).resolve() for root in workspace.state["download_roots"]]
    if not any(root in path.parents for root in roots) or not path.is_file():
        raise NextcloudError("Only an exact tracked file inside a registered download directory can be retired")
    return path


def apply_update(workspace, candidate, retention="archive", progress=None):
    if retention not in ("keep", "archive", "replace"):
        raise NextcloudError("Choose keep, archive or replace")
    entry, remote, old = candidate["entry"], candidate["old_remote"], candidate["old_record"]
    if workspace.state["downloads"].get(remote) != old:
        raise NextcloudError("The tracked version changed; check for updates again")
    if workspace.state["active_db"] == old["local_path"] and not is_database(entry):
        raise NextcloudError("A selected database cannot be replaced with a different artifact type")
    # Modified local files can be kept/archived, but never deleted as a receipt-matched version.
    original = None
    if Path(old["local_path"]).exists():
        original = retention_path(workspace, old)
        if retention == "replace" and sha256(original) != old["sha256"]:
            raise NextcloudError("The local file was modified. Keep or archive it; replacement deletion is refused")
    item = {"remote_path": remote, "replacement_remote": entry["path"], "action": retention,
            "record": dict(old), "status": "update-pending" if original else "missing",
            "updated_utc": datetime.now(timezone.utc).isoformat()}
    # Journal the old receipt BEFORE installing/saving a new receipt. A crash
    # between download completion and retirement must not lose the old path.
    workspace.state["download_history"].append(item)
    workspace.save()
    try:
        result = workspace.download_entry(entry, progress)
    except (OSError, ValueError):
        item["status"] = "kept" if original else "missing"
        try:
            workspace.save()
        except OSError:
            pass  # The previously durable pending journal still references it.
        raise
    if Path(result["local_path"]).resolve() == Path(old["local_path"]).resolve():
        workspace.state["download_history"].remove(item)
        workspace.save()
        return {**result, "retention": "same verified copy"}
    item["status"] = "kept" if original else "missing"
    if remote != entry["path"]:
        workspace.state["downloads"].pop(remote, None)
    workspace.save()
    if original is None or retention == "keep":
        return {**result, "retention": item["status"]}
    if retention == "archive":
        archive_root = Path(workspace.state["download_root"]).resolve() if workspace.state["download_root"] else (workspace.root / "downloads").resolve()
        destination = archive_root / "archive" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:12])
        if archive_root not in destination.resolve().parents:
            raise NextcloudError("Archive destination must remain in the download directory")
        actual_hash = sha256(retention_path(workspace, old))
        with bundle(destination) as stage:
            shutil.copy2(original, stage / original.name)
            if sha256(stage / original.name) != actual_hash or sha256(retention_path(workspace, old)) != actual_hash:
                raise NextcloudError("The old file changed while archiving; it has not been deleted")
            archived = {**old, "local_path": str(destination / original.name), "sha256": actual_hash, "size_bytes": original.stat().st_size}
            write_json(stage / "archive_receipt.json", {"remote_path": remote, "record": archived, "original_receipt_sha256": old["sha256"]})
        item.update(status="archived", record=archived, original_path=str(original))
        workspace.save()
        # Verify the source still matches the archived bytes immediately before unlink.
        if sha256(retention_path(workspace, old)) != actual_hash:
            item["cleanup"] = "Original changed after archiving; retained"
            workspace.save()
            return {**result, "retention": "archived; changed original retained"}
    else:
        if sha256(retention_path(workspace, old)) != old["sha256"]:
            return {**result, "retention": "new copy installed; changed original retained"}
        item["status"] = "replacement-verified-pending-delete"
        workspace.save()
    try:
        # Single-file unlink only: never delete a folder, adjacent imaging, or exports.
        retention_path(workspace, old).unlink()
    except OSError:
        item["cleanup"] = "Original is locked or unavailable; retained"
        if retention == "replace":
            item["status"] = "kept"
        workspace.save()
        return {**result, "retention": "new copy installed; original retained (cleanup unavailable)"}
    if retention == "replace":
        item["status"] = "deleted"
    else:
        item["cleanup"] = "Original retired after verified archive"
    workspace.save()
    return {**result, "retention": item["status"]}


def check_updates(workspace, read=input, write=print, plain=False):
    """Called only after authenticated root access and a positive Y/N response."""
    # Keep this small catalogue check quiet; data files retain full progress.
    refreshed = refresh_manifest(workspace)
    write("Checking Databank manifest ... SUCCESS" + ("" if refreshed["status"] == "UNCHANGED" else " | " + refreshed["status"] + " | " + text(refreshed["manifest"]["release"])))
    if workspace.manifest_copy_notice:
        write(workspace.manifest_copy_notice)
    candidates = update_candidates(workspace)
    if not candidates:
        return []
    write("Updates/repairs available: " + str(len(candidates)) + ". Detection compares publisher checksums and file presence/size; use Validate for a full local hash check.")
    selected = choose_many(candidates, lambda item: item["entry"]["path"] + " | " + item["reason"] + " | " + size_label(item["entry"]["size_bytes"]), read, write, plain, message="Choose updated files to download (cancel keeps current versions)")
    if not selected:
        return []
    retention = choose(["archive", "keep", "replace"], lambda value: {"archive": "Archive old versions (recommended)", "keep": "Keep old versions in place", "replace": "Replace: DELETE tracked old files after verification"}[value], read, write, plain, message="What should happen to the old versions?")
    if retention is None:
        return []
    suffix = " | " + {"archive": "Archive", "keep": "Keep", "replace": "DELETE"}[retention] + " tracked old versions after verification"
    if confirm_location(workspace, read, write, plain, message="Download these updates to:", suffix=suffix) is None:
        return []
    results = []
    for candidate in selected:
        try:
            with DownloadProgress(candidate["entry"]["path"], write) as progress:
                result = apply_update(workspace, candidate, retention, progress)
            write("Update complete: " + text(candidate["entry"]["path"]) + " | " + result["retention"])
            results.append(result)
        except (OSError, ValueError) as exc:
            write("Update incomplete: " + text(candidate["entry"]["path"]) + " | " + text(exc) + ". Old files are retained unless retirement already completed; check version history.")
    return results


def check_login(workspace, write=print):
    """Check configured authentication before rendering status or asking updates."""
    if not workspace.login_configured():
        write("Databank login is not configured for this session; use Setup. Local tools remain available.")
        workspace.connection_status = None
        return False
    try:
        write("Checking configured login and databank access...")
        workspace.connection_status = False
        client = workspace.client()
        if hasattr(client, "timeout"):
            client.timeout = min(client.timeout, 8)
        result = client.check()
        if result.get("status") != "PASS":
            raise NextcloudError("Databank access check did not pass")
        workspace.connection_status = True
        write("Login and databank access: SUCCESS")
    except (OSError, ValueError):
        # Avoid reporting connector exceptions containing server/account details.
        write("Databank login/access check failed. Review Setup or retry later; local tools and cached downloads remain available.")
        return False
    return True


def startup_updates(workspace, read=input, write=print, plain=False, login_checked=False):
    if any(item.get("status") in ("update-pending", "replacement-verified-pending-delete") for item in workspace.state["download_history"]):
        write("An earlier update was interrupted. Old-version paths remain in local version history; no automatic cleanup will delete them.")
    if not login_checked:
        check_login(workspace, write)
    if workspace.connection_status is not True:
        return
    if not confirm("Check for data updates now?", read, write, plain, default=True):
        return
    try:
        check_updates(workspace, read, write, plain)
    except ManifestError as exc:
        write("Manifest validation failed: " + text(exc) + ". Your cached manifest and local files are retained; retry from Setup.")
    except NextcloudError as exc:
        if exc.status_code == 404:
            write("Databank access works, but manifest.json is not available (HTTP 404). The administrator must publish it. Your cached manifest is retained.")
        else:
            write("Could not refresh the databank manifest. Your cached manifest and local files are retained; retry from Setup.")
    except OSError:
        write("The update check could not complete. Cached manifest and local files are retained.")
