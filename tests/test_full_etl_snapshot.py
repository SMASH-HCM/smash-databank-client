import json
import sqlite3

import pytest

from smash_hcm_databank_client.database import OmopDatabase
from smash_hcm_databank_client.tabular import export_wide
from smash_hcm_databank_client.validation import validate_database


def full_layout(path, manifest=True):
    with sqlite3.connect(path) as db:
        db.executescript('ALTER TABLE cohort RENAME TO results__cohort; ALTER TABLE cohort_definition RENAME TO results__cohort_definition; CREATE TABLE cdm__cohort (cohort_definition_id INTEGER,subject_id INTEGER); CREATE TABLE cdm__cohort_definition (cohort_definition_id INTEGER,cohort_definition_name TEXT);')
        if manifest:
            db.execute('CREATE TABLE smash_export_metadata (key TEXT,value TEXT)')
            data = {"generated_utc": "2026-10-17T21:30:38+00:00", "scope": "Full ETL", "private": "private-source-path",
                    "tables": [{"source_schema": "results", "source_table": name, "sqlite_table": "results__" + name} for name in ("cohort", "cohort_definition")]}
            db.execute('INSERT INTO smash_export_metadata VALUES (?,?)', ('manifest', json.dumps(data)))


def test_full_etl_cohort_mapping_enables_real_baseline_workflow(omop_path, tmp_path):
    full_layout(omop_path)
    with OmopDatabase(omop_path) as database:
        assert database.table('cohort') == 'results__cohort'
        assert database.table('cohort_definition') == 'results__cohort_definition'
        assert database.capabilities()['cohorts'] and database.capabilities()['cohort_catalog']
        assert export_wide(database, tmp_path / 'out', 1)['rows'] == 2
        assert database.release_metadata() == {"generated_utc": "2026-10-17T21:30:38+00:00", "scope": "Full ETL"}


def test_results_role_comes_from_manifest_and_does_not_merge_cdm_cohorts(omop_path):
    full_layout(omop_path)
    with sqlite3.connect(omop_path) as writer:
        writer.execute('INSERT INTO cdm__cohort VALUES (999,1)')
        writer.execute('INSERT INTO cdm__cohort_definition VALUES (999,?)', ('Unrelated CDM cohort',))
    with OmopDatabase(omop_path) as database:
        assert {row['cohort_id'] for row in database.cohorts()} == {1, 2, 3}


def test_duplicate_full_etl_names_without_manifest_remain_ambiguous(omop_path):
    full_layout(omop_path, manifest=False)
    with OmopDatabase(omop_path) as database:
        with pytest.raises(ValueError, match='Ambiguous'):
            database.table('cohort')


def test_vocabulary_lookup_is_sparse_and_cached(omop_path):
    with sqlite3.connect(omop_path) as writer:
        writer.execute('INSERT INTO concept VALUES (999999,?)', ('Unused vocabulary concept',))
    with OmopDatabase(omop_path) as database:
        names = database.concept_names()
        assert names[10] == 'Common numeric' and 999999 not in names
        assert database.concept_names() is names


def test_incomplete_anchors_warn_and_fail_when_required(omop_path, tmp_path):
    with sqlite3.connect(omop_path) as writer:
        writer.execute('UPDATE smash_endpoint_censor SET baseline_date=NULL WHERE person_id=1')
    with OmopDatabase(omop_path) as database:
        result = validate_database(database)
        check = next(row for row in result['checks'] if row['check'] == 'baseline_anchor_values')
        assert check['status'] == 'WARN' and check['missing_rows'] == 1
        assert validate_database(database, required=['baseline_anchors'])['status'] == 'FAIL'
        with pytest.raises(ValueError, match='baseline'):
            export_wide(database, tmp_path / 'out', 1)
    assert not (tmp_path / 'out').exists()
