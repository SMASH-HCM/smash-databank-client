"""Patient-level descriptive inventory; unknown evidence stays unknown."""
from collections import defaultdict
from datetime import date
import json

from .database import quote


def records(database, table, required=("person_id",)):
    if not set(required).issubset(database.columns(table)):
        return []
    cursor = database.connection.execute("SELECT * FROM " + quote(database.table(table)))
    fields = [column[0] for column in cursor.description]
    return [dict(zip(fields, row)) for row in cursor]


def parsed(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def patient_summary(database):
    sites = database.person_sites()
    anchors, endpoints, periods = defaultdict(list), defaultdict(list), defaultdict(list)
    for row in records(database, "smash_endpoint_censor"):
        anchors[row["person_id"]].append(row)
    for row in records(database, "smash_endpoint_event"):
        endpoints[row["person_id"]].append(row)
    for row in records(database, "observation_period"):
        periods[row["person_id"]].append(row)
    visits = defaultdict(set)
    for row in records(database, "visit_occurrence"):
        visits[row["person_id"]].add(row.get("visit_occurrence_id", len(visits[row["person_id"]])))
    memberships = defaultdict(list)
    definitions = {r["cohort_id"]: r["name"] for r in database.cohorts()}
    for row in records(database, "cohort", ("subject_id", "cohort_definition_id")):
        memberships[row["subject_id"]].append(definitions.get(row["cohort_definition_id"], str(row["cohort_definition_id"])))
    # associated_file is the preferred raw-file catalogue. Do not add imaging
    # occurrences to it: the same asset could otherwise be counted twice.
    asset_table = next((t for t in ("associated_file", "smash_asset") if {"person_id", "modality"}.issubset(database.columns(t))), None)
    assets = defaultdict(lambda: defaultdict(set))
    unlinked_assets = 0
    aliases = {"ECG": "ecg", "EKG": "ecg", "MRI": "mri", "MR": "mri", "CMR": "mri", "ECHO": "echo", "ECHOCARDIOGRAPHY": "echo"}
    if asset_table:
        for position, row in enumerate(records(database, asset_table)):
            if row["person_id"] not in sites:
                unlinked_assets += 1
                continue
            modality = aliases.get(str(row.get("modality", "")).strip().upper(), "other")
            identity = row.get("associated_file_id", row.get("asset_id", position))
            assets[row["person_id"]][modality].add(identity)
    # Count only a recognised explicit ledger, never invent annual landmarks.
    training_table = next((t for t in ("smash_training_index", "smash_training_landmark") if {"person_id", "index_date"}.issubset(database.columns(t))), None)
    training = defaultdict(set)
    if training_table:
        for row in records(database, training_table):
            if parsed(row["index_date"]):
                training[row["person_id"]].add(str(row["index_date"])[:10])
    endpoint_names = sorted({str(r["endpoint"]) for values in endpoints.values() for r in values})
    rows = []
    for pid, site in sorted(sites.items()):
        ledger = anchors[pid][0] if len(anchors[pid]) == 1 else {}
        baseline = parsed(ledger.get("baseline_date"))
        age = ledger.get("baseline_age")
        starts = [parsed(p.get("observation_period_start_date")) for p in periods[pid]]
        ends = [parsed(p.get("observation_period_end_date")) for p in periods[pid]]
        start, end = min((p for p in starts if p), default=None), max((p for p in ends if p), default=None)
        def relative_age(day):
            if baseline is None or day is None or age is None:
                return None
            try:
                result = float(age) + (day - baseline).days / 365.25
                return round(result, 6) if 0 <= result <= 120 else None
            except (ValueError, TypeError):
                return None
        row = {"person_id": pid, "site": site, "cohorts": "|".join(sorted(set(memberships[pid]))),
               "observation_start_date": start.isoformat() if start else None, "observation_start_age": relative_age(start),
               "observation_end_date": end.isoformat() if end else None, "observation_end_age": relative_age(end),
               "observation_age_basis": "baseline_age_plus_elapsed_days/365.25" if baseline and age is not None else "unavailable",
               "observation_period_count": len(periods[pid]) if database.table("observation_period") else None,
               "visit_count": len(visits[pid]) if database.table("visit_occurrence") else None,
               "baseline_date": baseline.isoformat() if baseline else None, "baseline_age": age,
               "baseline_ledger_rows": len(anchors[pid]), "baseline_index_count": int(baseline is not None and age is not None),
               "training_index_count": len(training[pid]) if training_table else None,
               "training_index_status": "explicit ledger: " + training_table if training_table else "unavailable: no recognised training-index ledger",
               "censor_date": ledger.get("censor_date"), "censor_age": ledger.get("censor_age"),
               "last_contact_date": ledger.get("last_contact_date"), "last_contact_age": ledger.get("last_contact_age"),
               "file_catalogue": asset_table, "logged_file_count": sum(len(s) for s in assets[pid].values()) if asset_table else None,
               **{"logged_" + modality + "_file_count": len(assets[pid][modality]) if asset_table else None for modality in ("ecg", "echo", "mri", "other")}}
        summary = []
        for endpoint in endpoint_names:
            matches = [r for r in endpoints[pid] if str(r["endpoint"]) == endpoint]
            item = matches[0] if len(matches) == 1 else {}
            prefix = "endpoint_" + endpoint.lower() + "_"
            for field in ("status", "event_date", "event_age", "prevalent_at_baseline", "quality_flags"):
                row[prefix + field] = item.get(field)
            row[prefix + "ledger_rows"] = len(matches)
            summary.extend({k: r.get(k) for k in ("endpoint", "status", "event_date", "event_age", "prevalent_at_baseline", "quality_flags")} for r in matches)
        row["endpoint_summary"] = json.dumps(summary, separators=(",", ":"))
        rows.append(row)
    return {"report": "patients", "release": database.release_metadata(), "patients_by_site": {s: list(sites.values()).count(s) for s in set(sites.values())},
            "status": "PASS", "patients": rows, "patient_count": len(rows),
            "file_catalogue": asset_table, "unlinked_file_catalogue_rows": unlinked_assets if asset_table else None,
            "scope": "Patient-level sensitive data. Observation bounds span recorded periods and may contain gaps. Ages are approximate elapsed-day offsets from the recorded baseline age. File counts are catalogue rows, not local-file checks, studies, or proven raw-only assets. Missing tables/counts remain unknown; no annual training indices or outcome negatives are inferred."}
