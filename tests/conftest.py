import os
import sqlite3
from pathlib import Path

import pytest

from smash_hcm_databank_client.database import OmopDatabase


@pytest.fixture(autouse=True)
def offline_menu_startup(monkeypatch):
    # Unit/workflow tests never contact the real server. Probe tests inject their
    # own opener into connectivity.probe_server and exercise the actual logic.
    monkeypatch.setattr("smash_hcm_databank_client.menu.probe_server", lambda: {"available": False, "detail": "Offline test"})
    # Existing workflow cases exercise individual menu actions. Startup update
    # networking/prompts are covered explicitly in test_updates.py.
    monkeypatch.setattr("smash_hcm_databank_client.menu.startup_updates", lambda *args, **kwargs: None)


def pytest_addoption(parser):
    parser.addoption("--omop-db", action="append", default=[], help="External OMOP SQLite path; repeat to test multiple releases. Or set OMOP_EXPORTER_TEST_DB.")


def pytest_generate_tests(metafunc):
    if "external_db_path" in metafunc.fixturenames:
        paths = metafunc.config.getoption("--omop-db")
        if not paths and os.environ.get("OMOP_EXPORTER_TEST_DB"):
            paths = [os.environ["OMOP_EXPORTER_TEST_DB"]]
        metafunc.parametrize("external_db_path", [Path(path) for path in paths], ids=[Path(path).name for path in paths])


@pytest.fixture
def omop_path(tmp_path):
    path = tmp_path / "OMOP.db"
    connection = sqlite3.connect(path)
    connection.executescript("""
        CREATE TABLE person (person_id INTEGER PRIMARY KEY, site TEXT);
        INSERT INTO person VALUES (1,'FLORENCE'),(2,'RENNES'),(3,'TAMPERE'),(4,'FLORENCE');
        CREATE TABLE concept (concept_id INTEGER PRIMARY KEY, concept_name TEXT);
        INSERT INTO concept VALUES (10,'Common numeric'),(11,'Pair numeric'),(12,'Single-site numeric'),(2000011000,'SMASH cohort membership: fixture');
        CREATE TABLE measurement (measurement_id INTEGER PRIMARY KEY,person_id INTEGER,measurement_concept_id INTEGER,measurement_date TEXT,value_as_number REAL,value_as_concept_id INTEGER,unit_concept_id INTEGER);
        INSERT INTO measurement VALUES (1,1,10,'2020-01-01',10,NULL,8582),(2,2,10,'2020-01-01',20,NULL,8582),(3,3,10,'2020-01-01',30,NULL,8582),(4,1,11,'2020-01-01',11,NULL,8582),(5,2,11,'2020-01-01',22,NULL,8582),(6,1,12,'2020-01-01',12,NULL,8582),(7,1,0,'2020-01-01',0,NULL,8582);
        CREATE TABLE condition_occurrence (condition_occurrence_id INTEGER PRIMARY KEY,person_id INTEGER,condition_concept_id INTEGER,condition_start_date TEXT);
        INSERT INTO condition_occurrence VALUES (1,1,10,'2020-01-01'),(2,3,10,'2020-01-01');
        CREATE TABLE observation (observation_id INTEGER PRIMARY KEY,person_id INTEGER,observation_concept_id INTEGER,observation_date TEXT,observation_source_value TEXT);
        INSERT INTO observation VALUES (1,1,2000011000,'2020-01-01','SMASH:cohort:fixture');
        CREATE TABLE cohort_definition (cohort_definition_id INTEGER PRIMARY KEY,cohort_definition_name TEXT);
        INSERT INTO cohort_definition VALUES (1,'FLORENCE-TRAIN'),(2,'RENNES-ALL'),(3,'TAMPERE-PILOT');
        CREATE TABLE cohort (cohort_definition_id INTEGER,subject_id INTEGER);
        INSERT INTO cohort VALUES (1,1),(1,4),(2,2),(3,3);
        CREATE TABLE smash_endpoint_censor (person_id INTEGER,baseline_date TEXT,baseline_age REAL);
        INSERT INTO smash_endpoint_censor VALUES (1,'2021-01-01',50),(2,'2021-01-01',60),(3,'2021-01-01',70),(4,'2021-01-01',40);
        CREATE TABLE smash_endpoint_event (person_id INTEGER,endpoint TEXT,status TEXT,event_date TEXT);
        INSERT INTO smash_endpoint_event VALUES (1,'OVERALL','positive','2022-01-01'),(2,'OVERALL','not_ascertained',NULL),(3,'OVERALL','not_ascertained',NULL),(4,'OVERALL','negative',NULL);
        CREATE TABLE smash_asset (asset_id TEXT,person_id INTEGER,relative_path TEXT,size_bytes INTEGER,sha256 TEXT);
    """)
    connection.close()
    return path


@pytest.fixture
def database(omop_path):
    with OmopDatabase(omop_path) as database:
        yield database
