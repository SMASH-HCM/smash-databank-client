"""Questionary prompts and equivalent numbered prompts for plain terminals."""
import re

from . import menu_ui
from .nextcloud import NextcloudError


def text(value):
    return re.sub(r"[\x00-\x1f\x7f]", "", str(value))[:240]


def ask(message, default="", read=input, write=print, plain=False, path=False, password=False):
    if menu_ui.arrow_ui(plain, read, write):
        result = menu_ui.ask_text(message, default, path=path, password=password)
        if result is None:
            raise KeyboardInterrupt()
        return result
    return read(message + (" [" + text(default) + "]" if default else "") + ": ").strip() or default


def confirm(message, read=input, write=print, plain=False, default=False):
    if menu_ui.arrow_ui(plain, read, write):
        return menu_ui.confirm(message, default) is True
    answer = read(message + (" [Y/n]: " if default else " [y/N]: ")).strip().casefold()
    return default if not answer else answer in ("y", "yes")


def location_choice(message, read=input, write=print, plain=False):
    """One confirmation with a change-path escape; Yes is the selected default."""
    if menu_ui.arrow_ui(plain, read, write):
        result = menu_ui.select(message, [("yes", "Yes", ""), ("no", "No", ""), ("change", "Change location", "")])
        if result is None:
            raise KeyboardInterrupt()
        return result
    answer = read(message + " [Y/n/change location]: ").strip().casefold()
    if answer in ("", "y", "yes", "1"):
        return "yes"
    if answer in ("n", "no", "0", "2"):
        return "no"
    if answer in ("c", "change", "change location", "3"):
        return "change"
    raise NextcloudError("Choose Yes, No or Change location")


def choose(entries, label, read=input, write=print, plain=False, disabled=None, message="Choose an option"):
    if not entries:
        raise NextcloudError("No matching entries are available")
    disabled = disabled or (lambda entry: "")
    if menu_ui.arrow_ui(plain, read, write):
        selected = menu_ui.select(message, [(str(i), text(label(entry)), disabled(entry)) for i, entry in enumerate(entries)] + [("cancel", "< Cancel", "")])
        return None if selected in (None, "cancel") else entries[int(selected)]
    write(message)
    for number, entry in enumerate(entries, 1):
        reason = disabled(entry)
        write(str(number) + ") " + text(label(entry)) + (" [UNAVAILABLE: " + reason + "]" if reason else ""))
    value = read("Choose a number (0 cancels): ").strip()
    if value in ("", "0"):
        return None
    if not value.isdigit() or not 1 <= int(value) <= len(entries):
        raise NextcloudError("Choose one of the listed numbers")
    chosen = entries[int(value) - 1]
    if disabled(chosen):
        raise NextcloudError(disabled(chosen))
    return chosen


def choose_many(entries, label, read=input, write=print, plain=False, message="Select cohorts", disabled=None):
    if not entries:
        raise NextcloudError("No matching items are published in this manifest")
    disabled = disabled or (lambda entry: "")
    if menu_ui.arrow_ui(plain, read, write):
        selected = menu_ui.checkbox(message, [(str(i), text(label(entry)), disabled(entry)) for i, entry in enumerate(entries)])
        return [] if selected is None else [entries[int(index)] for index in selected]
    write(message)
    for number, entry in enumerate(entries, 1):
        reason = disabled(entry)
        write(str(number) + ") " + text(label(entry)) + (" [UNAVAILABLE: " + reason + "]" if reason else ""))
    value = read("Numbers separated by commas (all selects all; 0 cancels): ").strip()
    if value in ("", "0"):
        return []
    if value.casefold() == "all":
        return [entry for entry in entries if not disabled(entry)]
    parts = [part.strip() for part in value.split(",")]
    if any(not part.isdigit() or not 1 <= int(part) <= len(entries) for part in parts):
        raise NextcloudError("Choose listed item numbers separated by commas")
    selected = [entries[number - 1] for number in dict.fromkeys(map(int, parts))]
    for entry in selected:
        if disabled(entry):
            raise NextcloudError(disabled(entry))
    return selected
