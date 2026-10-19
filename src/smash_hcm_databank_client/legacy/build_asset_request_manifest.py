"""Create a patient-linked request manifest for external image/signal assets.

The primary input is smash_cdm.image_occurrence (or its ETL load CSV).
An optional extra CSV can add ECG PDFs or NIfTI files with columns
person_id,relative_path,asset_kind[,modality]. No files are downloaded.
"""

import argparse
import csv
from collections import Counter
from pathlib import Path, PurePosixPath


def rows(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        yield from csv.DictReader(handle)


def safe_relative(path):
    clean = path.replace("\\", "/").strip()
    relative = PurePosixPath(clean)
    if not clean or relative.is_absolute() or ".." in relative.parts or ":" in relative.parts[0]:
        raise ValueError("Asset path must be a relative path under the data root")
    return relative.as_posix()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--patient-manifest", type=Path, required=True)
    parser.add_argument("--image-occurrences", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--extra-assets", type=Path)
    parser.add_argument("--site", action="append")
    parser.add_argument("--split", action="append")
    args = parser.parse_args()

    people = {r["person_id"]: r for r in rows(args.patient_manifest)}
    if not args.data_root.is_dir():
        parser.error("--data-root must exist")
    fields = ["person_id", "site", "split", "asset_kind", "modality",
              "image_occurrence_id", "study_uid", "series_uid",
              "relative_path", "wadors_uri", "local_exists", "request_needed"]
    counts = Counter()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()

        def write_asset(pid, relative_path, asset_kind, modality="", image_id="", study_uid="", series_uid="", wadors_uri=""):
            person = people.get(pid)
            if not person:
                counts["unmatched_person"] += 1
                return
            if args.site and person["site"] not in args.site:
                return
            if args.split and person["split"] not in args.split:
                return
            relative = safe_relative(relative_path)
            exists = (args.data_root / Path(relative)).exists()
            writer.writerow({"person_id": pid, "site": person["site"], "split": person["split"],
                             "asset_kind": asset_kind, "modality": modality,
                             "image_occurrence_id": image_id, "study_uid": study_uid,
                             "series_uid": series_uid, "relative_path": relative,
                             "wadors_uri": wadors_uri, "local_exists": int(exists),
                             "request_needed": int(not exists)})
            counts["assets"] += 1
            counts["missing_local"] += int(not exists)
            counts[f"{person['site']}_assets"] += 1

        for row in rows(args.image_occurrences):
            relative = safe_relative(row["local_path"])
            kind = "DICOM_FILE" if PurePosixPath(relative).suffix.lower() == ".dcm" else "DICOM_SERIES_DIRECTORY"
            write_asset(row["person_id"], relative, kind, row["modality"],
                        row["image_occurrence_id"], row["image_study_uid"],
                        row["image_series_uid"], row["wadors_uri"])
        if args.extra_assets:
            for row in rows(args.extra_assets):
                write_asset(row["person_id"], row["relative_path"], row["asset_kind"], row.get("modality", ""))
    print(dict(counts))
    print(args.output)


if __name__ == "__main__":
    main()
