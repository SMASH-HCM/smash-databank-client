"""Compact, aligned databank status panel for ordinary terminal widths."""
from pathlib import Path
import os
import re
import shutil
import sys
import textwrap

from .prompts import text
from .settings import SMASH_DATABANK_URL
from .console import is_console_writer


def status_panel(workspace, width=None):
    width = max(32, min(width or shutil.get_terminal_size((80, 24)).columns, 100))
    database = "<unavailable>"
    if workspace.database_available():
        info = workspace.database_info()
        if not info.startswith("Selected database is unavailable"):
            version, _, filename = info.partition(" | ")
            database = version if version != "version not recorded" else filename + " (version not recorded)"
    try:
        catalogue = workspace.manifest()
        manifest = "schema " + catalogue["schema_version"] + " | " + catalogue["release"]
    except (OSError, ValueError):
        manifest = "<unavailable>"
    server = getattr(workspace, "server_status", None)
    connection = workspace.connection_status
    reachable = bool(server and server["available"]) or connection is True
    detail = server["detail"].replace("; login not checked", "") if server else "HTTPS not checked"
    if connection is True and not (server and server["available"]):
        detail = "HTTPS reachable"
    login = "Verified" if connection is True else "Login/access failed" if connection is False else "Not checked"
    directory = str(workspace.suggested_download_root())
    try:
        directory_ok = bool(directory and Path(directory).is_dir())
    except OSError:
        directory_ok = False
    rows = [
        ("SMASH-HCM Databank:", SMASH_DATABANK_URL + " | " + detail, reachable),
        ("Databank login:", login, connection is True),
        ("Download location:", directory + (" (default)" if not workspace.state["download_root"] else ""), directory_ok),
        ("SMASH-HCM Manifest:", manifest, manifest != "<unavailable>"),
        ("SMASH-HCM OMOP database:", database, database != "<unavailable>"),
    ]
    inner = width - 4
    label_width = min(max(len(label) for label, _, _ in rows) + 2, inner - 10)
    border = "|" + "-" * (width - 2) + "|"
    rendered = [border]
    for label, value, available in rows:
        parts = textwrap.wrap(text(value), width=inner - label_width - 5, break_on_hyphens=False) or [""]
        for number, part in enumerate(parts):
            indicator = ("[OK] " if available else "[NO] ") if number == 0 else "     "
            content = (label if number == 0 else "").ljust(label_width) + indicator + part
            rendered.append("| " + content.ljust(inner) + " |")
    rendered.append(border)
    return "\n".join(rendered)


def write_status(workspace, write=print):
    """Use native console colors without counting escape sequences as columns."""
    panel = status_panel(workspace)
    if not is_console_writer(write) or not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
        write(panel)
        return
    try:
        from prompt_toolkit import print_formatted_text
        from prompt_toolkit.formatted_text import FormattedText
    except ImportError:
        write(panel)
        return
    from .menu_ui import console_style
    fragments = [("fg:ansigreen bold" if part == "[OK]" else "fg:ansired bold" if part == "[NO]" else "", part)
                 for part in re.split(r"(\[OK\]|\[NO\])", panel)]
    print_formatted_text(FormattedText(fragments), **console_style())
