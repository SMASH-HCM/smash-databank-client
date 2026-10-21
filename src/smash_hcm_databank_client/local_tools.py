"""Local-database report, variable-set and cohort export workflows."""
from pathlib import Path
import uuid

from .database import OmopDatabase
from .exports import export_events, DOMAINS
from .features import PRESETS, load_variable_set, resolve_variables, save_variable_set, variable_catalog, freeze_selection, selection_spec, anchor_features
from .datasets import export_dataset
from .output import bundle, write_json
from .prompts import ask, choose, choose_many, confirm, text
from .reports import REPORTS, summary_report, write_report, write_data_report
from .tabular import export_wide, HISTORY_FEATURES


def select_variables(workspace, database, read=input, write=print, plain=False, custom_only=False):
    options, resolved, reasons = [], {}, {}
    if not custom_only:
        for name, label in PRESETS.items():
            options.append((name, label))
            try:
                keys = resolve_variables(database, name)
                resolved[name] = freeze_selection(database, name)
                options[-1] = (name, label + " (" + str(len(keys)) + " source variables" + (" + baseline age" if anchor_features(name) else "") + ")")
            except ValueError as exc:
                reasons[name] = str(exc)
    for path in sorted((workspace.root / "variable_sets").glob("*.json")):
        try:
            data = load_variable_set(path)
            name = "saved:" + str(path)
            options.append((name, "Saved: " + data["name"] + " (" + str(len(data["keys"])) + " variables)"))
            resolved[name] = data
        except (OSError, ValueError):
            pass
    options += [("custom", "Choose variables from the database list"), ("load", "Load a saved variable-set JSON file")]
    option = choose(options, lambda row: row[1], read, write, plain, disabled=lambda row: reasons.get(row[0], ""), message="Choose variables")
    if not option:
        return None
    if option[0] in resolved:
        keys = resolved[option[0]]
    elif option[0] == "load":
        path = ask("Variable-set JSON file", read=read, write=write, plain=plain, path=True).strip().strip('"')
        data = load_variable_set(path) if path else None
        keys = data if data else None
        if not keys:
            return None
    else:
        catalog = variable_catalog(database)
        search = ask("Filter by name, concept ID or table (Enter lists all)", read=read, write=write, plain=plain).casefold()
        if search:
            catalog = [row for row in catalog if search in (row["table"] + " " + str(row["concept_id"]) + " " + row["concept_name"]).casefold()]
        if not catalog:
            write("No variables matched this filter.")
            return None
        selected = choose_many(catalog, lambda row: row["table"] + " | " + str(row["concept_id"]) + " | " + row["concept_name"] + " | " + "/".join(row["sites"]), read, write, plain, message="Tick the variables to include")
        if not selected:
            return None
        keys = [(row["table"], row["concept_id"]) for row in selected]
        name = ask("Name for this reusable variable set", "Custom variables", read, write, plain)
        path = workspace.root / "variable_sets" / (uuid.uuid4().hex + ".json")
        save_variable_set(path, database, keys, name)
        write("Variable set saved: " + text(path))
    available = {(row["table"], row["concept_id"]) for row in variable_catalog(database)}
    missing = set(resolve_variables(database, keys)) - available
    if missing:
        write(str(len(missing)) + " saved variables have no evidence in this database; their tabular columns will remain blank.")
    return keys


def export_cohorts(database, destination, cohorts, variables, fmt):
    """Reuse one frozen variable list for explicit cohorts; never randomly split."""
    keys = freeze_selection(database, variables)
    cohorts = list(dict.fromkeys(cohorts))
    if not cohorts or fmt not in ("tabular", "events"):
        raise ValueError("Choose cohorts and a supported export format")
    def export(output, cohort):
        return export_wide(database, output, cohort, keys) if fmt == "tabular" else export_events(database, output, cohort, keys)
    if len(cohorts) == 1:
        return export(destination, cohorts[0])
    rows, entries = 0, []
    with bundle(destination) as stage:
        for cohort in cohorts:
            cohort_id = database.cohort_id(cohort) if cohort is not None else None
            folder = "cohort-" + str(cohort_id) if cohort_id is not None else "all-people"
            result = export(stage / folder, cohort)
            rows += result["rows"]
            entries.append({"cohort_id": cohort_id, "directory": folder, **result})
        save_variable_set(stage / "variable_set.json", database, keys)
        write_json(stage / "cohort_exports.json", {"format": fmt, "cohorts": entries, "policy": "Existing database memberships, no random splitting; identical ordered feature list for every cohort."})
    return {"rows": rows, "format": fmt, "cohorts": len(entries)}


