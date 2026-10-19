"""Build a leakage-controlled landmark extract from the SMASH v1.2 OMOP dump.

Input CSVs come from export_smash_omop.sql. Patient-level outputs belong in
private_data/ (gitignored). No inference is made from the ETL cohort dates.
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
ENDPOINTS = {
    "overall": ("Composite_Overall", "Composite_Overall_Age_Date"),
    "heart_failure": ("Composite_HF", "Composite_HF_Age_Date"),
    "ventricular_arrhythmia": ("Composite_VArrhythmia", "Composite_VArrhythmia_Age_Date"),
    "all_cause_death": ("IsDeath", "Death_Age_Date"),
}
HORIZONS = (1, 2, 5)


def rows(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        yield from csv.DictReader(handle)


def parse_date(value):
    try:
        return date.fromisoformat(value[:10]) if value else None
    except ValueError:
        return None


def positive(value):
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def write_csv(path, fieldnames, data):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export-dir", type=Path, required=True)
    parser.add_argument("--florence-dir", type=Path, required=True)
    parser.add_argument("--rennes-csv", type=Path, required=True)
    parser.add_argument("--rennes-endpoints-csv", type=Path, required=True)
    args = parser.parse_args()
    out = args.export_dir
    memberships = defaultdict(set)
    for row in rows(out / "cohort_membership.csv"):
        memberships[row["person_id"]].add(row["cohort_definition_id"])

    florence = {r["HCM_PatientKeyOutcomes_PID"]: r for r in rows(args.florence_dir / "HCM_PatientKeyOutcomes.csv")}
    florence_events = {r["HCM_Events_PID"]: r for r in rows(args.florence_dir / "HCM_Events.csv")}
    rennes = {r["Patient_ID CHU RENNES"]: r for r in rows(args.rennes_csv)}
    rennes_keys = ("Date_inclusion_TTE_baseline", "Lastfollow-up_ordeath_date", "Age_at_inclusion", "Gender_man0_woman_1")
    rennes_key = lambda row: tuple(row[name] for name in rennes_keys)
    rennes_by_key = {rennes_key(row): source_id for source_id, row in rennes.items()}
    rennes_endpoints = {}
    for row in rows(args.rennes_endpoints_csv):
        source_id = rennes_by_key.get(rennes_key(row))
        if source_id is None or source_id in rennes_endpoints:
            raise ValueError("Rennes clinical and endpoint files must link one to one")
        rennes_endpoints[source_id] = row
    if len(rennes_endpoints) != len(rennes):
        raise ValueError("Rennes endpoint linkage is incomplete")
    people = list(rows(out / "person.csv"))
    audit = Counter()
    manifest = []
    labels = []
    index_dates = {}
    index_ages = {}

    for person in people:
        pid = person["person_id"]
        source_id = person["person_source_value"]
        split_ids = memberships[pid].intersection(SPLITS)
        if len(split_ids) != 1:
            raise ValueError("Each person must belong to exactly one study split")
        site, split = SPLITS[next(iter(split_ids))]
        index = censor = None
        baseline_age = ""
        provenance = ""
        if site == "FLORENCE":
            outcome = florence.get(source_id)
            event_record = florence_events.get(source_id)
            if outcome and event_record:
                index = parse_date(outcome["FirstVisit_Age_Date"])
                censor = parse_date(event_record["Last_FollowUp_Age_Date"])
                baseline_age = outcome["FirstVisit_Age"]
                provenance = "FLORENCE curated first visit and last follow-up"
        elif site == "RENNES":
            outcome = rennes.get(source_id)
            if outcome:
                index = parse_date(outcome["Date_inclusion_TTE_baseline_date"])
                censor = parse_date(outcome["Lastfollow-up_ordeath_date_date"])
                baseline_age = outcome["Age_at_inclusion"]
                provenance = "RENNES curated baseline TTE and last follow-up"
        else:
            outcome = None
            provenance = "No locally verified clinical index or outcomes"

        valid_dates = bool(index and censor and censor >= index)
        if not index:
            audit[f"{site}_missing_index"] += 1
        if not censor:
            audit[f"{site}_missing_censor"] += 1
        if index and censor and censor < index:
            audit[f"{site}_censor_before_index"] += 1
        if index:
            index_dates[pid] = index
        if index and baseline_age:
            index_ages[pid] = float(baseline_age)
        manifest.append({
            "person_id": pid, "person_source_value": source_id,
            "site": site, "split": split,
            "index_date": index.isoformat() if index else "",
            "censor_date": censor.isoformat() if censor else "",
            "baseline_age_years": baseline_age,
            "valid_followup": int(valid_dates), "date_provenance": provenance,
            "gender_concept_id": person["gender_concept_id"],
            "race_concept_id": person["race_concept_id"],
            "ethnicity_concept_id": person["ethnicity_concept_id"],
        })
        audit[f"split_{split}"] += 1
        if valid_dates:
            audit[f"{site}_valid_followup"] += 1

        for endpoint, (status_col, date_col) in ENDPOINTS.items():
            # Rennes uses the same endpoint categories as Florence, but its
            # dated records are in the separately linked endpoint CSV.
            # Tampere has no locally available outcome follow-up.
            supported = site == "FLORENCE" and outcome is not None
            endpoint_record = outcome
            expected_cohort_id = None
            if site == "RENNES" and outcome and endpoint in ("overall", "heart_failure", "ventricular_arrhythmia"):
                supported = True
                endpoint_record = rennes_endpoints[source_id]
                status_col, date_col, expected_cohort_id = {
                    "overall": ("overall_mortality_endpoint", "overall_mortality_endpoint_date", "1302"),
                    "heart_failure": ("composite_hf_endpoint", "composite_hf_endpoint_date", "1300"),
                    "ventricular_arrhythmia": ("composite_va_endpoint", "composite_va_endpoint_date", "1301"),
                }[endpoint]
            elif site == "RENNES" and endpoint == "all_cause_death" and outcome:
                supported = True
                status_col, date_col = "Death_all_cause", "Death_all_cause_date_date"
            status = positive(endpoint_record[status_col]) if supported else False
            conflict = bool(expected_cohort_id and status != (expected_cohort_id in memberships[pid]))
            if conflict:
                audit[f"{endpoint}_cohort_status_conflict"] += 1
            event_date = parse_date(endpoint_record[date_col]) if supported and status else None
            if supported and status and event_date is None:
                audit[f"{endpoint}_positive_without_date"] += 1
            for horizon in HORIZONS:
                label = ""
                reason = "unsupported_endpoint" if not supported else "missing_or_invalid_followup"
                if conflict:
                    reason = "cohort_status_conflict"
                elif valid_dates and supported:
                    days = round(horizon * 365.2425)
                    if status and event_date and event_date < index:
                        reason = "prevalent_event"
                    elif status and event_date:
                        if event_date > censor and horizon == HORIZONS[0]:
                            audit[f"{endpoint}_event_after_recorded_followup"] += 1
                        label = int((event_date - index).days <= days)
                        reason = "observed_event"
                    elif status and not event_date:
                        reason = "positive_without_event_date"
                    elif (censor - index).days >= days:
                        label = 0
                        reason = "observed_event_free"
                    else:
                        reason = "censored_before_horizon"
                labels.append({
                    "person_id": pid, "site": site, "split": split,
                    "endpoint": endpoint, "horizon_years": horizon,
                    "label": label, "label_reason": reason,
                    "index_date": index.isoformat() if index else "",
                    "event_date": event_date.isoformat() if event_date else "",
                    "censor_date": censor.isoformat() if censor else "",
                    "event_after_recorded_followup": int(bool(valid_dates and status and event_date and event_date > censor)),
                    "cohort_status_conflict": int(conflict),
                    "time_to_event_or_censor_days": (
                        (event_date - index).days
                        if valid_dates and supported and not conflict and event_date and event_date >= index
                        else (censor - index).days if valid_dates and supported and not status and not conflict else ""
                    ),
                })
                audit[f"label_{endpoint}_{horizon}_{reason}"] += 1

    write_csv(out / "patient_manifest.csv", list(manifest[0]), manifest)
    write_csv(out / "horizon_labels.csv", list(labels[0]), labels)

    kept = Counter()
    with (out / "preindex_omop_events.csv").open("w", newline="", encoding="utf-8") as handle, \
         (out / "age_omop_events.csv").open("w", newline="", encoding="utf-8") as age_handle:
        writer = None
        age_writer = None
        for row in rows(out / "omop_events.csv"):
            if writer is None:
                writer = csv.DictWriter(handle, fieldnames=list(row))
                writer.writeheader()
                age_fields = ["person_id", "domain", "concept_id", "patient_age_at_event_years",
                              "years_from_anchor", "value_as_number", "value_as_concept_id", "unit_concept_id"]
                age_writer = csv.DictWriter(age_handle, fieldnames=age_fields)
                age_writer.writeheader()
            index = index_dates.get(row["person_id"])
            event_date = parse_date(row["event_date"])
            age_anchor = index_ages.get(row["person_id"])
            if index and event_date and age_anchor is not None:
                years_from_anchor = (event_date - index).days / 365.2425
                patient_age = age_anchor + years_from_anchor
                if 0 <= patient_age <= 120:
                    age_writer.writerow({
                        "person_id": row["person_id"], "domain": row["domain"],
                        "concept_id": row["concept_id"],
                        "patient_age_at_event_years": f"{patient_age:.4f}",
                        "years_from_anchor": f"{years_from_anchor:.4f}",
                        "value_as_number": row["value_as_number"],
                        "value_as_concept_id": row["value_as_concept_id"],
                        "unit_concept_id": row["unit_concept_id"],
                    })
                    audit["age_event_rows"] += 1
                else:
                    audit["age_event_rows_implausible_age"] += 1
            else:
                audit["age_event_rows_missing_anchor_or_date"] += 1
            if index and event_date and event_date < index:
                writer.writerow(row)
                kept[row["domain"]] += 1
            else:
                audit["omop_events_excluded_after_or_without_index"] += 1
    audit.update({f"preindex_{k}": v for k, v in kept.items()})
    (out / "extract_audit.json").write_text(json.dumps(dict(sorted(audit.items())), indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in sorted(audit.items()) if k.startswith(("split_", "preindex_", "FLORENCE_valid", "RENNES_valid"))}, indent=2))


if __name__ == "__main__":
    main()
