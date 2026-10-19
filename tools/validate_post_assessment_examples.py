"""Extend an existing release validation with the agreed baseline-day protocol."""
import argparse
from collections import Counter
import json
from pathlib import Path

from validate_release_examples import announce, read_csv, verify_bundle
from omop_exporter import __version__
from omop_exporter.database import OmopDatabase, sha256
from omop_exporter.features import load_variable_set
from omop_exporter.output import write_csv, write_json
from omop_exporter.tabular import export_wide
from datetime import date


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True, help='Existing validation directory')
    args = parser.parse_args()
    root = args.out
    summary = json.loads((root / 'acceptance.json').read_text())
    results = summary['examples']
    with OmopDatabase(args.db) as db:
        anchors = {}
        for pid, day, age in db.connection.execute('SELECT person_id,baseline_date,baseline_age FROM smash_endpoint_censor'):
            if day is not None and age is not None:
                anchors[pid] = (date.fromisoformat(str(day)[:10]), float(age))
        announce('Reconcile existing exports against source values and latest eligible dates...')
        for row in results:
            if row['status'] != 'PASS':
                continue
            output = root / row['directory']
            manifest = json.loads((output / 'dataset_manifest.json').read_text())
            keys = load_variable_set(output / 'variable_set.json')['keys']
            row['acceptance'] = verify_bundle(db, output, row['cohort'], keys, row['format'], anchors)
            row['availability_policy'] = manifest.get('availability_policy', 'strict-before') if row['format'] == 'tabular' else 'full-history'
            announce('Source reconciliation PASS: ' + output.name)
        timing = db.connection.execute('SELECT a.site,count(*),sum(substr(m.measurement_date,1,10)<substr(a.baseline_date,1,10)),sum(substr(m.measurement_date,1,10)=substr(a.baseline_date,1,10)),sum(substr(m.measurement_date,1,10)>substr(a.baseline_date,1,10)),sum(a.baseline_date IS NULL) FROM measurement m JOIN smash_endpoint_censor a ON a.person_id=m.person_id GROUP BY a.site').fetchall()
        fields = ['site','total','before_baseline','on_baseline','after_baseline','missing_anchor']
        write_csv(root / 'audit/measurement_timing.csv', fields, [dict(zip(fields, row)) for row in timing])
        query = 'SELECT e.person_id,a.site,e.endpoint,e.status,e.event_date,a.censor_date FROM smash_endpoint_event e JOIN smash_endpoint_censor a ON a.person_id=e.person_id WHERE e.event_date IS NOT NULL AND a.censor_date IS NOT NULL AND substr(e.event_date,1,10)>substr(a.censor_date,1,10)'
        fields = ['person_id','site','endpoint','status','event_date','censor_date']
        after_censor = [dict(zip(fields, row)) for row in db.connection.execute(query)]
        write_csv(root / 'audit/events_after_censor.csv', fields, after_censor)
        missing_censor = db.connection.execute('SELECT count(*) FROM smash_endpoint_censor WHERE censor_date IS NULL').fetchone()[0]
        summary['ledger_audit']['missing_censor_dates'] = missing_censor
        summary['ledger_audit']['dated_events_after_censor'] = len(after_censor)
        cases = [('Rennes Training','core'),('Rennes Test','core'),('Tampere Training','core'),('Tampere Pilot','core'),
                 ('Rennes Test','ecg-derived'),('Tampere All Patients','all'),('Rennes Training','custom'),('Rennes Test','custom')]
        for cohort, group in cases:
            number = len(results) + 1
            folder = f'{number:02d}-postassessment-' + cohort.lower().replace(' ','-') + '-' + group
            output = root / 'exports' / folder
            keys = load_variable_set(root / 'variable_sets' / (group + '.json'))['keys']
            announce('Post-assessment export: ' + cohort + ' | ' + group)
            result = export_wide(db, output, cohort, keys, availability_policy='post-assessment', tabular_mode='latest-history', lookback_days=1826)
            checks = verify_bundle(db, output, cohort, keys, 'tabular', anchors)
            manifest = json.loads((output / 'dataset_manifest.json').read_text())
            row = {'format':'tabular','cohort':cohort,'variables':group,'directory':'exports/'+folder,'availability_policy':'post-assessment',
                   'status':'PASS','rows':result['rows'],'feature_count':len(keys),'acceptance':checks,
                   'availability_excluded_events':manifest['availability_excluded_events'],'availability_affected_people':manifest['availability_affected_people']}
            results.append(row)
            write_json(root / 'examples.json', results)
            announce('PASS | ' + str(result['rows']) + ' people | ' + str(checks['populated_cells']) + '/' + str(checks['feature_cells']) + ' populated feature cells')
        announce('Final source hash verification...')
        assert sha256(args.db) == summary['database_sha256'], 'Source hash changed'
        summary.update(exporter_version=__version__, examples=results, counts=dict(Counter(row['status'] for row in results)), source_unchanged=True)
        write_json(root / 'acceptance.json', summary)
        lines = ['# RC4 validation, reports and export examples','',
                 'Patient-level outputs: keep this directory in protected storage. The source database was opened read-only and its SHA-256 is unchanged.','',
                 '## Baseline protocol confirmed','',
                 'The agreed protocol is post-assessment/pre-intervention: prediction-day measurements are eligible; new therapeutic decisions are not. Earlier established history may be retained. Strict-before exports below are preserved as controls, not the intended default.','',
                 'New post-assessment examples use an explicit conservative role mask: baseline-day measurements, listed clinical observations and listed diagnostic procedures can enter; new/unclassified same-day drug/device/procedure/condition facts are held out. Outcome/administrative/decision-derived observations are held out even if dated earlier. Generic medication-history class context remains unresolved. This is not a complete intraday/source-role implementation; the remaining limitations are recorded in each availability_policy.json.','',
                 '## Findings requiring review','',
                 '- 2,984 people, 2,833 valid baselines; 151 missing baseline dates/ages, all Florence/SHaRe. SHaRe Training has 124 affected members and SHaRe Pilot 21; the remaining six are outside the named all-patients cohort.',
                 '- SMASH All Patients has 2,978 members, six fewer than the person table. No missing people were silently assigned to a split.',
                 '- All 10,537 Rennes measurements fall on the baseline day; strict-before tables are consequently almost empty. Use post-assessment examples for the agreed measurement boundary.',
                 f'- {missing_censor} missing censor dates; {len(after_censor)} dated endpoint record after censor. The documented observed-event policy can retain an event after last clinical contact with a flag; review its ascertainment, rather than moving the event date.',
                 '- Cohort names include SHaRe Training/Pilot and Tampere Training/Pilot. PILOT is not silently relabelled as TEST.',
                 '- Full-ETL cohort tables use results__ names and are now correctly discovered via the embedded schema map. The database does not embed an explicit release-version tag; rc4 comes from its supplied filename.',
                 '- Units, conflicting latest values and missing class context still cause audited blanks. External imaging/ECG assets were not verified in this database-only run.','',
                 '## Examples','', '| Format | Cohort | Variables | Availability | Status | Rows | Output |','|---|---|---|---|---|---:|---|']
        for row in results:
            location = '['+row['directory']+']('+row['directory']+'/)' if row['status']=='PASS' else 'Not generated: invalid/missing baselines'
            lines.append('| '+' | '.join([row['format'],row['cohort'],row['variables'],row.get('availability_policy','strict-before'),row['status'],str(row.get('rows','')),location])+' |')
        lines += ['', 'Each successful dataset has acceptance.json with source-reconciled counts/values, cohort membership and checksum checks. Tabular checks also reconcile latest eligible source dates, baseline anchors and QC guards. Event streams are full history, including post-baseline events, and need a downstream prediction-time mask. Outputs are feature-only; this run does not construct endpoint-specific survival risk sets or fitted models.', '',
                  'Reports: reports/inventory, reports/cohorts, reports/endpoints, reports/overlap, reports/distributions. CORE: 37 table/concept pairs; exclusive two-site: 32. Shared frozen lists: variable_sets/. Actionable private audit CSVs: audit/baseline_issues.csv, audit/people_outside_all_patients_cohort.csv, audit/events_after_censor.csv. Aggregate coverage/timing/split checks are also in audit/.', '',
                  'For post-assessment exports use the new exporter with --availability-policy post-assessment (default). The strict control uses --availability-policy strict-before. Reuse --variables-file variable_sets/core.json or custom.json across training and test cohorts. Match the availability policy as well as the variable list.']
        (root / 'README.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
        announce(json.dumps({'examples':summary['counts'],'source_unchanged':True,'missing_censor_dates':missing_censor,'events_after_censor':len(after_censor)}))


if __name__ == '__main__':
    main()