def export_menu(workspace, read=input, write=print, plain=False):
    with OmopDatabase(workspace.state["active_db"]) as database:
        cohorts = database.cohorts() if database.capabilities()["cohorts"] else []
        if cohorts:
            selected = choose_many(cohorts, lambda row: str(row["cohort_id"]) + " | " + row["name"] + " | " + str(row["patients"]) + " people", read, write, plain, message="Select cohort(s): train/test memberships are preserved")
            if not selected:
                return
            cohort_ids = [row["cohort_id"] for row in selected]
        else:
            write("No populated cohort catalog: only full-history event export for all people is available.")
            cohort_ids = [None]
        keys = select_variables(workspace, database, read, write, plain)
        if not keys:
            return
        baseline_ready = None not in cohort_ids and database.capabilities()["baseline_anchors"]
        fmt = choose(["tabular", "events"], lambda value: "Tabular: exact baseline-day snapshot, one column per feature" if value == "tabular" else "Event stream: full history (prediction cutoffs must be applied downstream)", read, write, plain,
                     disabled=lambda value: "Requires populated cohorts and clinical baseline anchors" if value == "tabular" and not baseline_ready else "", message="Choose export format")
        if not fmt:
            return
        options = {}
        if fmt == "tabular":
            mode = choose(["snapshot", "latest-history"], lambda mode: "Exact baseline day: standard features only (default)" if mode == "snapshot" else "Configure prior history and optional derived columns", read, write, plain, message="Tabular configuration")
            if not mode:
                return
            options["tabular_mode"] = mode
            if mode == "latest-history":
                options["lookback_days"] = int(ask("Lookback in days (inclusive; must be positive)", "365", read, write, plain))
                derived = choose_many(list(HISTORY_FEATURES), lambda value: value, read, write, plain, message="Optional extra history columns (none keeps one source feature column)")
                options["history_features"] = derived
                policy = choose(["post-assessment", "strict-before"], lambda value: value, read, write, plain, message="Prediction-time availability policy")
                if not policy:
                    return
                options["availability_policy"] = policy
        else:
            scope = choose(["full-history", "baseline"], lambda value: "Full history: includes post-baseline events" if value == "full-history" else "Prediction baseline: apply availability mask and cutoff", read, write, plain, message="Event stream configuration")
            if not scope:
                return
            options["time_scope"] = scope
            domains = choose_many(list(DOMAINS.values()), lambda value: value, read, write, plain, message="Select event domains (all for all domains)")
            if not domains:
                return
            options["domains"] = domains
            if scope == "baseline":
                window = ask("History lookback days (blank uses all prior history)", read=read, write=write, plain=plain)
                options["event_lookback_days"] = int(window) if window else None
                policy = choose(["post-assessment", "strict-before"], lambda value: value, read, write, plain, message="Baseline availability policy")
                if not policy:
                    return
                options["event_availability_policy"] = policy
            options["date_start"] = ask("Optional calendar start (YYYY-MM-DD, blank for none)", read=read, write=write, plain=plain) or None
            options["date_end"] = ask("Optional calendar end (YYYY-MM-DD, blank for none)", read=read, write=write, plain=plain) or None
            options["include_metadata"] = confirm("Include source value, fact ID/table, site and baseline-relative timing?", read, write, plain)
        output = ask("DATA_DIR: dataset root", str(workspace.suggested_download_root()), read, write, plain, path=True).strip().strip('"')
        if not output:
            return
        write("Generating " + fmt + " data using " + str(len(resolve_variables(database, keys))) + " frozen source variables...")
        if fmt == "tabular":
            write("Default snapshots have no carry-forward or derived columns. New same-day treatment decisions and outcome-derived facts are held; source-role coverage is incomplete. No outcome labels/risk sets are generated.")
        else:
            write("Full-history streams may contain future/outcome information. Baseline scope applies the conservative availability mask; it does not create outcome labels or risk sets.")
            if selection_spec(keys)[1]:
                write("Consolidated presets select their raw source concepts for event streams; event rows are not collapsed into family columns.")
        from .datasets import cohort_paths
        for cohort in cohort_ids:
            directory, csv = cohort_paths(database, cohort, fmt)
            write("Output: " + text(Path(output) / (csv or directory)))
        if not confirm("Generate these protected datasets? Existing outputs will not be overwritten", read, write, plain, default=True):
            return
        workspace.set_download_root(output)
        result = export_dataset(database, output, cohort_ids, keys, fmt, **options)
        write("Export complete: " + str(result["rows"]) + " rows | " + text(output))


def reports_menu(workspace, read=input, write=print, plain=False):
    kind = choose(list(REPORTS), lambda value: REPORTS[value], read, write, plain, message="Choose a preconfigured report")
    if not kind:
        return
    with OmopDatabase(workspace.state["active_db"]) as database:
        write("Calculating report from the local database...")
        report = summary_report(database, kind)
        write("Report: " + REPORTS[kind] + " | " + report.get("status", "PASS"))
        for key in ("patients_by_site", "scope", "definition"):
            if key in report:
                write(key + ": " + text(report[key]))
        fields = {"inventory": ("tables", ["table", "rows"]), "cohorts": ("cohorts", ["cohort_id", "name", "patients"]),
                  "endpoints": ("endpoints", ["endpoint", "status", "site", "patients"]), "overlap": ("core", ["table", "concept_id", "concept_name"]),
                  "distributions": ("distributions", ["concept_id", "site", "unit_concept_id", "n", "mean", "median", "iqr", "min", "max"]),
                  "features": ("sets", ["name", "source_variable_count", "unavailable"]), "patients": ("patients", [])}
        table, columns = fields[kind]
        write(" | ".join(columns))
        if kind == "patients":
            write(str(report["patient_count"]) + " patient rows prepared. Patient-level records are saved to protected files, not printed in this menu.")
        else:
            for row in report.get(table, []):
                write(" | ".join(text(row.get(column, "")) for column in columns))
        if kind == "overlap":
            write("CORE: " + str(report["core_count"]) + "; two-site: " + str(report["two_site_count"]))
            write("Two-site variables: table | concept_id | concept_name | site_pair")
            for row in report["two_site"]:
                write(" | ".join(text(row[column]) for column in ("table", "concept_id", "concept_name", "site_pair")))
        if confirm("Save this report as JSON and CSV tables?", read, write, plain):
            output = ask("DATA_DIR: reports will be saved under reports/", str(workspace.suggested_download_root()), read, write, plain, path=True).strip().strip('"')
            if output:
                workspace.set_download_root(output)
                write_data_report(database, kind, output)
                write("Report saved: " + text(Path(output) / "reports" / (kind + ".txt")))


def variables_menu(workspace, read=input, write=print, plain=False):
    with OmopDatabase(workspace.state["active_db"]) as database:
        select_variables(workspace, database, read, write, plain, custom_only=True)
