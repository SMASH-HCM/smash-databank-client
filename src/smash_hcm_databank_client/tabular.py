"""Baseline feature-only tables using embedded OMOP cohort and anchor tables.

Exact overlap is structural, not proof of cross-site clinical equivalence.
No future values, assumed negatives, fitted preprocessing or outcome columns.
"""
from collections import Counter, defaultdict
from datetime import date
import json
import hashlib
import math
from statistics import mean

from . import __version__
from .database import FACTS, quote, sha256
from .features import resolve_variables, save_variable_set, selection_spec, anchor_features
from .availability import held_reason, policy_document
from .output import bundle, write_csv, write_json


HISTORY_FEATURES = ("previous-value", "previous-age-days", "last-age-days", "count", "mean", "min", "max")


def resolve_cell(table, cid, values, units, snapshot=False):
    if table in {"condition_occurrence", "procedure_occurrence", "drug_exposure", "device_exposure"}:
        return 1, "documented_positive_on_snapshot_day" if snapshot else "documented_positive_in_window", ""
    if table == "observation" and cid == 3021806:
        return "", "requires_medication_class_context", ""
    numbers = {float(n) for n, _, _ in values if n is not None}
    codes = {c for _, c, _ in values if c not in (None, 0)}
    numeric_units = {u for n, _, u in values if n is not None}
    if numbers and codes:
        return "", "mixed_numeric_categorical", ""
    if numbers:
        if not all(math.isfinite(n) for n in numbers):
            return "", "nonfinite_value", ""
        if None in numeric_units or 0 in numeric_units:
            return "", "unknown_unit", ""
        if len(numeric_units) != 1 or len(units) != 1:
            return "", "unit_conflict", ""
        if len(numbers) != 1:
            return "", "conflicting_latest_values", ""
        return next(iter(numbers)), "ok", next(iter(numeric_units))
    if len(codes) == 1:
        return next(iter(codes)), "coded_category_id", ""
    return "", "conflicting_latest_categories" if codes else "no_supported_value", ""


