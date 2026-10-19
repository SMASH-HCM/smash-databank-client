"""Add exact-day default examples and FLORENCE labels to an RC4 validation run."""
import argparse
from collections import Counter
from datetime import date
import json
from pathlib import Path
import re

from validate_release_examples import announce, verify_bundle
from smash_hcm_databank_client import __version__
from smash_hcm_databank_client.database import OmopDatabase, sha256
from smash_hcm_databank_client.features import load_variable_set
from smash_hcm_databank_client.output import write_csv, write_json
from smash_hcm_databank_client.reports import write_report
from smash_hcm_databank_client.tabular import export_wide


def label(value):
    return re.sub(r'\bshare\b','FLORENCE',str(value),flags=re.I)


def relocate(source, target, root):
    # Verify both absolute targets before any directory move; never overwrite.
    base=root.resolve()
    if base not in source.resolve().parents or base not in target.resolve().parents:
        raise ValueError('Directory move escapes the validation output')
    if source.is_symlink() or target.exists():
        raise ValueError('Directory move must have a regular source and new target')
    target.parent.mkdir(parents=True,exist_ok=True)
    source.rename(target)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    root=args.out
    summary=json.loads((root/'acceptance.json').read_text())
    previous=summary['examples']
    with OmopDatabase(args.db) as db:
        anchors={pid:(date.fromisoformat(str(day)[:10]),float(age)) for pid,day,age in db.connection.execute('SELECT person_id,baseline_date,baseline_age FROM smash_endpoint_censor') if day is not None and age is not None}
        by_id={row['cohort_id']:row for row in db.cohorts()}
        for row in previous:
            row.setdefault('source_cohort_name',row['cohort'])
            row['cohort']=label(row['cohort'])
            row['tabular_mode']='latest-history' if row['format']=='tabular' else 'full-history'
            old=row['directory']
            new=old.replace('-share-','-florence-')
            if new!=old:
                if (root/old).exists():
                    relocate(root/old,root/new,root)
                row['directory']=new
        for row in summary['ledger_audit']['cohorts']:
            row.update(by_id[row['cohort_id']])
        for pair in summary['ledger_audit']['split_overlap']:
            pair['left']=label(pair['left']);pair['right']=label(pair['right'])
        write_json(root/'audit/ledger_audit.json',summary['ledger_audit'])
        write_csv(root/'audit/cohort_baseline_coverage.csv',['cohort_id','name','source_name','patients','missing_or_invalid_baselines'],summary['ledger_audit']['cohorts'])
        write_csv(root/'audit/split_overlap.csv',['left','right','overlapping_people'],summary['ledger_audit']['split_overlap'])
        for kind in ('cohorts','inventory'):
            announce('Refreshing FLORENCE report labels: '+kind)
            relocate(root/'reports'/kind,root/'reports/archive-previous-layout'/kind,root)
            write_report(db,kind,root/'reports'/kind)
        cases=[('Rennes Training','core'),('Rennes Test','core'),('Tampere Training','core'),('Tampere Pilot','core'),
               ('Rennes Test','ecg-derived'),('Tampere All Patients','all'),('Rennes Training','custom'),('Rennes Test','custom')]
        current=[]
        for cohort,group in cases:
            output=root/'snapshots'/(cohort.lower().replace(' ','-')+'-'+group)
            keys=load_variable_set(root/'variable_sets'/(group+'.json'))['keys']
            announce('Exact-day snapshot: '+cohort+' | '+group)
            result=export_wide(db,output,cohort,keys)
            checks=verify_bundle(db,output,cohort,keys,'tabular',anchors)
            manifest=json.loads((output/'dataset_manifest.json').read_text())
            assert len(manifest['columns'])==len(keys)+4 and manifest['aggregation'].startswith('none')
            row={'format':'tabular','cohort':manifest['cohort_name'],'source_cohort_name':manifest['source_cohort_name'],'variables':group,
                 'directory':str(output.relative_to(root)).replace('\\','/'),'tabular_mode':'snapshot','availability_policy':'post-assessment','status':'PASS',
                 'rows':result['rows'],'feature_count':len(keys),'metadata_columns':4,'total_columns':len(keys)+4,'acceptance':checks}
            current.append(row)
            write_json(root/'snapshot_examples.json',current)
            announce(f"PASS | {result['rows']} people | {len(keys)} feature columns + 4 metadata columns | {checks['populated_cells']} populated cells")
        history=root/'history-examples/tampere-training-core-365d'
        keys=load_variable_set(root/'variable_sets/core.json')['keys']
        announce('Explicit opt-in history example: Tampere Training | 365 days')
        result=export_wide(db,history,'Tampere Training',keys,tabular_mode='latest-history',lookback_days=365)
        checks=verify_bundle(db,history,'Tampere Training',keys,'tabular',anchors)
        history_row={'format':'tabular','cohort':'Tampere Training','variables':'core','directory':'history-examples/tampere-training-core-365d','tabular_mode':'latest-history',
                     'lookback_days':365,'availability_policy':'post-assessment','status':'PASS','rows':result['rows'],'feature_count':len(keys),'metadata_columns':4,'total_columns':len(keys)+4,'acceptance':checks}
        results=previous+current+[history_row]
        assert sha256(args.db)==summary['database_sha256'],'Source changed'
        summary.update(exporter_version=__version__,examples=results,counts=dict(Counter(row['status'] for row in results)),default_tabular_mode='snapshot',source_unchanged=True)
        write_json(root/'acceptance.json',summary)
        write_json(root/'examples.json',results)
        previous_readme=(root/'README.md').read_text(encoding='utf-8')
        archive=root/'historical-controls-README.md'
        archive.write_text(previous_readme,encoding='utf-8')
        lines=['# RC4 validation: default exact-day snapshots','',
               'Patient-level outputs: keep this directory in protected storage. The source database was read-only and its SHA-256 remains unchanged.','',
               '## Default tabular contract','',
               '**One day, one selected feature per column.** data.csv contains person_id, site, cohort, snapshot_date, then the selected feature values. RC4 CORE is 37 table/concept pairs, so the main CSV has 41 columns: 37 features plus four metadata columns. It has no rolling/window means, previous-value/age columns, recency/count features, scaling, imputation or implicit carry-forward. Same-day conflicting values remain missing with a QC reason; they are not averaged. Detailed audit files are separate.','',
               'FLORENCE is the export label for source SHaRe cohorts. Original names and IDs remain in provenance, and PILOT is not relabelled as TEST. Baseline-day availability still follows the agreed post-assessment/pre-intervention mask; unclassified actions and outcome-derived information are held out.','',
               '## Current snapshot examples','', '| Cohort | Variables | People | Feature columns | Metadata columns | Total | CSV |','|---|---|---:|---:|---:|---:|---|']
        for row in current:
            lines.append('| '+' | '.join([row['cohort'],row['variables'],str(row['rows']),str(row['feature_count']),'4',str(row['total_columns']),'[data.csv]('+row['directory']+'/data.csv)'])+' |')
        lines+=['','The FLORENCE Training and Pilot tabular requests remain blocked by missing baselines (124 and 21 members respectively); no patients were silently dropped and no anchor was invented. Their full-history event examples are in exports/, using FLORENCE-labelled directories.','',
                '## Explicit opt-in history','',
                'Historical/as-of selection requires both --tabular-mode latest-history and a positive --lookback-days. [The 365-day Tampere example](history-examples/tampere-training-core-365d/data.csv) demonstrates that opt-in. Historical controls from the earlier run are retained under exports/ and indexed in examples.json; they are not the current default. Rolling/annual training landmarks and shifted prediction indexes remain a separate, explicitly configured risk-set workflow, not automatic snapshot features.','',
                '```powershell',
                'smash-hcm-databank-client export --db ./private/OMOP.db --format tabular --cohort "Rennes Training" --vars core --out <new-snapshot-directory>',
                'smash-hcm-databank-client export --db ./private/OMOP.db --format tabular --cohort "Tampere Training" --vars core --tabular-mode latest-history --lookback-days 365 --out <new-history-directory>',
                '```','',
                '## Findings requiring review','',
                '- 151 people have missing baseline dates/ages, all FLORENCE. There are 2,984 person rows but 2,978 SMASH All Patients cohort members; six people have no assignment to that cohort.',
                '- 152 missing censor dates and one dated OVERALL event after censor remain flagged. The observed-event protocol permits a flagged event after last clinical contact; review ascertainment rather than moving dates.',
                '- All Rennes measurements occur on the baseline day. Post-assessment exact-day snapshots retain eligible measurements; the old strict-before controls were almost empty.',
                '- Unitless numeric NYHA values are still held by the generic numeric unit rule: a feature-type limitation requiring a reviewed ordinal representation. Conflicting baseline blood-pressure values and mixed troponin units are also held, not averaged or converted.',
                '- ECG-labelled measurement examples for Rennes/Tampere may be empty/all-missing; this preset does not process adjacent ECG signals or encompass all ECG diagnoses.',
                '- CORE is shared concept/table presence, not proof of complete or clinically equivalent measurements. External imaging/ECG file availability was not verified in this database-only run.',
                '- No explicit release-version tag is embedded in RC4; the supplied filename provides that label. Full-ETL results__cohort mapping is supported by the updated exporter.','',
                'Reports are in reports/. Private actionable records are in audit/baseline_issues.csv, audit/people_outside_all_patients_cohort.csv and audit/events_after_censor.csv. Frozen variable lists are in variable_sets/. Each new snapshot has acceptance.json reconciled against source membership, values, dates and output hashes.','',
                'Use the [updated Windows application](application/omop-exporter-0.9.0-windows-amd64.zip), extracting its whole ZIP. Select RC4 with menu --db <database-path>. The patient-level datasets are feature-only; endpoint-specific eligibility, risk sets and outcome labels are not manufactured by this validation run.']
        (root/'README.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
        announce(json.dumps({'current_snapshots':len(current),'explicit_history_examples':1,'all_example_statuses':summary['counts'],'core_features':37,'core_csv_columns':41,'source_unchanged':True}))


if __name__=='__main__':
    main()
