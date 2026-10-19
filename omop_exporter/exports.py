"""Full-history event export; not a prediction-landmark dataset."""
from . import __version__
from .database import FACTS, quote, sha256
from .features import resolve_variables, save_variable_set
from .output import bundle, write_csv, write_json
from .availability import held_reason, policy_document
from collections import Counter
from datetime import date as calendar_date

DOMAINS = {"condition_occurrence": "condition", "measurement": "measurement", "observation": "observation", "procedure_occurrence": "procedure", "drug_exposure": "drug", "device_exposure": "device"}
FIELDS = ["person_id", "domain", "concept_id", "event_date", "value_as_number", "value_as_concept_id", "unit_concept_id"]


def export_events(database, destination, cohort=None, variables=None, time_scope="full-history", domains=None, date_start=None, date_end=None,
                  event_lookback_days=None, event_availability_policy="post-assessment", include_metadata=False):
    if time_scope not in ("full-history", "baseline"):
        raise ValueError("Event time_scope must be full-history or baseline")
    domains = set(domains) if domains is not None else set(DOMAINS.values())
    if not domains or domains - set(DOMAINS.values()):
        raise ValueError("Choose supported event domains")
    start, end = calendar_date.fromisoformat(str(date_start)) if date_start else None, calendar_date.fromisoformat(str(date_end)) if date_end else None
    if start and end and start > end:
        raise ValueError("Event start date must not exceed end date")
    if event_lookback_days is not None and (time_scope != "baseline" or type(event_lookback_days) is not int or event_lookback_days <= 0):
        raise ValueError("Event lookback requires baseline scope and a positive day count")
    availability = policy_document(event_availability_policy)
    cohort_id = database.cohort_id(cohort) if cohort is not None else None
    cohort_info = next((row for row in database.cohorts() if row["cohort_id"] == cohort_id), {}) if cohort_id is not None else {}
    selected_variables = resolve_variables(database, variables) if variables is not None else None
    anchors = {}
    if time_scope == "baseline" or include_metadata:
        if time_scope == "baseline" and (cohort_id is None or not database.capabilities()["baseline_anchors"]):
            raise ValueError("Baseline event scope requires an explicit cohort and baseline anchors")
        cols = database.columns("smash_endpoint_censor")
        if {"person_id", "baseline_date", "baseline_age"}.issubset(cols):
            selected = set(pid for pid, in database.connection.execute("SELECT DISTINCT subject_id FROM " + quote(database.table("cohort")) + " WHERE cohort_definition_id=?", (cohort_id,))) if cohort_id is not None else set(database.person_sites())
            for pid, day, age in database.connection.execute("SELECT person_id,baseline_date,baseline_age FROM " + quote(database.table("smash_endpoint_censor"))):
                if pid not in selected:
                    continue
                if pid in anchors:
                    raise ValueError("Duplicate baseline anchors")
                try:
                    anchor = (calendar_date.fromisoformat(str(day)[:10]), float(age))
                    if not 0 <= anchor[1] <= 120:
                        raise ValueError()
                    anchors[pid] = anchor
                except (ValueError, TypeError):
                    if time_scope == "baseline":
                        raise ValueError("Selected people have missing or invalid baseline dates/ages") from None
            if time_scope == "baseline" and set(anchors) != selected:
                raise ValueError("Selected people are missing baseline anchors")
    parts, parameters = [], []
    membership = database.table("cohort")
    for logical, concept, date, numeric, category, unit, source, fact_id in FACTS:
        if DOMAINS[logical] not in domains:
            continue
        table, columns = database.table(logical), database.columns(logical)
        if not table or not {"person_id", concept, date}.issubset(columns):
            continue
        concept_ids = [cid for name, cid in selected_variables if name == logical] if selected_variables is not None else None
        if concept_ids == []:
            continue
        def field(name):
            return quote(name) if name in columns else "NULL"
        part = "SELECT person_id,'" + DOMAINS[logical] + "' AS domain," + quote(concept) + " AS concept_id," + quote(date) + " AS event_date," + field(numeric) + " AS value_as_number," + field(category) + " AS value_as_concept_id," + field(unit) + " AS unit_concept_id," + field(fact_id) + " AS fact_id," + field(source) + " AS source_value,'" + logical + "' AS fact_table FROM " + quote(table)
        predicates = []
        if logical == "observation" and source in columns:
            predicates.append("(" + quote(source) + " IS NULL OR " + quote(source) + " NOT LIKE 'SMASH:%')")
        if logical == "observation" and {"concept_id", "concept_name"}.issubset(database.columns("concept")):
            management = [cid for cid, name in database.concept_names().items() if str(name).casefold().startswith("smash cohort membership:")]
            if management:
                predicates.append(quote(concept) + " NOT IN (" + ",".join("?" for _ in management) + ")")
                parameters.extend(management)
        if cohort_id is not None:
            predicates.append("person_id IN (SELECT subject_id FROM " + quote(membership) + " WHERE cohort_definition_id=?)")
            parameters.append(cohort_id)
        if concept_ids is not None:
            predicates.append(quote(concept) + " IN (" + ",".join("?" for _ in concept_ids) + ")")
            parameters.extend(concept_ids)
        parts.append(part + (" WHERE " + " AND ".join(predicates) if predicates else ""))
    if not parts:
        raise ValueError("Database has no supported dated clinical fact tables")
    initial = database.path.stat()
    digest = sha256(database.path)
    rows_written = 0
    excluded = Counter()
    names = database.concept_names() if time_scope == "baseline" else {}
    sites = database.person_sites() if include_metadata else {}
    fields = FIELDS + (["fact_id", "source_value", "fact_table", "site", "days_before_baseline", "event_age_years"] if include_metadata else [])
    def rows():
        nonlocal rows_written
        for row in database.connection.execute(" UNION ALL ".join(parts) + " ORDER BY person_id,event_date,domain,concept_id,fact_id", parameters):
            try:
                event = calendar_date.fromisoformat(str(row[3])[:10])
            except ValueError:
                event = None
            if ((start or end or time_scope == "baseline") and event is None):
                excluded["invalid_date"] += 1
                continue
            if (start and event < start) or (end and event > end):
                excluded["outside_calendar_range"] += 1
                continue
            anchor = anchors.get(row[0])
            elapsed = (anchor[0] - event).days if anchor and event else None
            if time_scope == "baseline":
                if elapsed is None or elapsed < 0 or (event_lookback_days is not None and elapsed > event_lookback_days):
                    excluded["outside_baseline_boundary"] += 1
                    continue
                reason = held_reason(row[9], row[2], names.get(row[2], ""), elapsed == 0, event_availability_policy)
                if reason:
                    excluded[reason] += 1
                    continue
            rows_written += 1
            result = dict(zip(FIELDS, row[:7]))
            if include_metadata:
                result.update(fact_id=row[7], source_value=row[8], fact_table=row[9], site=sites.get(row[0], "UNKNOWN"),
                              days_before_baseline=elapsed, event_age_years=anchor[1] - elapsed / 365.25 if elapsed is not None else None)
            yield result
    with bundle(destination) as stage:
        if selected_variables is not None:
            save_variable_set(stage / "variable_set.json", database, selected_variables)
        write_csv(stage / "omop_events.csv", fields, rows())
        final = database.path.stat()
        wal = database.path.with_name(database.path.name + "-wal")
        if (initial.st_size, initial.st_mtime_ns) != (final.st_size, final.st_mtime_ns) or (wal.exists() and wal.stat().st_size):
            raise ValueError("Source changed or has WAL content; use a finalized release snapshot")
        write_json(stage / "dataset_manifest.json", {"format": "events", "exporter_version": __version__, "release": database.release_metadata(),
                   "database_sha256": digest, "cohort_id": cohort_id, "cohort_name": cohort_info.get("name"), "source_cohort_name": cohort_info.get("source_name"), "rows": rows_written, "columns": fields, "variables": selected_variables,
                   "time_scope": time_scope, "domains": sorted(domains), "date_start": date_start, "date_end": date_end, "lookback_days": event_lookback_days,
                   "include_metadata": include_metadata, "availability_policy": availability if time_scope == "baseline" else None, "excluded_events": dict(excluded),
                   "time_policy": "Full history within any requested calendar range, including post-baseline facts. Consumers must enforce prediction availability boundaries." if time_scope == "full-history" else "On/before each clinical baseline with the configured availability mask; no outcome labels or risk sets generated. Source-role classification remains incomplete.",
                   "output_sha256": {"omop_events.csv": sha256(stage / "omop_events.csv")}})
    return {"rows": rows_written, "format": "events"}
