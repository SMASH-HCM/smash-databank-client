import csv
import json
import sqlite3

from smash_hcm_databank_client.database import OmopDatabase
from smash_hcm_databank_client.tabular import export_wide
from smash_hcm_databank_client.cli import main


def records(path):
    with path.open() as handle:
        return list(csv.DictReader(handle))


def test_post_assessment_includes_day_measurement_but_never_future(omop_path, tmp_path):
    with sqlite3.connect(omop_path) as db:
        db.executescript("INSERT INTO measurement VALUES(90,1,10,'2021-01-01',99,NULL,8582); INSERT INTO measurement VALUES(91,1,10,'2021-01-02',1000,NULL,8582);")
    with OmopDatabase(omop_path) as db:
        export_wide(db, tmp_path / 'out', 1)
    assert records(tmp_path / 'out/data.csv')[0]['measurement__10'] == '99.0'
    manifest = json.loads((tmp_path / 'out/dataset_manifest.json').read_text())
    assert manifest['availability_policy'] == 'post-assessment'
    assert json.loads((tmp_path / 'out/availability_policy.json').read_text())['version'] == 'post-assessment-v1'


def test_same_day_new_actions_held_and_prior_treatment_retained(omop_path, tmp_path):
    with sqlite3.connect(omop_path) as db:
        db.executescript("CREATE TABLE drug_exposure (drug_exposure_id INTEGER,person_id INTEGER,drug_concept_id INTEGER,drug_exposure_start_date TEXT); INSERT INTO concept VALUES(900,'Established therapy'),(901,'New prescription'); INSERT INTO drug_exposure VALUES(1,1,900,'2020-01-01'),(2,1,901,'2021-01-01');")
    with OmopDatabase(omop_path) as db:
        export_wide(db, tmp_path / 'out', 1, [('drug_exposure',900),('drug_exposure',901)], tabular_mode='latest-history', lookback_days=1826)
    row = records(tmp_path / 'out/data.csv')[0]
    assert row['drug_exposure__900'] == '1' and row['drug_exposure__901'] == ''
    exclusions = records(tmp_path / 'out/availability_exclusions.csv')
    assert len(exclusions) == 1 and exclusions[0]['concept_id'] == '901'


def test_diagnostic_procedures_are_not_blanket_excluded(omop_path, tmp_path):
    with sqlite3.connect(omop_path) as db:
        db.executescript("CREATE TABLE procedure_occurrence (procedure_occurrence_id INTEGER,person_id INTEGER,procedure_concept_id INTEGER,procedure_date TEXT); INSERT INTO concept VALUES(4230911,'Echocardiography'),(4191948,'ICD implantation'); INSERT INTO procedure_occurrence VALUES(1,1,4230911,'2021-01-01'),(2,1,4191948,'2021-01-01');")
    with OmopDatabase(omop_path) as db:
        export_wide(db, tmp_path / 'out', 1, [('procedure_occurrence',4230911),('procedure_occurrence',4191948)])
    row = records(tmp_path / 'out/data.csv')[0]
    assert row['procedure_occurrence__4230911'] == '1' and row['procedure_occurrence__4191948'] == ''


def test_administrative_outcome_and_recommendation_features_held_even_before_day(omop_path, tmp_path):
    with sqlite3.connect(omop_path) as db:
        db.executescript("INSERT INTO concept VALUES(4083743,'Cause of death'),(2000001101,'ESC ICD recommendation category'); INSERT INTO observation VALUES(90,1,4083743,'2020-01-01','outcome'),(91,1,2000001101,'2020-01-01','decision');")
    with OmopDatabase(omop_path) as db:
        export_wide(db, tmp_path / 'out', 1, [('observation',4083743),('observation',2000001101)], tabular_mode='latest-history', lookback_days=1826)
    row = records(tmp_path / 'out/data.csv')[0]
    assert row['observation__4083743'] == '' and row['observation__2000001101'] == ''
    assert {r['reason'] for r in records(tmp_path / 'out/availability_exclusions.csv')} == {'administrative_outcome_or_decision_derived'}


def test_event_cli_cannot_be_mistaken_for_baseline_masked_export(omop_path, tmp_path, capsys):
    assert main(['export','--db',str(omop_path),'--format','events','--availability-policy','post-assessment','--out',str(tmp_path / 'out')]) == 2
    assert 'full history' in capsys.readouterr().err and not (tmp_path / 'out').exists()
