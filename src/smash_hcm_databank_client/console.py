"""Terminal-only outcome colors; redirected output and custom writers stay plain."""
import os
import re
import sys

STYLES = {"failure": "fg:ansired bold", "success": "fg:#006400 bold", "cancel": "fg:#ff8c00 bold", "info": ""}


def is_console_writer(write):
    return write is print or write is console_write


def message_level(message):
    message = str(message).strip()
    if re.match(r"(?:CANCELLED|CANCELED|Download cancelled|No cohorts selected; download cancelled|Download location was not changed|SMASH menu closed)\b", message, re.I):
        return "cancel"
    summary = re.match(r"Finished: (\d+) verified, (\d+) failed", message)
    if summary:
        return "failure" if int(summary[2]) else "success"
    if re.search(r"\bFAIL(?:ED|URE)?\b", message, re.I) or message.startswith(("Could not", "Error:", "Update incomplete:")):
        return "failure"
    if re.match(r"(?:PASS|SUCCESS|CACHED|DOWNLOADED)\b", message) or message.startswith((
        "Connection: PASS", "Login and databank access: PASS", "Database validation: PASS", "Manifest ready:", "Manifest saved:",
        "Manifest: FIRST", "Manifest: UPDATED", "Manifest: UNCHANGED", "Update complete:", "Downloaded/available:",
        "Local OMOP database selected.", "Variable set saved:", "Report saved:", "Dataset saved:", "Export complete:",
    )):
        return "success"
    return "info"


def write_message(message, write=print, level=None, stream=None, end="\n"):
    if not is_console_writer(write):
        write(message)
        return
    stream = stream or sys.stdout
    style = STYLES[level or message_level(message)]
    if style and stream.isatty() and not os.environ.get("NO_COLOR"):
        try:
            from prompt_toolkit import print_formatted_text
            from prompt_toolkit.formatted_text import FormattedText
            from .menu_ui import console_style
        except ImportError:
            pass
        else:
            print_formatted_text(FormattedText([(style, str(message))]), file=stream, end=end, **console_style())
            stream.flush()
            return
    print(message, file=stream, end=end, flush=True)


def console_write(message):
    write_message(message)
