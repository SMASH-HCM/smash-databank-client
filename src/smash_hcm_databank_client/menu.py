"""Interactive SMASH setup and data menu, backed by the same tested APIs."""
import getpass
from pathlib import Path
import sqlite3
import sys
import warnings
import webbrowser

from .credentials import env_credentials, load_vault, native_vault, save_env, save_vault
from .database import OmopDatabase
from .exports import export_events
from .nextcloud import NextcloudConfig, NextcloudError
from .settings import DATA_ACCESS_URL, SMASH_MANIFEST, SMASH_REMOTE_ROOT, SMASH_URL, terminal_logo
from .tabular import export_wide
from .menu_ui import actions, arrow_ui, navigate, render_plain
from .prompts import ask, choose, confirm, text
from .download_flow import download, folder, confirm_location
from .console import console_write
from .manifest_browser import browse
from .presentation import write_status
from .connectivity import probe_server
from .validation import validate_database
from .local_tools import export_menu, reports_menu, variables_menu
from .progress import DownloadProgress
from .updates import startup_updates


def secret_prompt(prompt):
    if not sys.stdin.isatty():
        raise NextcloudError("Password setup needs an interactive terminal; passwords are never read with echo enabled")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            return getpass.getpass(prompt)
    except getpass.GetPassWarning:
        raise NextcloudError("This terminal cannot hide password input; use an interactive console") from None


def banner(workspace, write=print, startup=False):
    write(terminal_logo())
    if startup:
        workspace.refresh_local()
        write("Checking server reachability (up to 3 seconds)...")
        workspace.server_status = probe_server()
    status(workspace, write)
    if startup and workspace.discovery_message:
        write(text(workspace.discovery_message))


def status(workspace, write=print):
    write_status(workspace, write)


def check_connection(workspace, write=print):
    write("Checking the SMASH databank connection...")
    workspace.connection_status = False
    result = workspace.client().check()
    if result["status"] != "PASS":
        raise NextcloudError("Connection check did not pass; manifest retrieval was not started")
    workspace.connection_status = True
    write("Connection: PASS (verified HTTPS WebDAV)")


def retrieve_manifest(workspace, path=None, write=print, connection_checked=False):
    remote = path or workspace.state["manifest_remote_path"]
    write("Retrieving and validating the manifest: /" + SMASH_REMOTE_ROOT + "/" + text(remote))
    try:
        with DownloadProgress(remote, write) as progress:
            manifest = workspace.retrieve_manifest(remote, progress=progress)
    except NextcloudError as exc:
        if exc.status_code != 404:
            raise
        # A missing file is distinct from an inaccessible databank. Confirm the
        # folder first if this action did not already perform a connection check.
        if not connection_checked:
            check_connection(workspace, write)
        write("Manifest: NOT AVAILABLE (HTTP 404) at /" + SMASH_REMOTE_ROOT + "/" + text(remote))
        write("The databank connection works. This manifest file is missing or is not visible to your account.")
        write("The databank administrator needs to publish /databank/manifest.json and grant your account access.")
        try:
            workspace.manifest()
        except (OSError, ValueError):
            write("Manifest-based downloads remain unavailable. Specific-file downloads and local database tools still work.")
        else:
            write("Your previously loaded manifest is still available and has not been replaced.")
        return None
    write("Manifest ready: " + text(manifest["release"]) + " | " + str(len(manifest["files"])) + " files")
    if workspace.manifest_copy_notice:
        write(workspace.manifest_copy_notice)
    elif workspace.state["download_root"]:
        write("Manifest saved: " + text(Path(workspace.state["download_root"]) / "manifest.json"))
    return manifest


