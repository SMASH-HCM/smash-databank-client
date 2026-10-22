"""Validated transport manifest and explicit cohort/modality/group selection."""
import json
import re
from pathlib import Path

from .nextcloud import NextcloudError, remote_path

CURRENT_SCHEMA_VERSION = "1.0"


class ManifestError(NextcloudError):
    """A safe validation error, separate from transport/authentication failures."""


def schema_version(value):
    """Accept legacy 1 and dotted versions; compatibility is checked by fields.

    A newer number does not require a client release if the published catalogue
    still supplies the paths, byte sizes and stored-file SHA-256s we understand.
    """
    if type(value) not in (str, int, float):
        raise ManifestError("Manifest schema_version must be 1.0 or a newer numeric version")
    version = str(value).strip()
    if not re.fullmatch(r"(?:0|[1-9][0-9]{0,8})(?:\.(?:0|[1-9][0-9]{0,8})){0,2}", version):
        raise ManifestError("Manifest schema_version must be 1.0 or a newer numeric version")
    parts = [int(part) for part in version.split(".")]
    if parts[0] < 1:
        raise ManifestError("Manifest schemas older than 1.0 are unsupported")
    return version + ".0" if len(parts) == 1 else version


def normalized(value):
    return str(value).strip().casefold().replace("_", "-").replace(" ", "-")


def load_manifest(path):
    path = Path(path)
    if path.stat().st_size > 8 * 1024 * 1024:
        raise ManifestError("Manifest exceeds the 8 MiB limit")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (ValueError, UnicodeError):
        raise ManifestError("Manifest must be valid UTF-8 JSON") from None
    return validate_manifest(data)


