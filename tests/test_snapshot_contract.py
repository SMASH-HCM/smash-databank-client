import csv
import json
import sqlite3

import pytest

from omop_exporter.cli import main
from omop_exporter.database import OmopDatabase
from omop_exporter.tabular import export_wide


def rows(path):
    with path.open() as handle:
        return list(csv.DictReader(handle))


def test_default_snapshot_never_carries_earlier_measurement_forward(database, tmp_path):
    export_wide(database, tmp_path / 'out', 1, [('measurement',10)])
    records = rows(tmp_path / 'out/data.csv')
    assert all(row['measurement__10']=='' for row in records)
    assert list(records[0])==['person_id','site','cohort','snapshot_date','measurement__10']
    assert {row['snapshot_date'] for row in records}=={'2021-01-01'}
    manifest=json.loads((tmp_path / 'out/dataset_manifest.json').read_text())
    assert manifest['tabular_mode']=='snapshot' and manifest['lookback_days'] is None and not manifest['carry_forward']
    assert manifest['feature_count']==1 and manifest['feature_columns']==['measurement__10']


def test_snapshot_is_one_column_per_selected_concept_with_no_averaging(omop_path, tmp_path):
    with sqlite3.connect(omop_path) as db:
        db.executescript("INSERT INTO measurement VALUES(80,1,10,'2021-01-01',20,NULL,8582),(81,1,10,'2021-01-01',40,NULL,8582),(82,1,11,'2021-01-01',7,NULL,8582);")
    with OmopDatabase(omop_path) as db:
        export_wide(db,tmp_path/'out',1,[('measurement',10),('measurement',11)])
    record=rows(tmp_path/'out/data.csv')[0]
    assert len(record)==6 and record['measurement__10']=='' and record['measurement__11']=='7.0'
    assert not any('mean' in field or 'previous' in field or 'recency' in field for field in record)


def test_history_requires_explicit_mode_and_window(database, tmp_path):
    with pytest.raises(ValueError,match='explicit latest-history'):
        export_wide(database,tmp_path/'bad',1,lookback_days=1826)
    with pytest.raises(ValueError,match='explicit positive'):
        export_wide(database,tmp_path/'bad',1,tabular_mode='latest-history')
    export_wide(database,tmp_path/'history',1,tabular_mode='latest-history',lookback_days=1826)
    assert rows(tmp_path/'history/data.csv')[0]['measurement__10']=='10.0'
    assert json.loads((tmp_path/'history/dataset_manifest.json').read_text())['carry_forward']


def test_florence_label_retains_source_name_and_memberships(omop_path,tmp_path):
    with sqlite3.connect(omop_path) as db:
        db.execute("UPDATE cohort_definition SET cohort_definition_name='SHaRe Training' WHERE cohort_definition_id=1")
    with OmopDatabase(omop_path) as db:
        cohort=db.cohorts()[0]
        assert cohort['name']=='FLORENCE Training' and cohort['source_name']=='SHaRe Training'
        assert db.cohort_id('FLORENCE-TRAIN')==db.cohort_id('SHaRe Training')==1
        export_wide(db,tmp_path/'out','FLORENCE-TRAIN')
    manifest=json.loads((tmp_path/'out/dataset_manifest.json').read_text())
    assert manifest['cohort_name']=='FLORENCE Training' and manifest['source_cohort_name']=='SHaRe Training'
    assert {row['cohort'] for row in rows(tmp_path/'out/data.csv')}=={'FLORENCE Training'}
    assert len(rows(tmp_path/'out/data.csv'))==2


def test_cli_default_snapshot_and_explicit_history_are_distinct(omop_path,tmp_path):
    args=['export','--db',str(omop_path),'--format','tabular','--cohort','FLORENCE-TRAIN']
    assert main(args+['--out',str(tmp_path/'snapshot')])==0
    assert main(args+['--tabular-mode','latest-history','--lookback-days','1826','--out',str(tmp_path/'history')])==0
    assert rows(tmp_path/'snapshot/data.csv')[0]['measurement__10']==''
    assert rows(tmp_path/'history/data.csv')[0]['measurement__10']=='10.0'
