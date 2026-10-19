"""Aggregate reports calculated from the supplied database only."""
from collections import Counter, defaultdict
import math
from statistics import mean, median, pstdev

from .database import SITES, quote

REPORTS = {"inventory": "OMOP tables, columns, variables and site populations", "cohorts": "Cohort membership summary",
           "endpoints": "Endpoint/status summary", "overlap": "CORE and two-site variables", "distributions": "CORE + two-site numeric distributions by site/unit"}
REPORTS["patients"] = "Patient-level inventory: observation, visits, files, baseline and endpoints (sensitive)"
REPORTS["features"] = "Named feature sets, concept IDs and explicit category-family definitions"


def inventory(database):
    variables = database.variables()
    tables = []
    for name, kind in sorted(database.objects.items()):
        tables.append({"table": name, "kind": kind, "rows": database.connection.execute("SELECT count(*) FROM " + quote(name)).fetchone()[0],
                       "columns": [{"name": r[1], "type": r[2], "required": bool(r[3]), "primary_key": bool(r[5])} for r in database.connection.execute("PRAGMA table_info(" + quote(name) + ")")]})
    return {"report": "inventory", "release": database.release_metadata(), "capabilities": database.capabilities(),
            "patients_by_site": dict(sorted(Counter(database.person_sites().values()).items())),
            "tables": tables, "cohorts": database.cohorts(), "variables": variables,
            "scope": "Full loaded history; cohort memberships overlap; no clinical-equivalence or baseline-availability claim."}


def overlap(database):
    populations = Counter(database.person_sites().values())
    if populations.get("UNKNOWN") or any(not populations.get(site) for site in SITES):
        raise ValueError("Three-site overlap requires Florence, Rennes and Tampere populations with known site metadata")
    grouped = defaultdict(dict)
    names = {}
    for row in database.variables():
        if row["site"] not in SITES:
            raise ValueError("Clinical facts have unmatched person/site metadata")
        key = (row["table"], row["concept_id"])
        grouped[key][row["site"]] = {"patients": row["patients"], "facts": row["facts"], "coverage": row["patients"] / populations[row["site"]]}
        names[key] = row["concept_name"]
    core, two_site = [], []
    for (table, cid), sites in sorted(grouped.items()):
        row = {"table": table, "concept_id": cid, "concept_name": names[(table, cid)], "site_pair": "|".join(site for site in SITES if site in sites), "sites": sites}
        if len(sites) == 3:
            core.append(row)
        elif len(sites) == 2:
            two_site.append(row)
    return {"report": "overlap", "release": database.release_metadata(), "patients_by_site": dict(populations),
            "definition": "Exact (fact table, target concept_id) presence over full history; concept 0 and cohort-management concepts excluded. Two-site rows are exclusive. Demographics/death/derived medication classes excluded.",
            "core": core, "two_site": two_site, "core_count": len(core), "two_site_count": len(two_site),
            "two_site_counts": dict(sorted(Counter(row["site_pair"] for row in two_site).items())),
            "clinical_status": "Observed overlap candidates; units, contexts and baseline eligibility require separate review."}


def summary_report(database, kind):
    if kind == "features":
        from .features import PRESETS, resolve_variables, selection_spec, anchor_features
        names = database.concept_names()
        rows, sets = [], []
        for preset, label in PRESETS.items():
            try:
                keys = resolve_variables(database, preset)
                _, families = selection_spec(preset)
                sets.append({"name": preset, "label": label, "source_variable_count": len(keys), "families": families, "anchor_features": anchor_features(preset)})
                rows.extend({"set": preset, "table": table, "concept_id": cid, "concept_name": names.get(cid, "")} for table, cid in keys)
            except ValueError as exc:
                sets.append({"name": preset, "label": label, "unavailable": str(exc)})
        return {"report": kind, "release": database.release_metadata(), "patients_by_site": dict(Counter(database.person_sites().values())),
                "status": "PASS", "features": rows, "sets": sets,
                "scope": "Versioned source concept lists; clinical equivalence and baseline availability are not inferred. Minimal list is a starter selection, not a validated prediction score. Consolidation is explicit and preserves unknown categories."}
    if kind == "patients":
        from .patients import patient_summary
        return patient_summary(database)
    if kind == "inventory":
        return inventory(database)
    if kind == "overlap":
        return overlap(database)
    base = {"report": kind, "release": database.release_metadata(), "patients_by_site": dict(Counter(database.person_sites().values()))}
    if kind == "cohorts":
        rows = database.cohorts()
        return {**base, "status": "PASS" if database.capabilities()["cohorts"] and rows else "UNAVAILABLE",
                "cohorts": rows, "scope": "Embedded cohort definitions and distinct memberships; missing definitions/memberships are not inferred."}
    if kind == "endpoints":
        if not database.capabilities()["endpoint_labels"]:
            return {**base, "status": "UNAVAILABLE", "endpoints": [], "scope": "No populated embedded smash_endpoint_event ledger; absence is not a negative outcome."}
        sites = database.person_sites()
        grouped = defaultdict(set)
        query = "SELECT person_id,endpoint,status FROM " + quote(database.table("smash_endpoint_event"))
        for pid, endpoint, status in database.connection.execute(query):
            grouped[(str(endpoint), str(status), sites.get(pid, "UNKNOWN"))].add(pid)
        rows = [{"endpoint": endpoint, "status": status, "site": site, "patients": len(people)} for (endpoint, status, site), people in sorted(grouped.items())]
        return {**base, "status": "PASS", "endpoints": rows, "scope": "Distinct people per recorded endpoint/status/site. Categories can overlap; unknown outcomes remain separate."}
    if kind != "distributions":
        raise ValueError("Unknown summary report")
    from .features import resolve_variables
    from .database import FACTS
    keys = set(resolve_variables(database, "core+two-site"))
    groups, excluded = defaultdict(list), 0
    sites, names = database.person_sites(), database.concept_names()
    for logical, concept, day, numeric, category, unit, *_ in FACTS:
        columns = database.columns(logical)
        if not numeric or not {"person_id", concept, numeric}.issubset(columns):
            continue
        unit_sql = quote(unit) if unit in columns else "NULL"
        query = "SELECT person_id," + quote(concept) + "," + quote(numeric) + "," + unit_sql + " FROM " + quote(database.table(logical)) + " WHERE " + quote(numeric) + " IS NOT NULL"
        for pid, cid, value, unit_id in database.connection.execute(query):
            if (logical, cid) not in keys:
                continue
            try:
                value = float(value)
                if not math.isfinite(value):
                    raise ValueError()
            except (TypeError, ValueError):
                excluded += 1
                continue
            groups[(logical, cid, sites.get(pid, "UNKNOWN"), unit_id or 0)].append(value)
    rows = []
    for (table, cid, site, unit), values in sorted(groups.items()):
        values.sort()
        def percentile(p):
            index = (len(values) - 1) * p
            lo, hi = math.floor(index), math.ceil(index)
            return values[lo] + (values[hi] - values[lo]) * (index - lo)
        q1, q3 = percentile(.25), percentile(.75)
        rows.append({"table": table, "concept_id": cid, "concept_name": names.get(cid, ""), "site": site, "unit_concept_id": unit,
                     "n": len(values), "mean": mean(values), "median": median(values), "q1": q1, "q3": q3, "iqr": q3 - q1,
                     "min": values[0], "max": values[-1], "stddev_population": pstdev(values)})
    return {**base, "status": "PASS", "distributions": rows, "excluded_nonfinite_or_invalid": excluded,
            "scope": "All numeric observations, not one value per patient or baseline. Units stratified; unit 0 means unknown. No unit conversion or clinical equivalence assumed."}


