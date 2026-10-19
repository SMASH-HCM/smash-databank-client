"""Stage output bundles; never overwrite a completed bundle implicitly."""
import csv
import json
import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def bundle(destination):
    destination = Path(destination).expanduser().resolve()
    if destination.exists():
        raise FileExistsError("Output already exists; choose a new directory")
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".omop-exporter-", dir=str(destination.parent)))
    try:
        yield stage
        if destination.exists():
            raise FileExistsError("Output appeared during generation; refusing overwrite")
        os.rename(stage, destination)
    finally:
        if stage.exists():
            if stage.resolve().parent != destination.parent or not stage.name.startswith(".omop-exporter-"):
                raise ValueError("Unsafe staging cleanup path")
            shutil.rmtree(stage)


def write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def write_csv(path, fields, rows):
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
