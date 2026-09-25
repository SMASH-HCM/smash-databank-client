"""Build a sparse patient-landmark-concept table from the local OMOP age stream.

Example:
  python scripts/export_omop_tabular.py --data-dir private_data/smash_v1_2 \
    --output private_data/smash_v1_2/omop_baseline_2y.csv \
    --site FLORENCE --domain measurement --lookback-years 2

The default landmark is each patient's age anchor. Supply --landmarks-csv with
person_id,landmark_age_years columns for rolling landmarks. This exports
features only; endpoint labels are maintained separately. Patient-level output
must be stored in an access-controlled, gitignored location.
"""

import argparse
import csv
from collections import defaultdict
from pathlib import Path

AGE_EPSILON = 1e-6


def rows(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        yield from csv.DictReader(handle)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--landmarks-csv", type=Path)
    parser.add_argument("--site", action="append", help="Repeat to select sites")
    parser.add_argument("--split", action="append", help="Repeat to select splits")
    parser.add_argument("--endpoint", action="append", help="Repeat to select endpoint-specific landmarks")
    parser.add_argument("--cohort-id", action="append", help="Repeat to select results.cohort IDs")
    parser.add_argument("--domain", action="append", help="Repeat to select OMOP domains")
    parser.add_argument("--concept-id", action="append", help="Repeat to select concepts")
    parser.add_argument("--input-source", action="append", help="Requires a provenance-enriched event export")
    parser.add_argument("--lookback-years", type=float, help="Only events within this many years before the landmark")
    parser.add_argument("--include-landmark-day", action="store_true", help="Requires same-day availability audit")
    args = parser.parse_args()
    if args.lookback_years is not None and args.lookback_years <= 0:
        parser.error("--lookback-years must be positive")
    if args.output.resolve() == (args.data_dir / "age_omop_events.csv").resolve():
        parser.error("Output must not overwrite the source event stream")

    people = {r["person_id"]: r for r in rows(args.data_dir / "patient_manifest.csv")}
    members = defaultdict(set)
    if args.cohort_id:
        for row in rows(args.data_dir / "cohort_membership.csv"):
            members[row["person_id"]].add(row["cohort_definition_id"])
    selected = {
        pid for pid, person in people.items()
        if (not args.site or person["site"] in args.site)
        and (not args.split or person["split"] in args.split)
        and (not args.cohort_id or members[pid].intersection(args.cohort_id))
    }

    landmarks = []
    if args.landmarks_csv:
        for row in rows(args.landmarks_csv):
            if row["person_id"] in selected and row["landmark_age_years"] and (not args.endpoint or row.get("endpoint") in args.endpoint):
                landmarks.append((row["person_id"], float(row["landmark_age_years"]),
                                  row.get("landmark_id") or f"{row['person_id']}:{len(landmarks)}",
                                  row.get("endpoint", "")))
    else:
        for pid in sorted(selected):
            age = people[pid]["baseline_age_years"]
            if age:
                landmarks.append((pid, float(age), f"{pid}:baseline", ""))

    events = defaultdict(list)
    stream_path = args.data_dir / "age_omop_events.csv"
    with stream_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if args.input_source and "input_source" not in reader.fieldnames:
            parser.error("The current age stream lacks input_source; re-export with source provenance before filtering by source")
        for row in reader:
            pid = row["person_id"]
            if pid not in selected:
                continue
            if args.domain and row["domain"] not in args.domain:
                continue
            if args.concept_id and row["concept_id"] not in args.concept_id:
                continue
            if args.input_source and row["input_source"] not in args.input_source:
                continue
            events[pid].append(row)
    for patient_events in events.values():
        patient_events.sort(key=lambda row: float(row["patient_age_at_event_years"]))

    fields = ["person_id", "site", "split", "landmark_id", "endpoint",
              "landmark_age_years", "lookback_years",
              "domain", "concept_id", "event_count", "latest_event_age_years",
              "years_since_latest", "latest_numeric_mean", "window_numeric_mean",
              "latest_value_as_concept_id", "unit_concept_id", "unit_conflict"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for pid, landmark, landmark_id, endpoint in landmarks:
            grouped = defaultdict(list)
            for event in events[pid]:
                age = float(event["patient_age_at_event_years"])
                if age > landmark + AGE_EPSILON or (not args.include_landmark_day and age >= landmark - AGE_EPSILON):
                    break
                if args.lookback_years is not None and age < landmark - args.lookback_years:
                    continue
                grouped[(event["domain"], event["concept_id"])].append(event)
            for (domain, concept_id), group in sorted(grouped.items()):
                latest_age = max(float(event["patient_age_at_event_years"]) for event in group)
                latest = [event for event in group if float(event["patient_age_at_event_years"]) == latest_age]
                units = {event["unit_concept_id"] for event in group if event["unit_concept_id"] not in ("", "0")}
                unit_conflict = len(units) > 1
                numeric = [float(event["value_as_number"]) for event in group if event["value_as_number"]]
                latest_numeric = [float(event["value_as_number"]) for event in latest if event["value_as_number"]]
                latest_categories = {event["value_as_concept_id"] for event in latest if event["value_as_concept_id"] not in ("", "0")}
                writer.writerow({
                    "person_id": pid, "site": people[pid]["site"], "split": people[pid]["split"],
                    "landmark_id": landmark_id, "endpoint": endpoint,
                    "landmark_age_years": f"{landmark:.4f}",
                    "lookback_years": args.lookback_years if args.lookback_years is not None else "all_prior",
                    "domain": domain, "concept_id": concept_id, "event_count": len(group),
                    "latest_event_age_years": f"{latest_age:.4f}",
                    "years_since_latest": f"{landmark - latest_age:.4f}",
                    "latest_numeric_mean": sum(latest_numeric) / len(latest_numeric) if latest_numeric and not unit_conflict else "",
                    "window_numeric_mean": sum(numeric) / len(numeric) if numeric and not unit_conflict else "",
                    "latest_value_as_concept_id": next(iter(latest_categories)) if len(latest_categories) == 1 else "",
                    "unit_concept_id": next(iter(units)) if len(units) == 1 else "",
                    "unit_conflict": int(unit_conflict),
                })
                written += 1
    print(f"Selected patients: {len(selected)}; landmarks: {len(landmarks)}; sparse feature rows: {written}")
    print(args.output)


if __name__ == "__main__":
    main()
