"""Build age-indexed SMASH study exports from ETL endpoint/censor tables.

The ETL ledger is authoritative for endpoint status and dates. Undated positives
and unascertained endpoints remain explicit exclusions; cohort flags are audited.
"""

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path


SPLITS = {
    "1100": ("FLORENCE", "FLORENCE-TEST"),
    "1101": ("FLORENCE", "FLORENCE-TRAIN"),
    "1102": ("RENNES", "RENNES-TRAIN"),
    "1103": ("RENNES", "RENNES-TEST"),
    "1104": ("TAMPERE", "TAMPERE-TRAIN"),
    "1105": ("TAMPERE", "TAMPERE-TEST"),
}
ENDPOINTS = {"OVERALL": "overall", "HF": "heart_failure",
             "VA": "ventricular_arrhythmia", "DEATH": "all_cause_death"}
COHORT_IDS = {"OVERALL": "1302", "HF": "1300", "VA": "1301", "DEATH": "1304"}
HORIZONS = (1, 2, 5)
YEAR_DAYS = 365.2425


def rows(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        yield from csv.DictReader(handle)


def parse_date(value):
    return date.fromisoformat(value[:10]) if value else None


def truth(value):
    return str(value).strip().lower() in {"t", "true", "1", "yes"}


def write_csv(path, records, fieldnames):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export-dir", type=Path, required=True)
    args = parser.parse_args()
    root = args.export_dir
    audit = Counter()
    people = {row["person_id"]: row for row in rows(root / "person.csv")}
    censor = {row["person_id"]: row for row in rows(root / "smash_endpoint_censor.csv")}
    membership = defaultdict(set)
    for row in rows(root / "cohort_membership.csv"):
        membership[row["person_id"]].add(row["cohort_definition_id"])
    if set(people) != set(censor):
        raise ValueError("person and smash_endpoint_censor person IDs differ")

    manifest = []
    for pid, person in sorted(people.items()):
        followup = censor[pid]
        assigned = set(SPLITS).intersection(membership[pid])
        if not assigned:
            audit[f"{followup['site']}_unassigned_split"] += 1
            continue
        if len(assigned) != 1:
            raise ValueError(f"Person {pid} must have exactly one study split")
        site, split = SPLITS[next(iter(assigned))]
        if site != followup["site"]:
            raise ValueError(f"Site mismatch for person {pid}")
        baseline = parse_date(followup["baseline_date"])
        end = parse_date(followup["censor_date"])
        age = followup["baseline_age"]
        valid = bool(baseline and end and end >= baseline and age)
        if site == "TAMPERE" and valid:
            raise ValueError("Tampere unexpectedly has modeled outcome follow-up")
        audit[f"split_{split}"] += 1
        audit[f"{site}_valid_followup"] += int(valid)
        if not valid:
            audit[f"{site}_missing_or_invalid_followup"] += 1
        manifest.append({
            "person_id": pid, "person_source_value": person["person_source_value"],
            "site": site, "split": split,
            "index_date": baseline.isoformat() if baseline else "",
            "censor_date": end.isoformat() if end else "",
            "baseline_age_years": age, "valid_followup": int(valid),
            "date_provenance": followup["birth_date_basis"],
            "endpoint_definition_version": followup["definition_version"],
            "baseline_source": followup["baseline_source"],
            "censor_source": followup["censor_source"],
            "gender_concept_id": person["gender_concept_id"],
            "race_concept_id": person["race_concept_id"],
            "ethnicity_concept_id": person["ethnicity_concept_id"],
        })
    manifest_by_pid = {row["person_id"]: row for row in manifest}
    write_csv(root / "patient_manifest.csv", manifest, list(manifest[0]))

    labels = []
    seen = set()
    for source in rows(root / "smash_endpoint_event.csv"):
        pid = source["person_id"]
        if pid not in manifest_by_pid:
            continue
        endpoint_name = source["endpoint"]
        if endpoint_name not in ENDPOINTS:
            raise ValueError(f"Unknown endpoint {endpoint_name}")
        endpoint = ENDPOINTS[endpoint_name]
        if (pid, endpoint) in seen:
            raise ValueError(f"Duplicate endpoint row for person {pid}, {endpoint}")
        seen.add((pid, endpoint))
        person = manifest_by_pid[pid]
        if source["site"] != person["site"]:
            raise ValueError(f"Endpoint site mismatch for person {pid}")
        if source["definition_version"] != person["endpoint_definition_version"]:
            raise ValueError(f"Endpoint version mismatch for person {pid}")
        status = source["status"]
        if status not in {"positive", "negative", "undated_positive", "not_ascertained"}:
            raise ValueError(f"Unexpected endpoint status {status}")
        baseline = parse_date(person["index_date"])
        end = parse_date(person["censor_date"])
        event = parse_date(source["event_date"])
        if status == "positive" and not event:
            raise ValueError("Positive endpoint is missing its ETL event date")
        if status in {"negative", "not_ascertained", "undated_positive"} and event:
            raise ValueError("Non-dated endpoint status unexpectedly has an event date")
        conflict = False
        if status in {"positive", "negative"}:
            conflict = (status == "positive") != (COHORT_IDS[endpoint_name] in membership[pid])
        audit[f"{person['site']}_{endpoint}_{status}"] += 1
        audit[f"{person['site']}_{endpoint}_cohort_conflict"] += int(conflict)
        if source["date_precision"]:
            audit[f"{person['site']}_{endpoint}_date_precision_{source['date_precision']}"] += 1
        if event and end and event > end:
            audit[f"{person['site']}_{endpoint}_event_after_censor"] += 1
        for horizon in HORIZONS:
            label = ""
            if status == "not_ascertained":
                reason = "not_ascertained"
            elif status == "undated_positive":
                reason = "positive_without_event_date"
            elif conflict:
                reason = "cohort_status_conflict"
            elif not baseline or not person["baseline_age_years"] or not end or end < baseline:
                reason = "missing_or_invalid_followup"
            elif event and (truth(source["prevalent_at_baseline"]) or event <= baseline):
                reason = "prevalent_event"
            elif event:
                label = int((event - baseline).days <= round(horizon * YEAR_DAYS))
                reason = "observed_event"
            elif (end - baseline).days >= round(horizon * YEAR_DAYS):
                label = 0
                reason = "observed_event_free"
            else:
                reason = "censored_before_horizon"
            labels.append({
                "person_id": pid, "site": person["site"], "split": person["split"],
                "endpoint": endpoint, "horizon_years": horizon,
                "label": label, "label_reason": reason,
                "index_date": baseline.isoformat() if baseline else "",
                "event_date": event.isoformat() if event else "",
                "censor_date": end.isoformat() if end else "",
                "event_after_recorded_followup": int(bool(event and end and event > end)),
                "cohort_status_conflict": int(conflict),
                "prevalent_at_baseline": int(truth(source["prevalent_at_baseline"])),
                "date_precision": source["date_precision"],
                "definition_version": source["definition_version"],
                "time_to_event_or_censor_days": ((event - baseline).days if event and baseline
                                                 else (end - baseline).days if end and baseline and status == "negative"
                                                 else ""),
            })
            audit[f"label_{endpoint}_{horizon}_{reason}"] += 1
    if len(seen) != len(manifest) * len(ENDPOINTS):
        raise ValueError("Endpoint ledger does not cover every patient and endpoint")
    write_csv(root / "horizon_labels.csv", labels, list(labels[0]))

    age_fields = ["person_id", "domain", "concept_id", "patient_age_at_event_years",
                  "years_from_anchor", "value_as_number", "value_as_concept_id", "unit_concept_id"]
    with (root / "age_omop_events.csv").open("w", newline="", encoding="utf-8") as age_handle, \
         (root / "preindex_omop_events.csv").open("w", newline="", encoding="utf-8") as pre_handle:
        age_writer = csv.DictWriter(age_handle, fieldnames=age_fields)
        pre_writer = None
        age_writer.writeheader()
        for event in rows(root / "omop_events.csv"):
            pid = event["person_id"]
            if pid not in manifest_by_pid:
                audit["events_unassigned_split"] += 1
                continue
            person = manifest_by_pid[pid]
            baseline = parse_date(person["index_date"])
            event_date = parse_date(event["event_date"])
            if pre_writer is None:
                pre_writer = csv.DictWriter(pre_handle, fieldnames=list(event))
                pre_writer.writeheader()
            if not baseline or not event_date or not person["baseline_age_years"]:
                audit["events_missing_anchor_or_date"] += 1
                continue
            offset = (event_date - baseline).days / YEAR_DAYS
            age = float(person["baseline_age_years"]) + offset
            if not 0 <= age <= 120:
                audit["events_implausible_age"] += 1
                continue
            age_writer.writerow({"person_id": pid, "domain": event["domain"],
                                 "concept_id": event["concept_id"],
                                 "patient_age_at_event_years": f"{age:.10f}",
                                 "years_from_anchor": f"{offset:.10f}",
                                 "value_as_number": event["value_as_number"],
                                 "value_as_concept_id": event["value_as_concept_id"],
                                 "unit_concept_id": event["unit_concept_id"]})
            audit["age_event_rows"] += 1
            if event_date < baseline:
                pre_writer.writerow(event)
                audit["preindex_event_rows"] += 1
    (root / "extract_audit.json").write_text(json.dumps(dict(sorted(audit.items())), indent=2) + "\n",
                                                encoding="utf-8")
    print(json.dumps({key: value for key, value in sorted(audit.items())
                      if key.startswith(("split_", "preindex_", "age_event"))}, indent=2))


if __name__ == "__main__":
    main()
