"""Aligned, control-character-safe file sizes and publisher comments."""
from pathlib import PurePosixPath

from .prompts import text


def size_label(size):
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return (str(int(value)) if unit == "B" else f"{value:.1f}") + " " + unit
        value /= 1024


def table_labels(rows):
    """Align columns (size is second, comment last) before rendering prompts."""
    rows = [tuple(text(value) for value in row) for row in rows]
    if not rows:
        return []
    widths = [max(len(value) for value in column) for column in zip(*rows)]
    return [" | ".join(value if i == len(row) - 1 else value.rjust(widths[i]) if i == 1 else value.ljust(widths[i])
                      for i, value in enumerate(row)) for row in rows]


def file_labels(entries, basename=False):
    labels = table_labels([(PurePosixPath(item["path"]).name if basename else item["path"],
                            size_label(item["size_bytes"]), item.get("comment", "")) for item in entries])
    return {item["path"]: label for item, label in zip(entries, labels)}