def validate_manifest(data):
    if not isinstance(data, dict):
        raise ManifestError("Manifest must be a JSON object")
    version = schema_version(data.get("schema_version"))
    catalogue = "entries" in data
    if catalogue and "files" in data:
        raise ManifestError("Manifest must provide one catalogue: entries or files, not both")
    source = data.get("entries" if catalogue else "files")
    if not isinstance(source, list):
        raise ManifestError("Manifest needs a compatible entries or files list; a client update may be needed for a different layout")
    if str(data.get("hash_algorithm", "SHA-256")).upper().replace("-", "") != "SHA256":
        raise ManifestError("Manifest hashes must use SHA-256 of stored file bytes")
    database = data.get("database")
    if database is not None and (not isinstance(database, dict) or not isinstance(database.get("path"), str)):
        raise ManifestError("Manifest database reference needs a relative path")
    try:
        database_path = remote_path(database["path"]) if database is not None else None
    except NextcloudError as exc:
        raise ManifestError(str(exc)) from None
    if database is not None:
        if "size_bytes" in database and (type(database["size_bytes"]) is not int or database["size_bytes"] < 0):
            raise ManifestError("Manifest database size_bytes must be a nonnegative integer")
        if "sha256" in database and (not isinstance(database["sha256"], str) or not re.fullmatch(r"[a-fA-F0-9]{64}", database["sha256"])):
            raise ManifestError("Manifest database reference needs a valid SHA-256")
        database = {**database, **({"sha256": database["sha256"].lower()} if "sha256" in database else {})}
    release = data.get("release")
    if release is None and catalogue:
        # The databank inventory has no release field: label the catalogue from
        # its explicit database filename, or its generation date. Not a DB check.
        release = Path(database_path).stem if database_path else data.get("generated_utc")
    if not isinstance(release, str) or not release.strip():
        raise ManifestError("Manifest needs a release name, database filename or generation date")
    extra_directories = data.get("directories", [])
    if not isinstance(extra_directories, list) or any(not isinstance(item, dict) or item.get("type", "directory") != "directory" for item in extra_directories):
        raise ManifestError("Manifest directories must be a list of directory metadata records")
    seen, identities, files, directories = set(), set(), [], []
    for entry in source + [{**item, "type": "directory"} for item in extra_directories]:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise ManifestError("Each manifest entry needs a relative path")
        try:
            path = remote_path(entry["path"])
        except NextcloudError as exc:
            raise ManifestError(str(exc)) from None
        if not path or path in seen:
            raise ManifestError("Manifest entry paths must be nonempty and unique")
        seen.add(path)
        kind = entry.get("type", "file")
        if kind not in ("file", "directory"):
            raise ManifestError("Manifest entry type must be file or directory")
        if any(not isinstance(entry[key], str) for key in ("comment", "kind", "preprocessing", "role") if key in entry):
            raise ManifestError("Manifest comment/kind/preprocessing/role must be strings")
        if "preprocessing" in entry and not entry["preprocessing"].strip():
            raise ManifestError("Manifest preprocessing must be a nonempty string when supplied")
        if kind == "directory":
            # Optional metadata only; directory digests are not file checksums.
            directories.append({**entry, "path": path, "type": "directory"})
            continue
        size, checksum = entry.get("size_bytes"), entry.get("sha256")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise ManifestError("Each manifest entry needs a nonnegative integer size_bytes")
        if not isinstance(checksum, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", checksum):
            raise ManifestError("Each manifest entry needs a SHA-256 checksum")
        item = {**entry, "path": path, "sha256": checksum.lower()}
        if item.get("hash_scope") not in (None, "file_bytes", "full_file_bytes", "stored_file_bytes"):
            raise ManifestError("File SHA-256 must cover stored file bytes, not directory records")
        if path == database_path:
            if any(database.get(key, item[key]) != item[key] for key in ("size_bytes", "sha256")):
                raise ManifestError("Manifest database reference disagrees with its file size or SHA-256")
            item["kind"] = "database"
        if "artifact_id" in item:
            identity = item["artifact_id"]
            if not isinstance(identity, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,159}", identity) or identity in identities:
                raise ManifestError("Manifest artifact_id must be a unique stable identifier using letters, digits, dots, dashes or underscores")
            identities.add(identity)
        if "version" in item and (not isinstance(item["version"], str) or not item["version"].strip()):
            raise ManifestError("Manifest file version must be a nonempty string")
        for key in ("cohorts", "modalities", "variable_groups"):
            value = item.get(key, [])
            singular = {"cohorts": "cohort", "modalities": "modality"}.get(key)
            if singular and singular in item and not value:
                value = [item[singular]]
            if isinstance(value, str):
                value = [value]
            if not isinstance(value, list) or any(not isinstance(tag, str) or not tag.strip() for tag in value):
                raise ManifestError("Manifest selection tags must be strings or lists of nonempty strings")
            item[key] = value
        if "kind" in item and not isinstance(item["kind"], str):
            raise ManifestError("Manifest kind must be a string")
        if any(not isinstance(item[key], str) for key in ("representation", "format", "description", "split") if key in item):
            raise ManifestError("Manifest representation/format/description/split must be strings")
        files.append(item)
    if database_path is not None and not any(item["path"] == database_path for item in files):
        raise ManifestError("Manifest database reference is absent from the downloadable files")
    for item in files:
        if "kind" not in item:
            parents = [folder for folder in directories if folder.get("kind") and item["path"].startswith(folder["path"] + "/")]
            if parents:
                item["kind"] = max(parents, key=lambda folder: len(folder["path"]))["kind"]
    result = {key: value for key, value in data.items() if key != "entries"}
    result.update(schema_version=version, release=release.strip(), files=files)
    if catalogue:
        result["source_layout"] = "entries"
    if catalogue or "directories" in data:
        result["directories"] = directories
    return result


def is_database(entry):
    return normalized(entry.get("kind", "")) in {"database", "omop-database"}


def artifact_type(entry):
    """Classify published files, without manufacturing clinical cohort membership."""
    if is_database(entry):
        return "database"
    kind = normalized(entry.get("kind", ""))
    if kind in {"event-stream", "events", "event-export", "cohort-events"}:
        return "events"
    if kind in {"report", "summary-report", "cohort-summary"}:
        return "reports"
    if kind == "etl-output":
        return "etl"
    if kind == "curated-bundle":
        return "curated"
    if kind in {"clinical-data", "clinical-landmarks"}:
        return "tables"
    if kind == "dataset-file":
        return "other"  # Individual companion files remain browsable.
    path = entry["path"].casefold()
    # Legacy untagged catalogues: classify publication areas, never membership.
    if not kind and path.startswith("cohorts/"):
        return "reports"
    if not kind and path.startswith("smash-etl/"):
        return "etl"
    if kind in {"table", "tabular", "tabular-export", "csv", "training-table"} or path.endswith((".csv", ".csv.gz")):
        return "tables"
    representation = normalized(entry.get("representation", ""))
    if path.endswith(".zip") and entry["modalities"] and representation not in {"raw", "dicom", "raw-dicom"}:
        return "curated"
    return "other"


def select_downloads(manifest, category, cohorts=(), modality=None, variable_group=None, modalities=(), preprocessing=()):
    """OR across explicitly selected cohorts, AND with type/modality/variable set."""
    if category not in {"database", "tables", "events", "reports", "curated", "etl"}:
        raise NextcloudError("Choose database, tables, events, reports, curated data or ETL output")
    requested = {normalized(cohort) for cohort in cohorts}
    requested_types = {normalized(value) for value in modalities}
    if modality:
        requested_types.add(normalized(modality))
    result = []
    covered, covered_pairs = set(), set()
    for entry in manifest["files"]:
        if artifact_type(entry) != category:
            continue
        if preprocessing and normalized(entry.get("preprocessing", "unspecified")) not in {normalized(value) for value in preprocessing}:
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
