"""Read-only OMOP SQLite access and capability discovery.

Clinical inputs are database tables, never WP2 reports or source CSVs.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

SITES = ("FLORENCE", "RENNES", "TAMPERE")
# Logical table, target concept, date, numeric, categorical, unit, source, fact ID.
FACTS = (
    ("condition_occurrence", "condition_concept_id", "condition_start_date", None, None, None, "condition_source_value", "condition_occurrence_id"),
    ("measurement", "measurement_concept_id", "measurement_date", "value_as_number", "value_as_concept_id", "unit_concept_id", "measurement_source_value", "measurement_id"),
    ("observation", "observation_concept_id", "observation_date", "value_as_number", "value_as_concept_id", "unit_concept_id", "observation_source_value", "observation_id"),
    ("procedure_occurrence", "procedure_concept_id", "procedure_date", None, None, None, "procedure_source_value", "procedure_occurrence_id"),
    ("drug_exposure", "drug_concept_id", "drug_exposure_start_date", None, None, None, "drug_source_value", "drug_exposure_id"),
    ("device_exposure", "device_concept_id", "device_exposure_start_date", None, None, None, "device_source_value", "device_exposure_id"),
)


def quote(name):
    return '"' + name.replace('"', '""') + '"'


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class OmopDatabase:
    def __init__(self, path):
        self.path = Path(path).expanduser().resolve(strict=True)
        if not self.path.is_file():
            raise ValueError("Database must be a regular SQLite file")
        with self.path.open("rb") as handle:
            if handle.read(16) != b"SQLite format 3\x00":
                raise ValueError("Input is not a SQLite database; PostgreSQL dumps use the optional legacy workflow")
        self.connection = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)
        try:
            self.connection.execute("PRAGMA query_only=ON")
            self.connection.execute("BEGIN")
            self.objects = dict(self.connection.execute(
                "SELECT name,type FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%'"))
            self._sites = None
            self._variables = None
            self._names = None
            self._export = None
        except Exception:
            self.connection.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.connection.close()

    def table(self, name, required=False):
        # Also support flattened schema-qualified SQLite snapshots.
        candidates = [name] + [prefix + separator + name for prefix in ("cdm", "results", "vocabulary", "smash_cdm") for separator in ("_", ".", "__")]
        matches = [candidate for candidate in candidates if candidate in self.objects]
        if len(matches) > 1:
            # The full ETL flattens duplicate CDM/results relation names with __.
            # Use the embedded source-schema map to identify analytical cohorts;
            # do not infer roles from row counts or silently merge memberships.
            if name in ("cohort", "cohort_definition"):
                mapped = [row.get("sqlite_table") for row in self.export_metadata().get("tables", [])
                          if isinstance(row, dict) and row.get("source_schema") == "results" and row.get("source_table") == name and row.get("sqlite_table") in matches]
                if len(mapped) == 1:
                    return mapped[0]
            raise ValueError("Ambiguous database table: " + name)
        if not matches and required:
            raise ValueError("Database lacks required table: " + name)
        return matches[0] if matches else None

    def columns(self, name):
        table = self.table(name)
        if not table:
            return set()
        return {row[1] for row in self.connection.execute("PRAGMA table_info(" + quote(table) + ")")}

    def count(self, name):
        table = self.table(name)
        return self.connection.execute("SELECT count(*) FROM " + quote(table)).fetchone()[0] if table else 0

    def capabilities(self):
        def has(name, fields):
            return set(fields).issubset(self.columns(name))
        return {
            "persons": has("person", ["person_id"]),
            "concept_names": has("concept", ["concept_id", "concept_name"]),
            "cohorts": has("cohort", ["subject_id", "cohort_definition_id"]) and self.count("cohort") > 0,
            "cohort_catalog": has("cohort_definition", ["cohort_definition_id", "cohort_definition_name"]) and self.count("cohort_definition") > 0,
            "endpoint_labels": has("smash_endpoint_event", ["person_id", "endpoint", "status"]) and self.count("smash_endpoint_event") > 0,
            "baseline_anchors": has("smash_endpoint_censor", ["person_id", "baseline_date", "baseline_age"]) and self.count("smash_endpoint_censor") > 0,
            "asset_catalog": has("smash_asset", ["asset_id", "person_id", "relative_path"]) and self.count("smash_asset") > 0,
            "image_occurrences": has("image_occurrence", ["person_id", "local_path"]) and self.count("image_occurrence") > 0,
        }

    def release_metadata(self):
        table = self.table("smash_release_metadata")
        if not table or not {"key", "value"}.issubset(self.columns("smash_release_metadata")):
            data = self.export_metadata()
            return {key: data[key] for key in ("release", "scope", "generated_utc") if key in data}
        row = self.connection.execute("SELECT value FROM " + quote(table) + " WHERE key=?", ("build_manifest",)).fetchone()
        if not row:
            return {}
        try:
            data = json.loads(row[0])
        except (ValueError, TypeError):
            return {"metadata_error": "build_manifest is not valid JSON"}
        if not isinstance(data, dict):
            return {"metadata_error": "build_manifest must be an object"}
        # Do not echo patient/source paths or private source-row audit lists.
        return {key: data[key] for key in ("release", "scope", "generated_utc") if key in data}

    def export_metadata(self):
        """Read the full ETL's embedded mapping, without exposing private fields."""
        if self._export is None:
            self._export = {}
            if "smash_export_metadata" in self.objects:
                columns = {row[1] for row in self.connection.execute('PRAGMA table_info("smash_export_metadata")')}
                if {"key", "value"}.issubset(columns):
                    row = self.connection.execute('SELECT value FROM "smash_export_metadata" WHERE key=?', ("manifest",)).fetchone()
                    if row:
                        try:
                            data = json.loads(row[0])
                            if isinstance(data, dict):
                                self._export = data
                        except (TypeError, ValueError):
                            pass
        return self._export

    def person_sites(self):
        if self._sites is not None:
            return self._sites
        person = self.table("person", required=True)
        if "person_id" not in self.columns("person"):
            raise ValueError("person lacks person_id")
        columns = self.columns("person")
        sites = {}
        if "site" in columns:
            sites = {pid: str(site or "").upper() for pid, site in self.connection.execute("SELECT person_id,site FROM " + quote(person))}
        provenance = self.table("smash_fact_provenance")
        if provenance and {"omop_table", "fact_id", "site"}.issubset(self.columns("smash_fact_provenance")):
            for pid, site, distinct in self.connection.execute(
                "SELECT fact_id,min(upper(site)),count(DISTINCT upper(site)) FROM " + quote(provenance) + " WHERE lower(omop_table)='person' GROUP BY fact_id"):
                if distinct > 1 or (pid in sites and sites[pid] and sites[pid] != site):
                    raise ValueError("Conflicting person/site provenance")
                sites[pid] = site or "UNKNOWN"
        source = self.table("cdm_source")
        is_smash = self.table("smash_release_metadata") is not None
        if source and "cdm_source_name" in self.columns("cdm_source"):
            is_smash = is_smash or any("SMASH" in str(row[0]).upper() for row in self.connection.execute("SELECT cdm_source_name FROM " + quote(source)))
        result = {}
        for (pid,) in self.connection.execute("SELECT person_id FROM " + quote(person)):
            site = sites.get(pid)
            if not site and is_smash:
                site = "FLORENCE" if 1 <= pid <= 99999999 else "RENNES" if 100000000 <= pid <= 199999999 else "TAMPERE" if 500000000 <= pid <= 599999999 else "UNKNOWN"
            result[pid] = site if site in SITES else "UNKNOWN"
        self._sites = result
        return result

    def cohorts(self):
        table = self.table("cohort_definition")
        if not table or not {"cohort_definition_id", "cohort_definition_name"}.issubset(self.columns("cohort_definition")):
            return []
        memberships = self.table("cohort")
        counts = {}
        if memberships and {"subject_id", "cohort_definition_id"}.issubset(self.columns("cohort")):
            counts = dict(self.connection.execute("SELECT cohort_definition_id,count(DISTINCT subject_id) FROM " + quote(memberships) + " GROUP BY cohort_definition_id"))
        return [{"cohort_id": cid, "name": re.sub(r"\bshare\b", "FLORENCE", str(name), flags=re.I), "source_name": name, "patients": counts.get(cid, 0)} for cid, name in self.connection.execute(
            "SELECT cohort_definition_id,cohort_definition_name FROM " + quote(table) + " ORDER BY cohort_definition_id")]

    def cohort_id(self, selector):
        if not self.capabilities()["cohorts"]:
            raise ValueError("Database lacks populated cohort memberships")
        def normalized(value):
            value = str(value).casefold().replace("_", "-").replace(" ", "-")
            return re.sub(r"-training$", "-train", re.sub(r"-all-patients$", "-all", value))
        matches = [item["cohort_id"] for item in self.cohorts() if str(item["cohort_id"]) == str(selector) or normalized(selector) in (normalized(item["name"]), normalized(item["source_name"]))]
        if len(matches) != 1:
            raise ValueError("Unknown or ambiguous cohort; use cohorts list and its canonical name or ID")
        return matches[0]

    def concept_names(self):
        if self._names is not None:
            return self._names
        table = self.table("concept")
        if not table or not {"concept_id", "concept_name"}.issubset(self.columns("concept")):
            return {}
        # Full releases contain millions of vocabulary concepts. Resolve only
        # clinically referenced IDs and cache within this read-only snapshot.
        parts = []
        for logical, concept, *_ in FACTS:
            if concept in self.columns(logical):
                parts.append("SELECT DISTINCT " + quote(concept) + " FROM " + quote(self.table(logical)) + " WHERE " + quote(concept) + ">0")
        self._names = dict(self.connection.execute("SELECT concept_id,concept_name FROM " + quote(table) + " WHERE concept_id IN (" + " UNION ".join(parts) + ")")) if parts else {}
        return self._names

    def variables(self):
        if self._variables is not None:
            return self._variables
        sites, names = self.person_sites(), self.concept_names()
        result = []
        for logical, concept, *_ in FACTS:
            table = self.table(logical)
            if not table or not {"person_id", concept}.issubset(self.columns(logical)):
                continue
            grouped = defaultdict(lambda: Counter(facts=0, patients=0))
            for pid, cid, facts in self.connection.execute(
                "SELECT person_id," + quote(concept) + ",count(*) FROM " + quote(table) + " WHERE " + quote(concept) + ">0 GROUP BY person_id," + quote(concept)):
                if names.get(cid, "").startswith("SMASH cohort membership:"):
                    continue
                site = sites.get(pid, "UNKNOWN")
                grouped[(cid, site)]["facts"] += facts
                grouped[(cid, site)]["patients"] += 1
            for (cid, site), counts in sorted(grouped.items()):
                result.append({"table": logical, "concept_id": cid, "concept_name": names.get(cid, ""), "site": site, **counts})
        self._variables = result
        return result
