"""Small rsync-style progress display; JSON command output stays on stdout."""
import sys
import re
import time


def size_label(value):
    value = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.1f} {unit}"
        value /= 1024


class DownloadProgress:
    def __init__(self, label, write=print, stream=None, clock=time.monotonic):
        self.label = re.sub(r"[\x00-\x1f\x7f]", "", str(label))[:100]
        self.stream = stream or sys.stderr
        self.write = write
        self.clock = clock
        self.start = clock()
        self.last = None
        self.final = False
        self.last_width = 0

    def __enter__(self):
        return self

    def __call__(self, count, total, phase="transfer"):
        now = self.clock()
        terminal = phase in ("complete", "cached")
        if phase == "cached":
            self._emit(self.label + " | " + size_label(count) + " cached; size and SHA-256 verified", True)
            self.final = True
            return
        if not terminal and phase != "validating" and self.last is not None and now - self.last < 0.2:
            return
        self.last = now
        elapsed = max(now - self.start, 0.001)
        speed = count / elapsed
        fraction = min(count / total, 1) if total else 0
        filled = int(20 * fraction)
        bar = "[" + "#" * filled + "-" * (20 - filled) + "]"
        percent = f"{100 * fraction:5.1f}%" if total else "  ?  %"
        amount = size_label(count) + ("/" + size_label(total) if total is not None else " (size unknown)")
        eta = f" ETA {max(0, (total - count) / speed):.0f}s" if total and speed else ""
        line = f"{self.label} {bar} {percent} {amount} {size_label(speed)}/s{eta} {phase}"
        self._emit(line, terminal)
        self.final = terminal

    def _emit(self, line, final):
        if self.write is print:
            tty = self.stream.isatty()
            if tty:
                line = line + " " * max(0, self.last_width - len(line))
                self.last_width = len(line)
            self.stream.write(("\r" if tty else "") + line + ("\n" if final or not tty else ""))
            self.stream.flush()
        else:
            self.write(line)

    def __exit__(self, kind, value, traceback):
        if kind:
            self._emit(self.label + " | FAILED / cancelled; check the error before retrying", True)
        elif not self.final:
            self._emit(self.label + " | complete", True)