def setup(workspace, read=input, password_read=None, write=print, plain=False):
    if password_read is None:
        password_read = (lambda prompt: ask(prompt, read=read, write=write, plain=plain, password=True)) if arrow_ui(plain, read, write) else secret_prompt
    known = env_credentials(workspace.env_file)
    profile = workspace.state["profile"]
    current_user = profile.get("username") or known.get("NEXTCLOUD_USERNAME", "")
    username = ask("Username", current_user, read, write, plain).strip()
    previous = workspace.session.password if workspace.session and workspace.session.username == username else known.get("NEXTCLOUD_PASSWORD") if known.get("NEXTCLOUD_USERNAME") == username else None
    if not previous and profile.get("credential_storage") == "vault" and profile.get("username") == username:
        try:
            previous = load_vault(username)
        except NextcloudError:
            pass
    password = password_read("App password" + (" (Enter to keep current)" if previous else "") + ": ") or previous
    config = NextcloudConfig(SMASH_URL, username, password or "", SMASH_REMOTE_ROOT, profile.get("webdav_url") or known.get("NEXTCLOUD_WEBDAV_URL", ""))
    try:
        native_vault()
        default = "1"
    except NextcloudError:
        default = "2"
        write('OS vault not available here. Install ".[secure]" for native secure storage.')
    if arrow_ui(plain, read, write):
        storage = choose(["1", "2", "3"], lambda item: {"1": "OS credential vault (recommended)", "2": "This session only", "3": ".env (plaintext)"}[item], read, write, plain,
                         disabled=lambda item: "No native vault available" if item == "1" and default == "2" else "", message="How should this computer remember your login?")
    else:
        write("Save login: 1) OS credential vault (recommended)  2) This session only  3) .env (plaintext)")
        storage = read("Choice [" + default + "]: ").strip() or default
    if storage not in ("1", "2", "3"):
        raise NextcloudError("Choose 1, 2 or 3; no credentials were saved")
    if storage == "1":
        save_vault(username, config.password)
        mode = "vault"
        write("App password saved in the operating system credential vault.")
        if known.get("NEXTCLOUD_PASSWORD"):
            write("Your existing .env is unchanged. Remove its NEXTCLOUD_PASSWORD entry when you no longer need that plaintext copy.")
    elif storage == "3":
        save_env(workspace.env_file, username, config.password)
        mode = "env"
        write("Login saved in the local .env file (plaintext, excluded from Git).")
    else:
        mode = "session"
        write("Login will be kept only for this menu session.")
    workspace.session = config
    workspace.connection_status = None
    workspace.state["profile"] = {"username": username, "credential_storage": mode, "webdav_url": config.webdav_url}
    workspace.save()
    write("Server and databank folder are fixed to the SMASH service.")
    write("The app will check login/access and offer to check for data updates.")


