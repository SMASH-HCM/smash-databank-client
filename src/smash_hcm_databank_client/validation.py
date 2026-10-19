"""Layered integrity validation; unsupported capabilities are explicit."""
from .assets import validate_asset
from .database import FACTS, quote, sha256
from datetime import date


def validate_database(database, expected_sha256=None, required=(), asset_root=None):
    checks = []
    capabilities = database.capabilities()
    initial = database.path.stat()
    integrity = [row[0] for row in database.connection.execute("PRAGMA integrity_check")]
    checks.append({"check": "sqlite_integrity", "status": "PASS" if integrity == ["ok"] else "FAIL"})
    checks.append({"check": "person_schema", "status": "PASS" if capabilities["persons"] else "FAIL"})
    wal = database.path.with_name(database.path.name + "-wal")
    wal_bytes = wal.stat().st_size if wal.exists() else 0
    checks.append({"check": "standalone_snapshot", "status": "PASS" if wal_bytes == 0 else "FAIL",
                   "detail": "Nonempty WAL requires ETL snapshot finalization; exporter never checkpoints the source." if wal_bytes else "No WAL content"})
    digest = sha256(database.path)
    final = database.path.stat()
    unchanged = (initial.st_size, initial.st_mtime_ns) == (final.st_size, final.st_mtime_ns)
    checks.append({"check": "stable_file", "status": "PASS" if unchanged else "FAIL"})
    checks.append({"check": "expected_sha256", "status": "NOT_REQUESTED" if expected_sha256 is None else "PASS" if digest == expected_sha256.lower() else "FAIL"})
    for capability, available in capabilities.items():
        checks.append({"check": capability, "status": "PASS" if available else "FAIL" if capability in required else "UNSUPPORTED"})
    if capabilities["persons"]:
        person = quote(database.table("person", required=True))
        duplicate = database.connection.execute("SELECT count(*) FROM (SELECT person_id FROM " + person + " GROUP BY person_id HAVING person_id IS NULL OR count(*)>1)").fetchone()[0]
        checks.append({"check": "unique_person_ids", "status": "FAIL" if duplicate else "PASS", "invalid_groups": duplicate})
        for logical, concept, *_ in FACTS:
            table = database.table(logical)
            if table and {"person_id", concept}.issubset(database.columns(logical)):
                orphan = database.connection.execute("SELECT count(*) FROM " + quote(table) + " f LEFT JOIN " + person + " p ON p.person_id=f.person_id WHERE p.person_id IS NULL").fetchone()[0]
                checks.append({"check": logical + "_person_links", "status": "FAIL" if orphan else "PASS", "orphans": orphan})
        cohorts = database.table("cohort")
        if cohorts and "subject_id" in database.columns("cohort"):
            orphan = database.connection.execute("SELECT count(*) FROM " + quote(cohorts) + " c LEFT JOIN " + person + " p ON p.person_id=c.subject_id WHERE p.person_id IS NULL").fetchone()[0]
            checks.append({"check": "cohort_person_links", "status": "FAIL" if orphan else "PASS", "orphans": orphan})
        for logical, unique_columns in (("smash_endpoint_censor", ["person_id"]), ("smash_endpoint_event", ["person_id", "endpoint"])):
            table = database.table(logical)
            if not table or not set(unique_columns).issubset(database.columns(logical)):
                continue
            orphan = database.connection.execute("SELECT count(*) FROM " + quote(table) + " f LEFT JOIN " + person + " p ON p.person_id=f.person_id WHERE p.person_id IS NULL").fetchone()[0]
            duplicates = database.connection.execute("SELECT count(*) FROM (SELECT " + ",".join(map(quote, unique_columns)) + " FROM " + quote(table) + " GROUP BY " + ",".join(map(quote, unique_columns)) + " HAVING count(*)>1)").fetchone()[0]
            checks.append({"check": logical + "_person_links", "status": "FAIL" if orphan else "PASS", "orphans": orphan})
            checks.append({"check": logical + "_unique_keys", "status": "FAIL" if duplicates else "PASS", "duplicate_groups": duplicates})
        if capabilities["baseline_anchors"]:
            invalid, missing = 0, 0
            for day, age in database.connection.execute("SELECT baseline_date,baseline_age FROM " + quote(database.table("smash_endpoint_censor"))):
                if day is None or age is None:
                    missing += 1
                    continue
                try:
                    date.fromisoformat(str(day)[:10])
                    if not 0 <= float(age) <= 120:
                        raise ValueError()
                except (ValueError, TypeError):
                    invalid += 1
            checks.append({"check": "baseline_anchor_values", "status": "FAIL" if (missing or invalid) and "baseline_anchors" in required else "WARN" if missing or invalid else "PASS",
                           "missing_rows": missing, "invalid_rows": invalid, "detail": "Tabular exports reject selected people with missing/invalid baselines; no anchor is inferred."})
    if asset_root is None:
        checks.append({"check": "external_assets", "status": "NOT_REQUESTED"})
    elif not capabilities["asset_catalog"]:
        checks.append({"check": "external_assets", "status": "FAIL", "detail": "Database lacks populated smash_asset catalog; asset availability cannot be established."})
    else:
        table = quote(database.table("smash_asset"))
        columns = database.columns("smash_asset")
        selected = [name for name in ("asset_id", "relative_path", "size_bytes", "sha256") if name in columns]
        failed, total, unverified = 0, 0, 0
        for row in database.connection.execute("SELECT " + ",".join(map(quote, selected)) + " FROM " + table):
            total += 1
            record = dict(zip(selected, row))
            record = {key: value for key, value in record.items() if value is not None}
            try:
                result = validate_asset(asset_root, record)
                unverified += int(not result["checksum_verified"])
            except (OSError, ValueError, KeyError):
                failed += 1
        checks.append({"check": "external_assets", "status": "FAIL" if failed or unverified else "PASS", "expected_files": total,
                       "failed_files": failed, "files_without_expected_hash": unverified,
                       "scope": "Existence/readability, path containment, size and checksum; format and clinical acceptance not yet implemented."})
    latest = database.path.stat()
    if (initial.st_size, initial.st_mtime_ns) != (latest.st_size, latest.st_mtime_ns) or (wal.exists() and wal.stat().st_size):
        checks.append({"check": "stable_snapshot_at_completion", "status": "FAIL"})
    return {"status": "FAIL" if any(check["status"] == "FAIL" for check in checks) else "PASS",
            "release": database.release_metadata(), "database_sha256": digest, "checks": checks,
            "scope": "Technical database and requested file integrity; not clinical validation or a claim that unsupported components are present."}
