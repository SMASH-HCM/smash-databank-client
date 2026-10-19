import json
import sqlite3

import pytest

from omop_exporter.database import OmopDatabase, sha256
from omop_exporter.reports import inventory, overlap
from omop_exporter.validation import validate_database


def test_missing_database_is_not_created(tmp_path):
    path = tmp_path / "missing.db"
    with pytest.raises(FileNotFoundError):
        OmopDatabase(path)
    assert not path.exists()


def test_postgres_dump_is_rejected(tmp_path):
    path = tmp_path / "dump.db"
    path.write_bytes(b"PGDMP" + b"0" * 30)
    with pytest.raises(ValueError, match="not a SQLite"):
        OmopDatabase(path)


def test_database_is_read_only(database, omop_path):
    before = sha256(omop_path)
    with pytest.raises(sqlite3.OperationalError):
        database.connection.execute("DELETE FROM person")
    assert sha256(omop_path) == before


def test_inventory_directly_from_database_retains_empty_tables(database):
    result = inventory(database)
    assert result["patients_by_site"] == {"FLORENCE": 2, "RENNES": 1, "TAMPERE": 1}
    assert next(row for row in result["tables"] if row["table"] == "smash_asset")["rows"] == 0
    assert result["capabilities"]["baseline_anchors"]
    assert result["capabilities"]["endpoint_labels"]
    assert not result["capabilities"]["asset_catalog"]


def test_exact_overlap_is_table_specific_and_pairs_are_exclusive(database):
    result = overlap(database)
    assert result["core_count"] == 1
    assert result["two_site_count"] == 2
    assert result["two_site_counts"] == {"FLORENCE|RENNES": 1, "FLORENCE|TAMPERE": 1}
    assert result["core"][0]["table"] == "measurement"
    assert result["core"][0]["sites"]["FLORENCE"]["coverage"] == .5
    assert not any(row["concept_id"] in (0, 2000011000) for row in result["core"] + result["two_site"])


def test_cohort_discovery_preserves_pilot_role(database):
    assert database.cohort_id("florence_train") == 1
    assert database.cohort_id("3") == 3
    assert database.cohorts()[0]["patients"] == 2
    with pytest.raises(ValueError, match="Unknown or ambiguous"):
        database.cohort_id("tampere_test")


def test_valid_hash_and_partial_capabilities(database, omop_path):
    result = validate_database(database, sha256(omop_path))
    assert result["status"] == "PASS"
    assert next(row for row in result["checks"] if row["check"] == "asset_catalog")["status"] == "UNSUPPORTED"
    assert validate_database(database, "0" * 64)["status"] == "FAIL"
    assert validate_database(database, required=["asset_catalog"])["status"] == "FAIL"


def test_empty_study_tables_are_unsupported(omop_path):
    with sqlite3.connect(omop_path) as connection:
        connection.executescript("DELETE FROM cohort; DELETE FROM cohort_definition; DELETE FROM smash_endpoint_censor; DELETE FROM smash_endpoint_event;")
    with OmopDatabase(omop_path) as database:
        assert not database.capabilities()["cohorts"]
        assert not database.capabilities()["baseline_anchors"]
        assert validate_database(database, required=["cohorts"])["status"] == "FAIL"
        assert overlap(database)["core_count"] == 1


def test_orphan_fact_is_failure(omop_path):
    with sqlite3.connect(omop_path) as connection:
        connection.execute("INSERT INTO measurement VALUES (999,999,10,'2020-01-01',1,NULL,8582)")
    with OmopDatabase(omop_path) as database:
        result = validate_database(database)
        assert result["status"] == "FAIL"
        assert next(row for row in result["checks"] if row["check"] == "measurement_person_links")["orphans"] == 1


def test_generic_ids_do_not_silently_become_florence(tmp_path):
    path = tmp_path / "generic.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE person (person_id INTEGER)")
        connection.execute("INSERT INTO person VALUES (1)")
    with OmopDatabase(path) as database:
        assert database.person_sites() == {1: "UNKNOWN"}
        with pytest.raises(ValueError, match="known site"):
            overlap(database)


def test_conflicting_provenance_fails(omop_path):
    with sqlite3.connect(omop_path) as connection:
        connection.executescript("CREATE TABLE smash_fact_provenance (omop_table TEXT,fact_id INTEGER,site TEXT); INSERT INTO smash_fact_provenance VALUES ('person',1,'RENNES');")
    with OmopDatabase(omop_path) as database:
        with pytest.raises(ValueError, match="Conflicting"):
            database.person_sites()


def test_database_metadata_does_not_echo_private_sources(omop_path):
    with sqlite3.connect(omop_path) as connection:
        connection.execute("CREATE TABLE smash_release_metadata (key TEXT,value TEXT)")
        connection.execute("INSERT INTO smash_release_metadata VALUES (?,?)", ("build_manifest", json.dumps({"release": "fixture", "sources": ["private-person-path"]})))
    with OmopDatabase(omop_path) as database:
        assert database.release_metadata() == {"release": "fixture"}


def test_flattened_schema_snapshot(tmp_path):
    path = tmp_path / "flattened.db"
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE "cdm.person" (person_id INTEGER,site TEXT)')
        connection.execute('INSERT INTO "cdm.person" VALUES (1,\'FLORENCE\')')
    with OmopDatabase(path) as database:
        assert database.table("person") == "cdm.person"
        assert database.person_sites() == {1: "FLORENCE"}


def test_ambiguous_table_names_are_rejected(omop_path):
    with sqlite3.connect(omop_path) as connection:
        connection.execute('CREATE TABLE "cdm.person" (person_id INTEGER)')
    with OmopDatabase(omop_path) as database:
        with pytest.raises(ValueError, match="Ambiguous"):
            database.table("person")


def test_nonempty_wal_is_not_validated_as_standalone_release(omop_path):
    writer = sqlite3.connect(omop_path)
    try:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("INSERT INTO person VALUES (5,'FLORENCE')")
        writer.commit()
        with OmopDatabase(omop_path) as database:
            result = validate_database(database)
            assert result["status"] == "FAIL"
            assert next(row for row in result["checks"] if row["check"] == "standalone_snapshot")["status"] == "FAIL"
    finally:
        writer.close()


def test_requested_asset_validation_cannot_pass_without_catalog(database, tmp_path):
    result = validate_database(database, asset_root=tmp_path)
    assert result["status"] == "FAIL"
    assert next(row for row in result["checks"] if row["check"] == "external_assets")["status"] == "FAIL"


def test_embedded_assets_need_hashes_and_valid_bytes(omop_path, tmp_path):
    path = tmp_path / "signal.bin"
    path.write_bytes(b"synthetic signal")
    with sqlite3.connect(omop_path) as connection:
        connection.execute("INSERT INTO smash_asset VALUES (?,?,?,?,?)", ("fixture", 1, path.name, path.stat().st_size, sha256(path)))
    with OmopDatabase(omop_path) as database:
        assert validate_database(database, asset_root=tmp_path)["status"] == "PASS"
    path.write_bytes(b"changed")
    with OmopDatabase(omop_path) as database:
        assert validate_database(database, asset_root=tmp_path)["status"] == "FAIL"
    with sqlite3.connect(omop_path) as connection:
        connection.execute("UPDATE smash_asset SET size_bytes=NULL,sha256=NULL")
    with OmopDatabase(omop_path) as database:
        result = validate_database(database, asset_root=tmp_path)
        assert result["status"] == "FAIL"
        assert next(row for row in result["checks"] if row["check"] == "external_assets")["files_without_expected_hash"] == 1
