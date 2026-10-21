"""Recognize database artifacts without opening dumps as queryable databases."""
from pathlib import Path
import re

from .database import OmopDatabase, sha256
from .nextcloud import NextcloudError


def database_format(path):
    with Path(path).open("rb") as stream:
        header = stream.read(4096)
    if header.startswith(b"PGDMP"):
        if len(header) < 12:
            raise NextcloudError("PostgreSQL dump header is truncated")
        return "postgres-custom"
    if header.lstrip(b"\xef\xbb\xbf\r\n \t").startswith(b"--\n-- PostgreSQL database dump") or header.lstrip(b"\xef\xbb\xbf\r\n \t").startswith(b"--\r\n-- PostgreSQL database dump"):
        return "postgres-sql"
    if header.startswith(b"SQLite format 3\x00"):
        return "sqlite"  # Explicit compatibility with earlier local snapshots.
    raise NextcloudError("Unrecognized database artifact; expected a PostgreSQL pg_dump archive (PGDMP) or SQL dump")


def inspect_database(path):
    kind = database_format(path)
    if kind == "sqlite":
        with OmopDatabase(path) as database:
            if not database.capabilities()["persons"]:
                raise NextcloudError("This file does not contain an OMOP person table")
    return kind


def validate_dump(path, expected_sha256=None, expected_size=None):
    """Validate artifact bytes, never claim that a signature proves restoreability."""
    if expected_sha256 is not None and not re.fullmatch(r"[a-fA-F0-9]{64}", expected_sha256):
        raise NextcloudError("Expected SHA-256 must contain 64 hexadecimal characters")
    path = Path(path)
    initial = path.stat()
    kind = database_format(path)
    if not kind.startswith("postgres-"):
        raise NextcloudError("Expected a PostgreSQL dump")
    digest = sha256(path)
    final = path.stat()
    checks = [
        {"check": "postgres_dump_signature", "status": "PASS"},
        {"check": "stable_file", "status": "PASS" if (initial.st_size, initial.st_mtime_ns) == (final.st_size, final.st_mtime_ns) else "FAIL"},
        {"check": "expected_sha256", "status": "NOT_REQUESTED" if expected_sha256 is None else "PASS" if digest == expected_sha256.lower() else "FAIL"},
        {"check": "expected_size", "status": "NOT_REQUESTED" if expected_size is None else "PASS" if final.st_size == expected_size else "FAIL"},
        {"check": "restored_omop_schema", "status": "NOT_CHECKED", "detail": "Restore into PostgreSQL before querying OMOP tables or testing clinical completeness."},
    ]
    return {"status": "FAIL" if any(check["status"] == "FAIL" for check in checks) else "PASS", "database_format": kind,
            "database_sha256": digest, "checks": checks,
            "scope": "Dump signature and file integrity only; no restore, OMOP schema validation or clinical validation was performed."}
