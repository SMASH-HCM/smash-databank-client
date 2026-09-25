"""Export one age-indexed Echo exam per row using 19 shared curated fields.

This is a source-curated harmonized view for collaborator analysis. It is not
yet a claim that Echo provenance is recoverable from the seven-column OMOP
event export. Patient-level output belongs in private_data/.
"""

import argparse
import csv
from collections import Counter
from pathlib import Path


def read(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        yield from csv.DictReader(handle)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export-dir", type=Path, required=True)
    parser.add_argument("--florence-echo", type=Path, required=True)
    parser.add_argument("--rennes-clinical", type=Path, required=True)
    parser.add_argument("--rennes-endpoints", type=Path, required=True)
    parser.add_argument("--rennes-harmonized", type=Path, required=True)
    args = parser.parse_args()

    manifest = {r["person_source_value"]: r for r in read(args.export_dir / "patient_manifest.csv")}
    clinical = list(read(args.rennes_clinical))
    keys = ("Date_inclusion_TTE_baseline", "Lastfollow-up_ordeath_date", "Age_at_inclusion", "Gender_man0_woman_1")
    fingerprint = lambda row: tuple(row[key] for key in keys)
    clinical_by_fingerprint = {fingerprint(r): r for r in clinical}
    endpoint_to_source = {}
    for row in read(args.rennes_endpoints):
        source = clinical_by_fingerprint[fingerprint(row)]["Patient_ID CHU RENNES"]
        endpoint_to_source[row["Patient_ID CHU RENNES"]] = source
    if len(endpoint_to_source) != 201:
        raise ValueError("Rennes source linkage is incomplete")

    harmonized = list(read(args.rennes_harmonized))
    echo_columns = [name for name in harmonized[0] if name.startswith("Ech_")]
    florence_rows = list(read(args.florence_echo))
    if not set(echo_columns).issubset(florence_rows[0]):
        raise ValueError("Echo field names do not match across sites")
    columns = ["person_id", "site", "split", "echo_age_years", "echo_source", "available_feature_count"] + echo_columns
    counts = Counter()
    output = args.export_dir / "echo_tabular_exams.csv"
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in florence_rows:
            person = manifest.get(row["HCM_Echo_PID"])
            age = row["HCM_Echo_Patient_Age"]
            if not person or person["site"] != "FLORENCE" or not age:
                counts["Florence_excluded_missing_link_or_age"] += 1
                continue
            features = {field: row[field] for field in echo_columns}
            writer.writerow({"person_id": person["person_id"], "site": "FLORENCE", "split": person["split"],
                             "echo_age_years": age, "echo_source": "HCM_Echo",
                             "available_feature_count": sum(bool(value) for value in features.values()), **features})
            counts["Florence_exams"] += 1
        for row in harmonized:
            source = endpoint_to_source[row["Patient_ID CHU RENNES"]]
            person = manifest[source]
            age = person["baseline_age_years"]
            if not age:
                counts["Rennes_excluded_missing_age"] += 1
                continue
            features = {field: row[field] for field in echo_columns}
            writer.writerow({"person_id": person["person_id"], "site": "RENNES", "split": person["split"],
                             "echo_age_years": age, "echo_source": "renne_harmonised",
                             "available_feature_count": sum(bool(value) for value in features.values()), **features})
            counts["Rennes_exams"] += 1
    print(dict(counts))
    print(f"Shared Echo columns: {len(echo_columns)}")
    print(output)


if __name__ == "__main__":
    main()
