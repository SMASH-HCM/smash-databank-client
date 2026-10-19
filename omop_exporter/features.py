"""Stable exact-variable groups shared by event and baseline exports."""
import json
from pathlib import Path
import re

from .database import FACTS
from .reports import overlap

PRESETS = {"core": "CORE (3-site)", "core+two-site": "CORE + two-site variables", "all": "ALL clinical variables",
           "ecg-derived": "ECG-labelled measurements (name filter)", "measurements": "All measurements", "conditions": "All conditions"}
PRESETS.update({"core-measurements": "CORE clinical measurements only", "minimal-measurements": "Eight starter clinical measurements (fixed concept list)",
                "two-site": "Two-site variables only", "core-consolidated": "CORE with mitral-regurgitation categories consolidated"})

# A small transparent starter list, not a validated clinical prediction score.
MINIMAL_MEASUREMENTS = (607590, 4099154, 4245997, 4152194, 4154790, 4108582, 3021917, 3026578)
MR_GRADES = {3654726: "mild", 3654727: "moderate", 3654728: "severe", 2000001130: "trace",
             2000001131: "trace-mild", 2000001132: "mild-moderate", 2000001133: "moderate-severe"}
MR_FAMILY = {"name": "mitral_regurgitation_grade", "table": "condition_occurrence", "categories": MR_GRADES,
             "version": 1, "policy": "Latest eligible date; conflicting grades on that date remain missing. Absence is unknown, never none/normal. Availability mask still applies."}


def selection_spec(selection):
    """Preserve explicitly requested family transformations through saved sets."""
    if isinstance(selection, dict):
        return selection["keys"], selection.get("families", [])
    if selection == "core-consolidated":
        return selection, [MR_FAMILY]
    return selection, []


def resolve_variables(database, selection="core"):
    if isinstance(selection, dict):
        selection = selection["keys"]
    if isinstance(selection, str):
        if selection not in PRESETS:
            raise ValueError("Unknown variable group: " + selection)
        if selection == "minimal-measurements":
            return [("measurement", cid) for cid in sorted(MINIMAL_MEASUREMENTS)]
        if selection in ("all", "measurements", "conditions", "ecg-derived"):
            rows = database.variables()
            if selection in ("measurements", "conditions"):
                table = "measurement" if selection == "measurements" else "condition_occurrence"
                rows = [row for row in rows if row["table"] == table]
            elif selection == "ecg-derived":
                pattern = r"\b(ecg|ekg|electrocard\w*|qrs|qtc)\b|\b(qt|pr|rr) interval\b"
                rows = [row for row in rows if row["table"] == "measurement" and re.search(pattern, row["concept_name"], re.I)]
        else:
            report = overlap(database)
            rows = report["two_site"] if selection == "two-site" else report["core"] + (report["two_site"] if selection == "core+two-site" else [])
            if selection == "core-measurements":
                rows = [row for row in rows if row["table"] == "measurement"]
        keys = {(row["table"], row["concept_id"]) for row in rows}
        if selection == "core-consolidated":
            keys.update(("condition_occurrence", cid) for cid in MR_GRADES)
    else:
        keys = set()
        try:
            for table, concept in selection:
                keys.add((str(table), int(concept)))
        except (TypeError, ValueError):
            raise ValueError("Variables must be (fact table, concept ID) pairs") from None
    allowed = {row[0] for row in FACTS}
    if not keys or any(table not in allowed or concept <= 0 for table, concept in keys):
        raise ValueError("Variable selection is empty or contains unsupported fact-table/concept pairs")
    return sorted(keys)


def variable_catalog(database):
    grouped = {}
    for row in database.variables():
        key = (row["table"], row["concept_id"])
        item = grouped.setdefault(key, {"table": key[0], "concept_id": key[1], "concept_name": row["concept_name"], "sites": []})
        item["sites"].append(row["site"])
    return [grouped[key] for key in sorted(grouped)]


def save_variable_set(path, database, selection, name="Custom variables"):
    keys = resolve_variables(database, selection)
    _, families = selection_spec(selection)
    names = database.concept_names()
    data = {"schema_version": 1, "name": str(name).strip() or "Custom variables", "release": database.release_metadata(),
            "variables": [{"table": table, "concept_id": cid, "concept_name": names.get(cid, "")} for table, cid in keys]}
    if families:
        data["families"] = families
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, allow_nan=False)
        handle.write("\n")
    return data


def load_variable_set(path):
    data = json.loads(Path(path).expanduser().read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or data.get("schema_version") != 1 or not isinstance(data.get("name"), str) or not isinstance(data.get("variables"), list):
        raise ValueError("Invalid saved variable-set schema")
    keys = []
    for row in data["variables"]:
        if not isinstance(row, dict) or not isinstance(row.get("table"), str) or type(row.get("concept_id")) is not int:
            raise ValueError("Saved variables require a fact table and integer concept_id")
        keys.append((row["table"], row["concept_id"]))
    data["keys"] = resolve_variables(None, keys)
    # Only the versioned built-in mapping is accepted; never infer equivalence by name.
    if data.get("families"):
        expected = json.loads(json.dumps([MR_FAMILY]))
        if data["families"] != expected:
            raise ValueError("Unsupported feature-family mapping; use the versioned built-in definition")
        data["families"] = [MR_FAMILY]
    return data
