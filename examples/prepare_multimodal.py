"""Tutorial helper: guarded ZIP extraction and reviewed ECG/tabular linkage.

No third-party dependencies. The asset index must be supplied/reviewed by the
data owner; this script does not infer identity or prediction availability.
"""
import argparse
import csv
from datetime import date
import json
import os
from pathlib import Path
import shutil
import stat
import zipfile


def extract(archive, destination, max_bytes):
    destination = Path(destination).expanduser().resolve()
    if destination.exists():
        raise FileExistsError("Choose a new extraction directory")
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    with zipfile.ZipFile(archive) as source:
        entries = source.infolist()
        if len(entries) > 100000 or sum(info.file_size for info in entries) > max_bytes:
            raise ValueError("Archive exceeds the configured uncompressed size/member limit")
        targets, seen = [], set()
        for info in entries:
            name = info.orig_filename.rstrip("/")
            parts = name.split("/")
            if (not name or "\\" in name or ":" in name or any(ord(c) < 32 for c in name)
                    or any(part in ("", ".", "..") or part.endswith((" ", ".")) for part in parts)
                    or stat.S_ISLNK(info.external_attr >> 16)):
                raise ValueError("Unsafe ZIP member path or symbolic link")
            target = destination.joinpath(*parts)
            if destination not in target.resolve().parents or name.casefold() in seen:
                raise ValueError("Duplicate or escaping ZIP member")
            seen.add(name.casefold())
            targets.append((info, target))
        destination.mkdir(parents=True, exist_ok=False)
        # A transfer/extraction error leaves an incomplete directory for review.
        # Retrying requires a new destination, never overwrites it.
        for info, target in targets:
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.open(info) as src, target.open("xb") as dst:
                    shutil.copyfileobj(src, dst)


def read_csv(path, required):
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("Missing required CSV fields: " + str(sorted(required)))
        return reader.fieldnames, list(reader)


def link(train, test, asset_index, asset_root, destination, lookback_days):
    if type(lookback_days) is not int or lookback_days <= 0:
        raise ValueError("Choose an explicit positive ECG lookback in days")
    fields, training = read_csv(train, {"person_id", "snapshot_date"})
    test_fields, testing = read_csv(test, {"person_id", "snapshot_date"})
    if fields != test_fields or {"ecg_paths", "ecg_count"} & set(fields):
        raise ValueError("Train/test columns must match and must not already contain ECG links")
    people = {}
    for split, rows in (("train", training), ("test", testing)):
        for row in rows:
            pid = row["person_id"]
            if not pid or pid in people:
                raise ValueError("Patient IDs must be unique and disjoint across train/test")
            people[pid] = date.fromisoformat(row["snapshot_date"])
    _, assets = read_csv(asset_index, {"person_id", "relative_path", "acquisition_date", "available_at_baseline"})
    root = Path(asset_root).expanduser().resolve(strict=True)
    linked, seen = {pid: [] for pid in people}, set()
    for asset in assets:
        pid = asset["person_id"]
        if pid not in people:
            continue
        eligible = asset["available_at_baseline"].strip().lower()
        if eligible not in ("true", "false"):
            raise ValueError("available_at_baseline must be explicitly true or false")
        if eligible == "false":
            continue
        elapsed = (people[pid] - date.fromisoformat(asset["acquisition_date"])).days
        if elapsed < 0 or elapsed > lookback_days:
            continue
        relative = Path(asset["relative_path"])
        if not asset["relative_path"] or relative.is_absolute():
            raise ValueError("Asset path must be relative to asset_root")
        path = (root / relative).resolve(strict=True)
        if root not in path.parents or not path.is_file() or path.suffix.lower() != ".npz":
            raise ValueError("ECG asset must be an existing NPZ file inside asset_root")
        # A shared file or repeated index row is ambiguous, even within one patient.
        identity = os.path.normcase(str(path))
        if identity in seen:
            raise ValueError("Duplicate/shared asset path in eligible linkage index")
        seen.add(identity)
        linked[pid].append(path.relative_to(root).as_posix())
    destination = Path(destination).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=False)
    summary = {"asset_root": str(root), "lookback_days": lookback_days,
               "policy": "Explicit reviewed availability; acquisition on/before baseline within inclusive window. All eligible ECGs retained; no missing patients dropped.", "splits": {}}
    for split, rows in (("train", training), ("test", testing)):
        with (destination / (split + ".csv")).open("x", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fields + ["ecg_count", "ecg_paths"])
            writer.writeheader()
            for row in rows:
                paths = sorted(linked[row["person_id"]])
                writer.writerow({**row, "ecg_count": len(paths), "ecg_paths": json.dumps(paths)})
        summary["splits"][split] = {"patients": len(rows), "patients_with_ecg": sum(bool(linked[r["person_id"]]) for r in rows)}
    (destination / "linkage_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    unzip = commands.add_parser("extract", help="Extract an already verified ZIP to a new directory")
    unzip.add_argument("archive", type=Path)
    unzip.add_argument("--out", type=Path, required=True)
    unzip.add_argument("--max-bytes", type=int, default=5 * 1024 ** 3)
    join = commands.add_parser("link", help="Link reviewed ECG assets to existing tabular train/test rows")
    for argument in ("train", "test", "asset-index", "asset-root", "out"):
        join.add_argument("--" + argument, type=Path, required=True)
    join.add_argument("--lookback-days", type=int, required=True)
    args = parser.parse_args()
    if args.command == "extract":
        extract(args.archive, args.out, args.max_bytes)
    else:
        print(json.dumps(link(args.train, args.test, args.asset_index, args.asset_root, args.out, args.lookback_days), indent=2))


if __name__ == "__main__":
    main()