def export_wide(database, destination, cohort, variables="core", index="baseline", lookback_days=None, availability_policy="post-assessment", tabular_mode="snapshot", history_features=()):
    initial = database.path.stat()
    availability = policy_document(availability_policy)
    if index != "baseline":
        raise ValueError("Annual training indexes require a separately reviewed endpoint/risk-set policy; only baseline is supported here")
    if tabular_mode not in ("snapshot", "latest-history"):
        raise ValueError("tabular_mode must be snapshot or latest-history")
    if tabular_mode == "snapshot":
        if lookback_days is not None:
            raise ValueError("lookback_days requires explicit latest-history mode; snapshots never carry earlier values forward")
        if availability_policy == "strict-before":
            raise ValueError("An exact-day snapshot needs baseline-day availability; strict-before requires explicit latest-history mode")
    elif type(lookback_days) is not int or lookback_days <= 0:
        raise ValueError("latest-history requires an explicit positive lookback_days")
    history_features = list(dict.fromkeys(history_features))
    if any(value not in HISTORY_FEATURES for value in history_features) or (history_features and tabular_mode != "latest-history"):
        raise ValueError("History features require latest-history mode and supported feature names")
    _, families = selection_spec(variables)
    anchor_columns = anchor_features(variables)
    if families and history_features:
        raise ValueError("Categorical family consolidation and derived history columns must be exported separately")
    availability.update(tabular_mode=tabular_mode, lookback_days=lookback_days, carry_forward=tabular_mode == "latest-history")
    if not database.capabilities()["baseline_anchors"]:
        raise ValueError("This database lacks populated clinical baseline anchors; inventory/event exports remain available")
    cohort_id = database.cohort_id(cohort)
    cohort_info = next(row for row in database.cohorts() if row["cohort_id"] == cohort_id)
    selected = [pid for (pid,) in database.connection.execute("SELECT DISTINCT subject_id FROM " + quote(database.table("cohort")) + " WHERE cohort_definition_id=? ORDER BY subject_id", (cohort_id,))]
    if not selected:
        raise ValueError("Selected cohort has no people")
    selected_set = set(selected)
    people, names = database.person_sites(), database.concept_names()
    if not selected_set.issubset(people):
        raise ValueError("Cohort contains unmatched person IDs")
    anchors = {}
    for pid, day, age in database.connection.execute("SELECT person_id,baseline_date,baseline_age FROM " + quote(database.table("smash_endpoint_censor"))):
        if pid not in selected_set:
            continue
        if pid in anchors:
            raise ValueError("Selected people have duplicate baseline anchors")
        try:
            parsed, numeric_age = date.fromisoformat(str(day)[:10]), float(age)
            if not 0 <= numeric_age <= 120:
                raise ValueError()
        except (TypeError, ValueError):
            raise ValueError("Selected people have missing or invalid baseline dates/ages") from None
        anchors[pid] = (parsed, numeric_age)
    if set(anchors) != selected_set:
        raise ValueError("Selected people are missing clinical baseline anchors; no dates were inferred")
    keys = resolve_variables(database, variables)
    by_table = defaultdict(list)
    for table, cid in keys:
        by_table[table].append(cid)
    latest, held, removed = {}, {}, []
    historical = defaultdict(lambda: defaultdict(list))
    units = defaultdict(set)
    for logical, concept, day, numeric, category, unit, source, fact_id in FACTS:
        if logical not in by_table:
            continue
        table, columns = database.table(logical), database.columns(logical)
        if not table or not {"person_id", concept, day}.issubset(columns):
            continue  # Preserve the requested column, entirely missing at this site/release.
        def field(name):
            return quote(name) if name in columns else "NULL"
        ids = by_table[logical]
        if numeric in columns and unit in columns:
            for cid, unit_id in database.connection.execute("SELECT DISTINCT " + quote(concept) + "," + quote(unit) + " FROM " + quote(table) + " WHERE " + quote(numeric) + " IS NOT NULL AND " + quote(unit) + ">0 AND " + quote(concept) + " IN (" + ",".join("?" for _ in ids) + ")", ids):
                units[(logical, cid)].add(unit_id)
        query = "SELECT person_id," + quote(concept) + "," + quote(day) + "," + field(numeric) + "," + field(category) + "," + field(unit) + "," + field(fact_id) + " FROM " + quote(table) + " WHERE person_id IN (SELECT subject_id FROM " + quote(database.table("cohort")) + " WHERE cohort_definition_id=?) AND " + quote(concept) + " IN (" + ",".join("?" for _ in ids) + ")"
        for pid, cid, event_day, number, coded, unit_id, record_id in database.connection.execute(query, [cohort_id, *ids]):
            try:
                event = date.fromisoformat(str(event_day)[:10])
            except ValueError:
                continue
            elapsed = (anchors[pid][0] - event).days
            if elapsed < 0 or (tabular_mode == "snapshot" and elapsed != 0) or (tabular_mode == "latest-history" and elapsed > lookback_days):
                continue
            key = (pid, logical, cid)
            reason = held_reason(logical, cid, names.get(cid, ""), elapsed == 0, availability_policy)
            if reason:
                held[key] = reason
                removed.append({"person_id": pid, "landmark_id": str(pid) + ":baseline", "table": logical, "concept_id": cid, "fact_id": record_id, "event_date": event.isoformat(), "reason": reason})
                continue
            previous = latest.get(key)
            value = (number, coded, unit_id)
            if history_features:
                historical[key][event].append(value)
            if previous is None or event > previous[0]:
                latest[key] = (event, [value])
            elif event == previous[0]:
                previous[1].append(value)
    # Unit identity is resolved across the release, not refitted on each site.
    fields = ["person_id", "site", "cohort", "snapshot_date"] + [table + "__" + str(cid) for table, cid in keys] + anchor_columns
    fields += [table + "__" + str(cid) + "__" + option.replace("-", "_") for table, cid in keys for option in history_features]
    audit, rows, samples, provenance, history_provenance = Counter(), [], [], [], []
    presence = {"condition_occurrence", "procedure_occurrence", "drug_exposure", "device_exposure"}
    for pid in selected:
        anchor, age = anchors[pid]
        sample_id = str(pid) + ":baseline"
        row = {"person_id": pid, "site": people[pid], "cohort": cohort_info["name"], "snapshot_date": anchor.isoformat()}
        if "baseline_age_years" in anchor_columns:
            row["baseline_age_years"] = age
            provenance.append({"landmark_id": sample_id, "feature": "baseline_age_years", "table": "smash_endpoint_censor", "concept_id": "",
                               "unit_concept_id": "", "event_date": anchor.isoformat(), "qc_reason": "embedded_baseline_age_years"})
        samples.append({"landmark_id": sample_id, "person_id": pid, "baseline_date": anchor.isoformat(), "baseline_age_years": age})
        for table, cid in keys:
            feature = table + "__" + str(cid)
            cell, reason, unit = "", held.get((pid, table, cid), "no_eligible_evidence"), ""
            evidence = latest.get((pid, table, cid))
            if evidence:
                cell, reason, unit = resolve_cell(table, cid, evidence[1], units[(table, cid)], tabular_mode == "snapshot")
            row[feature] = cell
            audit[reason] += 1
            provenance.append({"landmark_id": sample_id, "feature": feature, "table": table, "concept_id": cid,
                               "unit_concept_id": unit, "event_date": evidence[0].isoformat() if evidence else "", "qc_reason": reason})
            if history_features:
                days = sorted(historical[(pid, table, cid)], reverse=True)
                resolved = [(day, *resolve_cell(table, cid, historical[(pid, table, cid)][day], units[(table, cid)])) for day in days]
                history_provenance.extend({"landmark_id": sample_id, "feature": feature, "event_date": day.isoformat(),
                                           "value": value, "qc_reason": qc, "unit_concept_id": u} for day, value, qc, u in resolved)
                previous = resolved[1] if len(resolved) > 1 else None
                valid_numeric = [value for _, value, qc, _ in resolved if qc == "ok"]
                numeric_only = table in ("measurement", "observation") and all(qc not in ("coded_category_id", "conflicting_latest_categories", "mixed_numeric_categorical") for _, _, qc, _ in resolved)
                derived = {"previous-value": previous[1] if previous else "",
                           "previous-age-days": (anchor - previous[0]).days if previous and previous[1] != "" else "",
                           "last-age-days": (anchor - evidence[0]).days if evidence and cell != "" else "",
                           "count": sum(value != "" for _, value, _, _ in resolved) if resolved else "",
                           "mean": mean(valid_numeric) if numeric_only and valid_numeric else "",
                           "min": min(valid_numeric) if numeric_only and valid_numeric else "",
                           "max": max(valid_numeric) if numeric_only and valid_numeric else ""}
                for option in history_features:
                    column = feature + "__" + option.replace("-", "_")
                    row[column] = derived[option]
                    derived_unit = previous[3] if option == "previous-value" and previous else next((u for _, _, qc, u in resolved if qc == "ok"), "") if option in ("mean", "min", "max") else ""
                    provenance.append({"landmark_id": sample_id, "feature": column, "table": table, "concept_id": cid,
                                       "unit_concept_id": derived_unit,
                                       "event_date": previous[0].isoformat() if option.startswith("previous-") and previous else evidence[0].isoformat() if evidence and option == "last-age-days" else "",
                                       "qc_reason": "explicit_history_" + option if row[column] != "" else "no_valid_history_value"})
        rows.append(row)
    if families:
        source_provenance = {(p["landmark_id"], p["feature"]): p for p in provenance}
        for family in families:
            categories = {int(cid): label for cid, label in family["categories"].items()}
            member_fields = [family["table"] + "__" + str(cid) for cid in categories]
            fields = [field for field in fields if field not in member_fields] + [family["name"]]
            for row in rows:
                sample_id = str(row["person_id"]) + ":baseline"
                candidates = [(source_provenance[(sample_id, family["table"] + "__" + str(cid))]["event_date"], label)
                              for cid, label in categories.items() if row.get(family["table"] + "__" + str(cid)) == 1]
                latest_day = max((day for day, _ in candidates), default="")
                grades = {label for day, label in candidates if day == latest_day}
                row[family["name"]] = next(iter(grades)) if len(grades) == 1 else ""
                provenance.append({"landmark_id": sample_id, "feature": family["name"], "table": family["table"], "concept_id": "",
                                   "unit_concept_id": "", "event_date": latest_day, "qc_reason": "family_category" if len(grades) == 1 else "family_conflict" if grades else "family_unknown_or_held"})
    with bundle(destination) as stage:
        write_json(stage / "availability_policy.json", availability)
        write_csv(stage / "availability_exclusions.csv", ["person_id", "landmark_id", "table", "concept_id", "fact_id", "event_date", "reason"], removed)
        save_variable_set(stage / "variable_set.json", database, {"keys": keys, "families": families, "anchor_features": anchor_columns})
        write_json(stage / "feature_definitions.json", {"columns": fields[4:], "source_variables": keys, "families": families, "anchor_features": anchor_columns, "history_features": history_features})
        write_csv(stage / "data.csv", fields, rows)
        write_csv(stage / "samples.csv", ["landmark_id", "person_id", "baseline_date", "baseline_age_years"], samples)
        write_csv(stage / "variables.csv", ["feature", "table", "concept_id", "concept_name", "unit_concept_ids"],
                  [{"feature": table + "__" + str(cid), "table": table, "concept_id": cid, "concept_name": names.get(cid, ""), "unit_concept_ids": "|".join(map(str, sorted(units[(table, cid)])))} for table, cid in keys])
        write_csv(stage / "feature_provenance.csv", ["landmark_id", "feature", "table", "concept_id", "unit_concept_id", "event_date", "qc_reason"], provenance)
        if history_features:
            write_csv(stage / "history_provenance.csv", ["landmark_id", "feature", "event_date", "value", "qc_reason", "unit_concept_id"], history_provenance)
        wal = database.path.with_name(database.path.name + "-wal")
        digest = sha256(database.path)
        final = database.path.stat()
        if (wal.exists() and wal.stat().st_size) or (initial.st_size, initial.st_mtime_ns) != (final.st_size, final.st_mtime_ns):
            raise ValueError("Use a stable finalized standalone database snapshot without WAL content")
        write_json(stage / "dataset_manifest.json", {"format": "tabular", "exporter_version": __version__, "release": database.release_metadata(),
                   "database_sha256": digest, "cohort_id": cohort_id, "cohort_name": cohort_info["name"], "source_cohort_name": cohort_info["source_name"], "rows": len(rows), "columns": fields,
                   "feature_columns": fields[4:], "metadata_columns": fields[:4], "feature_count": len(fields) - 4, "source_variable_count": len(keys), "layout": "point-in-time-v1",
                   "variable_set_sha256": hashlib.sha256(json.dumps(keys, separators=(",", ":")).encode()).hexdigest(),
                   "variables": keys, "index": "baseline", "availability_policy": availability_policy, "tabular_mode": tabular_mode,
                   "boundary": "exact baseline date only; post-assessment/pre-intervention mask" if tabular_mode == "snapshot" else "on/before baseline with post-assessment/pre-intervention mask" if availability_policy == "post-assessment" else "strictly before baseline date", "lookback_days": lookback_days,
                   "aggregation": "explicit derived history columns; see history_definition" if history_features else "none; conflicting same-day values are held blank, identical repeats do not add columns", "carry_forward": tabular_mode == "latest-history",
                   "feature_families": families, "anchor_features": anchor_columns, "history_features": history_features,
                   "history_definition": "Inclusive lookback to prediction boundary after availability mask. One QC-valid value per distinct date, identical repeats collapsed, conflicting dates excluded from numeric summaries. Previous is the preceding distinct observed date, not the previous raw row; a conflicting previous date stays blank. Count is valid observed dates, blank when none; numeric summaries never average category IDs or mix units. Ages are days before baseline. No observation-window completeness is assumed.",
                   "availability_excluded_events": len(removed), "availability_affected_people": len({row["person_id"] for row in removed}), "availability": availability,
                   "qc_counts": dict(audit), "labels": "not included; feature-only export",
                   "clinical_status": "Exact concept overlap; cross-site equivalence is not established. Presence is documented positive, absence remains blank.",
                   "output_sha256": {p.name: sha256(p) for p in stage.glob("*.csv")}})
    return {"format": "tabular", "rows": len(rows), "variables": len(fields) - 4}