def write_report(database, kind, destination):
    from .output import bundle, write_json, write_csv
    report = summary_report(database, kind)
    with bundle(destination) as stage:
        write_json(stage / "report.json", report)
        (stage / "summary.txt").write_text("SMASH-HCM " + kind + " report\nStatus: " + report.get("status", "PASS") + "\nPatients by site: " + str(report["patients_by_site"]) + "\n" + report.get("scope", report.get("definition", "")) + "\n", encoding="utf-8")
        if kind == "inventory":
            write_csv(stage / "variables.csv", ["table", "concept_id", "concept_name", "site", "patients", "facts"], report["variables"])
            write_csv(stage / "tables.csv", ["table", "kind", "rows"], report["tables"])
            write_csv(stage / "columns.csv", ["table", "name", "type", "required", "primary_key"], [{"table": table["table"], **column} for table in report["tables"] for column in table["columns"]])
            write_csv(stage / "cohorts.csv", ["cohort_id", "name", "source_name", "patients"], report["cohorts"])
        elif kind in ("patients", "features"):
            write_csv(stage / (kind + ".csv"), list(report[kind][0]) if report[kind] else ["person_id"] if kind == "patients" else ["set", "table", "concept_id"], report[kind])
        elif kind == "overlap":
            fields = ["table", "concept_id", "concept_name", "site_pair"] + [site + "_" + key for site in SITES for key in ("patients", "facts", "coverage")]
            for name in ("core", "two_site"):
                rows = [{**row, **{site + "_" + key: value for site, counts in row["sites"].items() for key, value in counts.items()}} for row in report[name]]
                write_csv(stage / (name + ".csv"), fields, rows)
        else:
            fields = {"cohorts": ["cohort_id", "name", "source_name", "patients"], "endpoints": ["endpoint", "status", "site", "patients"],
                      "distributions": ["table", "concept_id", "concept_name", "site", "unit_concept_id", "n", "mean", "median", "q1", "q3", "iqr", "min", "max", "stddev_population"]}[kind]
            write_csv(stage / (kind + ".csv"), fields, report[kind])
    return report


def write_data_report(database, kind, data_dir):
    """Public report tables/text directly under DATA_DIR/reports; audit JSON beside."""
    import os
    from pathlib import Path
    import shutil
    import tempfile
    if kind not in REPORTS:
        raise ValueError("Unknown summary report")
    data_root = Path(data_dir).expanduser().resolve()
    root = data_root / "reports"
    if root.resolve().parent != data_root:
        raise ValueError("Reports directory must remain within DATA_DIR")
    root.mkdir(parents=True, exist_ok=True)
    companion, summary, table = root / kind, root / (kind + ".txt"), root / (kind + ".csv")
    if any(path.exists() for path in (companion, summary, table)):
        raise FileExistsError("Report output already exists; choose a new DATA_DIR")
    stage = Path(tempfile.mkdtemp(prefix=".omop-report-", dir=str(root)))
    published = []
    try:
        report = write_report(database, kind, stage / kind)
        for source, target in ((stage / kind / "summary.txt", summary), (stage / kind / (kind + ".csv"), table)):
            if source.exists():
                with target.open("xb") as dest, source.open("rb") as src:
                    published.append(target)
                    shutil.copyfileobj(src, dest)
        if companion.exists():
            raise FileExistsError("Report directory appeared during generation")
        os.rename(stage / kind, companion)
        published.append(companion)
        return report
    except Exception:
        for path in reversed(published):
            if path.resolve().parent != root:
                raise ValueError("Unsafe report rollback path")
            shutil.rmtree(path) if path.is_dir() else path.unlink()
        raise
    finally:
        if stage.exists() and stage.resolve().parent == root and stage.name.startswith(".omop-report-"):
            shutil.rmtree(stage)