def run_menu(workspace, initial_setup=False, read=input, password_read=None, write=print, plain=False, navigator=None):
    if write is print:
        write = console_write
    try:
        banner(workspace, write, startup=True)
        if initial_setup:
            setup(workspace, read, password_read, write, plain)
        startup_updates(workspace, read, write, plain)
        first = True
        while True:
            if not first:
                status(workspace, write)
            first = False
            items = actions(workspace)
            try:
                if navigator is not None:
                    choice = navigator(items)
                elif arrow_ui(plain, read, write):
                    choice = navigate(items)
                else:
                    def plain_select(message, entries):
                        entry = choose(entries, lambda item: item[1], read, write, plain=True, disabled=lambda item: item[2], message=message)
                        return entry[0] if entry else None if message == "SMASH-HCM Databank Menu" else "back"
                    choice = navigate(items, plain_select)
            except ValueError as exc:
                write("Could not select that option: " + text(exc))
                continue
            if choice in ("0", "q", "quit", "exit"):
                return 0
            try:
                selected = next((item for item in items if item.key == choice), None)
                if selected is not None and not selected.enabled:
                    write("Unavailable: " + selected.reason)
                    continue
                if choice == "1":
                    setup(workspace, read, password_read, write, plain)
                    startup_updates(workspace, read, write, plain)
                elif choice == "2":
                    check_connection(workspace, write)
                elif choice == "3":
                    retrieve_manifest(workspace, SMASH_MANIFEST, write)
                elif choice == "21":
                    startup_updates(workspace, read, write, plain)
                elif choice == "4":
                    write("Checking local file sizes and SHA-256 hashes...")
                    rows = workspace.verify_local()
                    if not rows:
                        write("No downloaded files or local database are registered yet.")
                    for row in rows:
                        write(text(row["status"]) + " | " + text(row["path"]) + " | " + text(row.get("detail", "")) + " | reference: " + text(row["reference"]))
                elif choice in ("5", "6", "13"):
                    download(workspace, {"5": "database", "6": "curated", "13": "tables"}[choice], read, write, plain)
                elif choice == "16":
                    browse(workspace, read, write, plain)
                elif choice == "7":
                    path = read("File path relative to databank (e.g. README.md): ").strip()
                    if confirm_location(workspace, read, write, plain, message="Download this file to:") is None:
                        continue
                    write("Downloading " + text(path) + "...")
                    manifest = workspace.manifest() if workspace.state["manifest_path"] else None
                    matches = [item for item in manifest["files"] if item["path"] == path] if manifest else []
                    with DownloadProgress(path, write) as progress:
                        result = workspace.download_entry(matches[0], progress) if matches else workspace.download_file(path, progress)
                    write("Downloaded/available: " + text(result["local_path"]))
                    if not matches:
                        write("Receipt checksum recorded; no independent manifest hash was supplied.")
                elif choice == "8":
                    workspace.register_database(ask("Local OMOP database path", read=read, write=write, plain=plain, path=True).strip().strip('"'))
                    write("Local OMOP database selected.")
                elif choice == "9":
                    export_menu(workspace, read, write, plain)
                elif choice == "19":
                    reports_menu(workspace, read, write, plain)
                elif choice == "20":
                    variables_menu(workspace, read, write, plain)
                elif choice == "10":
                    manifest = workspace.use_manifest(ask("Local manifest JSON path", read=read, write=write, plain=plain, path=True).strip().strip('"'))
                    write("Manifest ready: " + text(manifest["release"]) + " | " + str(len(manifest["files"])) + " files")
                elif choice == "14":
                    folder(workspace, read, write, plain)
                elif choice == "15":
                    check_connection(workspace, write)
                    if retrieve_manifest(workspace, SMASH_MANIFEST, write=write, connection_checked=True) is not None:
                        write("Next: Choose Download data to select the published files you need.")
                elif choice == "18":
                    existing = ask("Existing folder to verify against manifest", read=read, write=write, plain=plain, path=True).strip().strip('"')
                    if existing:
                        for row in workspace.verify_folder(existing):
                            write(text(row["status"]) + " | " + text(row["path"]))
                elif choice == "11":
                    write("Data Access Request: " + DATA_ACCESS_URL)
                    try:
                        opened = webbrowser.open(DATA_ACCESS_URL, new=2)
                    except (OSError, webbrowser.Error):
                        opened = False
                    if not opened:
                        write("Open this link in your browser to complete the access request.")
                elif choice == "12":
                    write("Checking SQLite integrity, person links and database capabilities...")
                    with OmopDatabase(workspace.state["active_db"]) as database:
                        result = validate_database(database)
                    write("Database validation: " + result["status"])
                    for check in result["checks"]:
                        write(text(check["status"]) + " | " + text(check["check"]))
                    write("SHA-256: " + result["database_sha256"])
                    write("Expected hash comparison needs a trusted manifest or validate --sha256; technical checks do not establish clinical completeness.")
                else:
                    write("Choose a listed option, or 0 to exit.")
            except (ValueError, OSError, KeyError, sqlite3.Error) as exc:
                write("Could not complete that option: " + text(exc))
    except (EOFError, KeyboardInterrupt):
        write("\nSMASH menu closed.")
        return 0
