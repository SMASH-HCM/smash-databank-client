"""Validated transport manifest and explicit cohort/modality/group selection."""
import json
import re
from pathlib import Path

from .nextcloud import NextcloudError, remote_path


def normalized(value):
    return str(value).strip().casefold().replace("_", "-").replace(" ", "-")


def load_manifest(path):
    path = Path(path)
    if path.stat().st_size > 8 * 1024 * 1024:
        raise NextcloudError("Manifest exceeds the 8 MiB limit")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (ValueError, UnicodeError):
        raise NextcloudError("Manifest must be valid UTF-8 JSON") from None
    return validate_manifest(data)


def validate_manifest(data):
    if not isinstance(data, dict) or type(data.get("schema_version")) is not int or data.get("schema_version") != 1:
        raise NextcloudError("Manifest schema_version must be 1")
    if not isinstance(data.get("release"), str) or not data["release"].strip():
        raise NextcloudError("Manifest needs a release name")
    if not isinstance(data.get("files"), list):
        raise NextcloudError("Manifest files must be a list")
    seen, identities, files = set(), set(), []
    for entry in data["files"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise NextcloudError("Each manifest file needs a relative path")
        path = remote_path(entry["path"])
        if not path or path in seen:
            raise NextcloudError("Manifest file paths must be nonempty and unique")
        seen.add(path)
        size, checksum = entry.get("size_bytes"), entry.get("sha256")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise NextcloudError("Each manifest file needs a nonnegative integer size_bytes")
        if not isinstance(checksum, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", checksum):
            raise NextcloudError("Each manifest file needs a SHA-256 checksum")
        item = {**entry, "path": path, "sha256": checksum.lower()}
        if "artifact_id" in item:
            identity = item["artifact_id"]
            if not isinstance(identity, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,159}", identity) or identity in identities:
                raise NextcloudError("Manifest artifact_id must be a unique stable identifier using letters, digits, dots, dashes or underscores")
            identities.add(identity)
        if "version" in item and (not isinstance(item["version"], str) or not item["version"].strip()):
            raise NextcloudError("Manifest file version must be a nonempty string")
        for key in ("cohorts", "modalities", "variable_groups"):
            value = item.get(key, [])
            singular = {"cohorts": "cohort", "modalities": "modality"}.get(key)
            if singular and singular in item and not value:
                value = [item[singular]]
            if isinstance(value, str):
                value = [value]
            if not isinstance(value, list) or any(not isinstance(tag, str) or not tag.strip() for tag in value):
                raise NextcloudError("Manifest selection tags must be strings or lists of nonempty strings")
            item[key] = value
        if "kind" in item and not isinstance(item["kind"], str):
            raise NextcloudError("Manifest kind must be a string")
        if any(not isinstance(item[key], str) for key in ("representation", "format", "description", "split") if key in item):
            raise NextcloudError("Manifest representation/format/description/split must be strings")
        files.append(item)
    return {**data, "files": files}


def is_database(entry):
    return normalized(entry.get("kind", "")) in {"database", "omop-database"}


def artifact_type(entry):
    """Classify published files, without manufacturing clinical cohort membership."""
    if is_database(entry):
        return "database"
    kind = normalized(entry.get("kind", ""))
    path = entry["path"].casefold()
    if kind in {"table", "tabular", "tabular-export", "csv", "training-table"} or path.endswith((".csv", ".csv.gz")):
        return "tables"
    representation = normalized(entry.get("representation", ""))
    if path.endswith(".zip") and entry["modalities"] and representation not in {"raw", "dicom", "raw-dicom"}:
        return "curated"
    return "other"


def select_downloads(manifest, category, cohorts=(), modality=None, variable_group=None, modalities=()):
    """OR across explicitly selected cohorts, AND with type/modality/variable set."""
    if category not in {"database", "tables", "curated"}:
        raise NextcloudError("Choose database, tables or curated data")
    requested = {normalized(cohort) for cohort in cohorts}
    requested_types = {normalized(value) for value in modalities}
    if modality:
        requested_types.add(normalized(modality))
    result = []
    covered, covered_pairs = set(), set()
    for entry in manifest["files"]:
        if artifact_type(entry) != category:
            continue
        matching_types = requested_types & {normalized(tag) for tag in entry["modalities"]}
        if requested_types and not matching_types:
            continue
        if variable_group and normalized(variable_group) not in {normalized(tag) for tag in entry["variable_groups"]}:
            continue
        matching = requested & {normalized(tag) for tag in entry["cohorts"]}
        if requested and not matching:
            continue
        covered.update(matching)
        covered_pairs.update((cohort, kind) for cohort in matching for kind in matching_types)
        result.append(entry)
    missing = requested - covered
    if missing:
        raise NextcloudError("No matching published files for: " + ", ".join(sorted(missing)))
    missing_pairs = {(cohort, kind) for cohort in requested for kind in requested_types} - covered_pairs
    if missing_pairs:
        raise NextcloudError("No matching published files for: " + ", ".join(cohort + "/" + kind for cohort, kind in sorted(missing_pairs)))
    return result


def select_files(manifest, cohort=None, modality=None, variable_group=None, databases=False):
    result = []
    for entry in manifest["files"]:
        database = is_database(entry)
        if databases and not database:
            continue
        if not databases and database and (cohort or modality or variable_group):
            continue
        filters = ((cohort, "cohorts"), (modality, "modalities"), (variable_group, "variable_groups"))
        if any(value and normalized(value) not in {normalized(tag) for tag in entry[key]} for value, key in filters):
            continue
        result.append(entry)
    return result
