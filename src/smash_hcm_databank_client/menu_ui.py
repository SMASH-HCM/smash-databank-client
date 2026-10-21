"""Availability and optional arrow-key presentation, with no network side effects."""
from dataclasses import dataclass
import os
from pathlib import Path
import sys

from .credentials import env_credentials
from .manifest import artifact_type


@dataclass(frozen=True)
class Action:
    key: str
    label: str
    group: str
    reason: str = ""

    @property
    def enabled(self):
        return not self.reason


def actions(workspace):
    """Inspect local prerequisites only; never retrieve a vault secret or log in."""
    profile = workspace.state["profile"]
    login = workspace.session is not None or (profile.get("credential_storage") == "vault" and bool(profile.get("username")))
    if not login and profile.get("credential_storage") != "session":
        try:
            env = env_credentials(workspace.env_file)
            login = bool(env.get("NEXTCLOUD_USERNAME") and env.get("NEXTCLOUD_PASSWORD"))
        except (OSError, ValueError):
            pass
    manifest, manifest_reason = None, "Retrieve or load a manifest first"
    if workspace.state["manifest_path"]:
        try:
            manifest = workspace.manifest()
            manifest_reason = ""
        except (OSError, ValueError):
            manifest_reason = "Retrieve or load a valid manifest first"
    login_reason = "" if login else "Set up a login first"
    database = workspace.database_available()
    artifact_reason = "" if database else "Download or select a local database first"
    db_reason = "PostgreSQL dump available; restore into PostgreSQL and use the optional PostgreSQL analysis workflow" if database and workspace.database_is_dump() else artifact_reason
    download_reason = manifest_reason or login_reason
    def available(category, reason):
        return download_reason or ("" if any(artifact_type(item) == category and (category == "database" or item["cohorts"]) for item in manifest["files"]) else reason)
    return [
        Action("1", "Setup / Change User Login", "Setup"),
        Action("2", "Check Databank Connection", "Setup", login_reason),
        Action("3", "Retrieve manifest", "Setup", login_reason),
        Action("14", "Select Download location", "Setup"),
        Action("21", "Check for data updates", "Setup", login_reason),
        Action("5", "Download OMOP db", "Download", available("database", "Manifest has no database entries")),
        Action("13", "Download train / test CSVs", "Download", available("tables", "Manifest has no published CSV datasets")),
        Action("6", "Download cohort ZIP files (MRI / Echo / ECG)", "Download", available("curated", "Manifest has no published cohort data bundles")),
        Action("16", "Download specific file(s) / folder", "Download", download_reason or ("" if manifest["files"] else "Manifest has no files")),
        Action("9", "Export tabular / event datasets", "Local OMOP", db_reason),
        Action("19", "View / save summary reports", "Local OMOP", db_reason),
        Action("20", "Create / reuse variable sets", "Local OMOP", db_reason),
        Action("4", "Validate downloaded files", "Validate", "" if workspace.state["downloads"] else "Download some files first"),
        Action("12", "Validate local OMOP database", "Validate", artifact_reason),
        Action("18", "Validate an existing folder against manifest", "Validate", manifest_reason),
        Action("10", "Load / validate a local manifest", "Validate"),
        Action("8", "Select a local OMOP database", "Validate"),
        Action("11", "Data Access Request (open form)", ""),
        Action("0", "Exit", ""),
    ]


def arrow_ui(plain=False, read=input, write=print):
    from .console import is_console_writer
    if plain or read is not input or not is_console_writer(write) or not sys.stdin.isatty() or not sys.stdout.isatty():
        return False
    # Windows uses its console API, independently of the POSIX TERM hint.
    if sys.platform != "win32" and os.environ.get("TERM") == "dumb":
        return False
    try:
        import questionary
    except ImportError:
        return False
    return True


def style():
    import questionary
    return questionary.Style([
        ("qmark", "fg:#00b8d9 bold"),
        ("question", "bold"),
        ("pointer", "fg:#00d4aa bold"),
        ("highlighted", "fg:#00d4aa bold"),
        ("text", "fg:#50c8e8"),
        ("disabled", "fg:#858585 italic"),
        ("answer", "fg:#00d4aa bold"),
    ])


def console_style():
    # Windows console support does not depend on a Unix TERM setting. Preserve
    # explicit user color preferences while avoiding an inherited monochrome hint.
    if sys.platform == "win32" and os.environ.get("TERM") == "dumb" and not os.environ.get("NO_COLOR") and not os.environ.get("PROMPT_TOOLKIT_COLOR_DEPTH"):
        from prompt_toolkit.output import ColorDepth
        return {"color_depth": ColorDepth.DEPTH_8_BIT}
    return {}


def select(message, entries):
    """entries are (value, sanitized title, disabled reason). None means cancel."""
    import questionary
    choices = [questionary.Choice(title, value=value, disabled=reason or None) for value, title, reason in entries]
    return questionary.select(message, choices=choices, style=style(), pointer=">", instruction="(Up/Down to move, Enter to select, Ctrl+C to exit)", **console_style()).ask()


def checkbox(message, entries):
    import questionary
    choices = [questionary.Choice(entry[1], value=entry[0], disabled=(entry[2] if len(entry) > 2 else "") or None) for entry in entries]
    return questionary.checkbox(message, choices=choices, style=style(), pointer=">", instruction="(Space to tick items; Enter to continue; Ctrl+C to cancel)", **console_style()).ask()


def confirm(message, default=False):
    import questionary
    return questionary.confirm(message, default=default, style=style(), **console_style()).ask()


def ask_text(message, default="", path=False, password=False):
    import questionary
    prompt = questionary.password if password else questionary.path if path else questionary.text
    return prompt(message, default=default, style=style(), **console_style()).ask()


def navigate(items, selector=None):
    selector = selector or select
    groups = list(dict.fromkeys(item.group for item in items if item.group))
    while True:
        entries = []
        for group in groups:
            children = [item for item in items if item.group == group]
            enabled = sum(item.enabled for item in children)
            entries.append(("group:" + group, str(len(entries) + 1) + ". > " + group, "" if enabled else children[0].reason))
        entries += [("11", str(len(groups) + 1) + ". > Data Access Request", ""), ("0", str(len(groups) + 2) + ". > Exit", "")]
        result = selector("SMASH-HCM Databank Menu", entries)
        if result is None:
            return "0"
        if not result.startswith("group:"):
            return result
        group = result[len("group:"):]
        children = [(item.key, item.label, item.reason) for item in items if item.group == group]
        result = selector(group, children + [("back", "< Back", "")])
        if result is None:
            return "0"
        if result != "back":
            return result


def render_plain(items, write=print, color=False):
    group = None
    for item in items:
        if item.group and item.group != group:
            group = item.group
            write(group + ":")
        status = "AVAILABLE" if item.enabled else "UNAVAILABLE: " + item.reason
        line = item.key + ") " + item.label + " [" + status + "]"
        if color:
            line = ("\033[1;36m" if item.enabled else "\033[90m") + line + "\033[0m"
        write(line)
