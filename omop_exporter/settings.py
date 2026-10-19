"""Public SMASH defaults. Credentials are never part of these settings."""
from pathlib import Path
import shutil
import sys

SMASH_URL = "https://smash-hcm.ucd.ie"
SMASH_REMOTE_ROOT = "databank"
SMASH_DATABANK_URL = SMASH_URL + "/" + SMASH_REMOTE_ROOT
APP_TITLE = "SMASH-HCM DATABANK EXPORTER"
SMASH_MANIFEST = "manifest.json"
DATA_ACCESS_URL = "https://forms.gle/nNDDBbX8ah15dNcs8"
VAULT_SERVICE = "omop-exporter:nextcloud:smash-hcm.ucd.ie"

def terminal_logo():
    """Fit the supplied block artwork using quadrant characters on small terminals."""
    art = (Path(__file__).parent / "resources/smashhcm-logo.txt").read_text(encoding="utf-8-sig")
    terminal = shutil.get_terminal_size((80, 24))
    lines = [line.rstrip() for line in art.splitlines()]
    while max(map(len, lines)) > max(terminal.columns, 20) or len(lines) > max(terminal.lines - 8, 6):
        width = max(map(len, lines))
        padded = [line.ljust(width + width % 2) for line in lines]
        if len(padded) % 2:
            padded.append(" " * len(padded[0]))
        quadrants = " ▘▝▀▖▌▞▛▗▚▐▜▄▙▟█"
        reduced = []
        for y in range(0, len(padded), 2):
            row = []
            for x in range(0, len(padded[0]), 2):
                mask = sum(bit for bit, occupied in (
                    (1, padded[y][x] != " "), (2, padded[y][x+1] != " "),
                    (4, padded[y+1][x] != " "), (8, padded[y+1][x+1] != " ")) if occupied)
                row.append(quadrants[mask])
            reduced.append("".join(row).rstrip())
        lines = reduced
    rendered = "\n".join(lines)
    try:
        rendered.encode(sys.stdout.encoding or "utf-8")
    except UnicodeEncodeError:
        rendered = "\n".join("".join("#" if char != " " else " " for char in line) for line in lines)
    return rendered + "\n          " + APP_TITLE + "\n"
