"""Validate a full SQLite release and produce audited report/export examples.

Run explicitly against protected local storage. Outputs include patient-level
datasets; console output is restricted to counts/statuses. The source is read-only.
"""
import argparse
from collections import Counter, defaultdict
from datetime import date
import csv
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from smash_hcm_databank_client import __version__
from smash_hcm_databank_client.database import FACTS, OmopDatabase, quote, sha256
from smash_hcm_databank_client.exports import DOMAINS, FIELDS, export_events
from smash_hcm_databank_client.features import PRESETS, load_variable_set, resolve_variables, save_variable_set
from smash_hcm_databank_client.output import write_csv, write_json
from smash_hcm_databank_client.reports import REPORTS, write_report
from smash_hcm_databank_client.tabular import export_wide
from smash_hcm_databank_client.validation import validate_database
from smash_hcm_databank_client.availability import held_reason


def announce(message):
    print(message, flush=True)


def members(db, cohort):
    cid = db.cohort_id(cohort)
    return {row[0] for row in db.connection.execute('SELECT DISTINCT subject_id FROM ' + quote(db.table('cohort')) + ' WHERE cohort_definition_id=?', (cid,))}


def audit_ledgers(db, out):
    out.mkdir()
    population = set(db.person_sites())
    anchors, issues, coverage, cohort_members = {}, [], [], {}
    for pid, day, age in db.connection.execute('SELECT person_id,baseline_date,baseline_age FROM ' + quote(db.table('smash_endpoint_censor'))):
        reason = ''
        try:
            if day is None or age is None:
                reason = 'missing_baseline_date_or_age'
                raise ValueError()
            parsed, number = date.fromisoformat(str(day)[:10]), float(age)
            if not 0 <= number <= 120:
                raise ValueError()
            anchors[pid] = (parsed, number)
        except (ValueError, TypeError):
            issues.append({'person_id': pid, 'site': db.person_sites().get(pid, 'UNKNOWN'), 'issue': reason or 'invalid_baseline_date_or_age'})
    for row in db.cohorts():
        selected = members(db, row['cohort_id'])
        cohort_members[row['name']] = selected
        coverage.append({**row, 'missing_or_invalid_baselines': len(selected - set(anchors))})
    write_csv(out / 'baseline_issues.csv', ['person_id', 'site', 'issue'], issues)
    write_csv(out / 'cohort_baseline_coverage.csv', ['cohort_id', 'name', 'patients', 'missing_or_invalid_baselines'], coverage)
    all_members = cohort_members.get('SMASH All Patients', population)
    omitted = population - all_members
    write_csv(out / 'people_outside_all_patients_cohort.csv', ['person_id', 'site'], [{'person_id': pid, 'site': db.person_sites()[pid]} for pid in sorted(omitted)])
    splits = []
    for left, right in [('FLORENCE Training', 'FLORENCE Pilot'), ('Rennes Training', 'Rennes Test'), ('Tampere Training', 'Tampere Pilot')]:
        if left in cohort_members and right in cohort_members:
            splits.append({'left': left, 'right': right, 'overlapping_people': len(cohort_members[left] & cohort_members[right])})
    write_csv(out / 'split_overlap.csv', ['left', 'right', 'overlapping_people'], splits)
    endpoint_dates = db.connection.execute('SELECT endpoint,status,count(*),sum(event_date IS NULL) FROM smash_endpoint_event GROUP BY endpoint,status').fetchall()
    write_csv(out / 'endpoint_date_coverage.csv', ['endpoint', 'status', 'rows', 'missing_event_dates'], [dict(zip(['endpoint','status','rows','missing_event_dates'], row)) for row in endpoint_dates])
    result = {'people': len(population), 'valid_baselines': len(anchors), 'baseline_issues': len(issues), 'baseline_issues_by_site': dict(Counter(row['site'] for row in issues)),
              'cohorts': coverage, 'people_outside_all_patients_cohort': len(omitted), 'split_overlap': splits,
              'embedded_release_version': db.release_metadata().get('release'), 'external_assets_verified': False}
    if db.table('associated_file'):
        rows = db.connection.execute('SELECT site,modality,count(*),sum(sha256 IS NULL OR sha256=\'\'),sum(person_id IS NULL) FROM associated_file GROUP BY site,modality').fetchall()
        write_csv(out / 'associated_files.csv', ['site','modality','records','without_sha256','without_person_id'], [dict(zip(['site','modality','records','without_sha256','without_person_id'], row)) for row in rows])
    write_json(out / 'ledger_audit.json', result)
    return result, anchors


def read_csv(path):
    with Path(path).open(newline='', encoding='utf-8') as handle:
        yield from csv.DictReader(handle)


def event_fingerprint(row):
    text = json.dumps(['' if value is None else str(value) for value in row], separators=(',', ':'))
    return int.from_bytes(hashlib.sha256(text.encode()).digest(), 'big')


def verify_events(db, output, cohort, keys):
    wanted = members(db, cohort)
    actual, expected, actual_sum, expected_sum = Counter(), Counter(), 0, 0
    previous, rows = None, 0
    for row in read_csv(output / 'omop_events.csv'):
        assert int(row['person_id']) in wanted, 'Event export contains a nonmember'
        order = (int(row['person_id']), row['event_date'], row['domain'], int(row['concept_id']))
        assert previous is None or previous <= order, 'Event rows are not deterministically ordered'
        previous = order
        actual[(row['domain'], int(row['concept_id']))] += 1
        actual_sum += event_fingerprint([row[field] for field in FIELDS])
        rows += 1
    by_table = defaultdict(list)
    for table, cid in keys:
        by_table[table].append(cid)
    for logical, concept, day, numeric, category, unit, source, _ in FACTS:
        if logical not in by_table:
            continue
        columns = db.columns(logical)
        if not {concept, day, 'person_id'}.issubset(columns):
            continue
        def field(name):
            return 'f.' + quote(name) if name in columns else 'NULL'
        query = 'SELECT f.person_id,' + field(concept) + ',' + field(day) + ',' + field(numeric) + ',' + field(category) + ',' + field(unit) + ' FROM ' + quote(db.table(logical)) + ' f WHERE f.person_id IN (SELECT subject_id FROM ' + quote(db.table('cohort')) + ' WHERE cohort_definition_id=?)'
        if logical == 'observation' and source in columns:
            query += ' AND (' + field(source) + ' IS NULL OR ' + field(source) + ' NOT LIKE \'SMASH:%\')'
        selected_ids = set(by_table[logical])
        for pid, cid, event_day, number, coded, unit_id in db.connection.execute(query, (db.cohort_id(cohort),)):
            if cid not in selected_ids:
                continue
            domain = DOMAINS[logical]
            expected[(domain, cid)] += 1
            expected_sum += event_fingerprint([pid, domain, cid, event_day, number, coded, unit_id])
    assert actual == expected, 'Exported event counts differ from source table/concept counts'
    assert actual_sum == expected_sum, 'Exported event field contents differ from source'
    return {'rows_checked': rows, 'source_field_fingerprint': 'PASS', 'cohort_membership': 'PASS', 'source_counts': 'PASS', 'ordering': 'PASS'}


def verify_tabular(db, output, cohort, keys, anchors):
    manifest = json.loads((output / 'dataset_manifest.json').read_text())
    policy = manifest.get('availability_policy', 'strict-before')
    mode = manifest.get('tabular_mode', 'latest-history')
    lookback = manifest.get('lookback_days', 1826)
    rows = list(read_csv(output / 'data.csv'))
    wanted = members(db, cohort)
    assert {int(row['person_id']) for row in rows} == wanted and len(rows) == len(wanted), 'Tabular membership/uniqueness mismatch'
    feature_names = [table + '__' + str(cid) for table, cid in keys]
    metadata = manifest.get('metadata_columns', ['person_id', 'site', 'landmark_id', 'landmark_age_years'])
    assert list(rows[0]) == metadata + feature_names
    if mode == 'snapshot':
        assert len(rows[0]) == len(keys) + 4 and not manifest['carry_forward'] and lookback is None
        assert all(row['snapshot_date'] == anchors[int(row['person_id'])][0].isoformat() for row in rows)
    for row in read_csv(output / 'samples.csv'):
        pid = int(row['person_id'])
        assert row['baseline_date'] == anchors[pid][0].isoformat() and float(row['baseline_age_years']) == anchors[pid][1]
    data = {row.get('landmark_id', str(row['person_id']) + ':baseline'): row for row in rows}
    source_latest = {}
    by_table = defaultdict(set)
    for table, cid in keys:
        by_table[table].add(cid)
    names = db.concept_names()
    for logical, concept, day, numeric, category, unit, *_ in FACTS:
        if logical not in by_table or not {concept, day, 'person_id'}.issubset(db.columns(logical)):
            continue
        columns = db.columns(logical)
        def field(name):
            return quote(name) if name in columns else 'NULL'
        sql = 'SELECT person_id,' + ','.join(field(name) for name in (concept, day, numeric, category, unit)) + ' FROM ' + quote(db.table(logical)) + ' WHERE person_id IN (SELECT subject_id FROM ' + quote(db.table('cohort')) + ' WHERE cohort_definition_id=?)'
        for pid, cid, day_value, number, coded, unit_id in db.connection.execute(sql, (db.cohort_id(cohort),)):
            if cid not in by_table[logical]:
                continue
            try:
                event_day = date.fromisoformat(str(day_value)[:10])
            except ValueError:
                continue
            elapsed = (anchors[pid][0] - event_day).days
            if elapsed < 0 or (mode == 'snapshot' and elapsed != 0) or (mode == 'latest-history' and elapsed > lookback) or held_reason(logical, cid, names.get(cid, ''), elapsed == 0, policy):
                continue
            key = (pid, logical, cid)
            existing = source_latest.get(key)
            value = (number, coded, unit_id)
            if existing is None or event_day > existing[0]:
                source_latest[key] = (event_day, [value])
            elif event_day == existing[0]:
                existing[1].append(value)
    provenance_count, populated, reasons = 0, 0, Counter()
    for row in read_csv(output / 'feature_provenance.csv'):
        pid = int(data[row['landmark_id']]['person_id'])
        if row['event_date']:
            elapsed = (anchors[pid][0] - date.fromisoformat(row['event_date'])).days
            assert elapsed == 0 if mode == 'snapshot' else (0 <= elapsed if policy == 'post-assessment' else 0 < elapsed) and elapsed <= lookback, 'Baseline cutoff/lookback violation'
        evidence = source_latest.get((pid, row['table'], int(row['concept_id'])))
        assert row['event_date'] == (evidence[0].isoformat() if evidence else ''), 'Provenance does not select the latest eligible source date'
        value = data[row['landmark_id']][row['feature']]
        if value:
            assert row['qc_reason'] in ('ok', 'coded_category_id', 'documented_positive_in_window', 'documented_positive_on_snapshot_day'), 'Unsafe value escaped QC'
            if row['qc_reason'] == 'ok':
                assert int(row['unit_concept_id']) > 0
                assert evidence and any(number is not None and float(value) == float(number) and str(unit_id) == row['unit_concept_id'] for number, _, unit_id in evidence[1]), 'Numeric value/unit does not match eligible source evidence'
            elif row['qc_reason'] == 'coded_category_id':
                assert evidence and any(str(coded) == value for _, coded, _ in evidence[1]), 'Category does not match eligible source evidence'
            else:
                assert evidence and value == '1'
            populated += 1
        else:
            assert row['qc_reason'] not in ('ok', 'coded_category_id', 'documented_positive_in_window', 'documented_positive_on_snapshot_day')
        provenance_count += 1
        reasons[row['qc_reason']] += 1
    assert provenance_count == len(rows) * len(keys)
    return {'rows_checked': len(rows), 'feature_columns': len(keys), 'feature_cells': provenance_count, 'populated_cells': populated,
            'populated_fraction': populated / provenance_count if provenance_count else 0, 'qc_counts': dict(reasons),
            'cohort_membership_and_columns': 'PASS', 'anchor_alignment': 'PASS', 'time_boundaries': 'PASS', 'unsafe_values_blank': 'PASS'}


def verify_bundle(db, output, cohort, keys, fmt, anchors):
    manifest = json.loads((output / 'dataset_manifest.json').read_text())
    assert manifest['cohort_id'] == db.cohort_id(cohort) and manifest['variables'] == [list(key) for key in keys]
    assert load_variable_set(output / 'variable_set.json')['keys'] == keys
    for filename, expected in manifest['output_sha256'].items():
        assert sha256(output / filename) == expected, 'Output checksum mismatch'
    checks = verify_tabular(db, output, cohort, keys, anchors) if fmt == 'tabular' else verify_events(db, output, cohort, keys)
    assert checks['rows_checked'] == manifest['rows']
    write_json(output / 'acceptance.json', {'status': 'PASS', **checks})
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    initial = args.db.stat()
    announce('Running source integrity/hash/schema validation (read-only)...')
    with OmopDatabase(args.db) as db:
        validation = validate_database(db, required=['cohorts', 'cohort_catalog', 'baseline_anchors', 'endpoint_labels'])
        (args.out / 'validation').mkdir()
        write_json(args.out / 'validation/database.json', validation)
        announce('Technical validation: ' + validation['status'] + '; writing ledger audits...')
        ledger, anchors = audit_ledgers(db, args.out / 'audit')
        for kind in REPORTS:
            announce('Generating report: ' + kind)
            report = write_report(db, kind, args.out / 'reports' / kind)
            announce('Report ' + kind + ': ' + report.get('status', 'PASS'))
        presets = {}
        for name in PRESETS:
            try:
                presets[name] = resolve_variables(db, name)
            except ValueError:
                pass
        custom = [key for key in presets['core'] if key[0] == 'measurement'][:5] + [key for key in presets['core'] if key[0] == 'condition_occurrence'][:2]
        custom = sorted(set(custom or presets['core'][:5]))
        presets['custom'] = custom
        for name, keys in presets.items():
            save_variable_set(args.out / 'variable_sets' / (name.replace('+', '-plus-') + '.json'), db, keys, name)
        cases = [
            ('tabular', 'Rennes Training', 'core'), ('tabular', 'Rennes Test', 'core'),
            ('tabular', 'Tampere Training', 'core'), ('tabular', 'Tampere Pilot', 'core'),
            ('tabular', 'Rennes All Patients', 'core+two-site'), ('tabular', 'Tampere All Patients', 'all'),
            ('tabular', 'Rennes Test', 'ecg-derived'), ('tabular', 'Rennes Training', 'custom'), ('tabular', 'Rennes Test', 'custom'),
            ('events', 'FLORENCE Training', 'core'), ('events', 'FLORENCE Pilot', 'all'),
            ('events', 'Rennes Test', 'custom'), ('events', 'Tampere Pilot', 'ecg-derived'), ('events', 'SMASH All Patients', 'core+two-site'),
            ('tabular', 'FLORENCE Training', 'core'), ('tabular', 'FLORENCE Pilot', 'core')]
        results = []
        for number, (fmt, cohort, group) in enumerate(cases, 1):
            folder = f'{number:02d}-' + fmt + '-' + cohort.lower().replace(' ', '-') + '-' + group.replace('+', '-plus-')
            output = args.out / 'exports' / folder
            announce(f'{number}/{len(cases)}: {fmt} | {cohort} | {group}')
            row = {'format': fmt, 'cohort': cohort, 'variables': group, 'directory': 'exports/' + folder}
            if group not in presets:
                results.append({**row, 'status': 'UNAVAILABLE', 'detail': 'No matching variables'})
                continue
            keys = presets[group]
            try:
                result = export_wide(db, output, cohort, keys, availability_policy='strict-before', tabular_mode='latest-history', lookback_days=1826) if fmt == 'tabular' else export_events(db, output, cohort, keys)
                checks = verify_bundle(db, output, cohort, keys, fmt, anchors)
                row.update(status='PASS', rows=result['rows'], feature_count=len(keys), acceptance=checks)
            except (ValueError, AssertionError) as exc:
                row.update(status='BLOCKED' if not output.exists() else 'FAIL', detail=str(exc))
            results.append(row)
            write_json(args.out / 'examples.json', results)
            announce(row['status'] + ' | ' + str(row.get('rows', 0)) + ' rows' + (' | ' + row['detail'] if 'detail' in row else ''))
        announce('Rechecking source SHA-256 and snapshot stability...')
        final_digest = sha256(args.db)
        final = args.db.stat()
        source_unchanged = final_digest == validation['database_sha256'] and (initial.st_size, initial.st_mtime_ns) == (final.st_size, final.st_mtime_ns)
        result = {'exporter_version': __version__, 'database': args.db.name, 'database_sha256': final_digest, 'source_unchanged': source_unchanged,
                  'database_validation': validation['status'], 'ledger_audit': ledger, 'examples': results,
                  'counts': dict(Counter(row['status'] for row in results)), 'external_assets_verified': False}
        write_json(args.out / 'acceptance.json', result)
        lines = ['# RC4 validation and export examples', '', 'This directory contains patient-level datasets. Keep it in protected storage.', '',
                 f'Exporter: {__version__}. Database: `{args.db.name}`.', f'Source unchanged: {source_unchanged}. SHA-256: `{final_digest}`.', '',
                 '## Findings', '', f'- {ledger["people"]} people; {ledger["valid_baselines"]} valid baseline anchors; {ledger["baseline_issues"]} missing/invalid anchors.',
                 f'- {ledger["people_outside_all_patients_cohort"]} people are outside the named SMASH All Patients cohort.',
                 '- The full ETL uses results__cohort tables; the exporter adapter now uses its embedded schema map.',
                 '- No embedded release version is present; rc4 is the supplied filename label, not a version verified from metadata.',
                 '- External asset files were not validated; associated-file metadata alone does not prove local availability.', '',
                 '## Examples', '', '| Format | Cohort | Variables | Status | Rows | Files |', '|---|---|---|---|---:|---|']
        for row in results:
            lines.append('| ' + ' | '.join([row['format'], row['cohort'], row['variables'], row['status'], str(row.get('rows', '')), '[' + row['directory'] + '](' + row['directory'] + '/)']) + ' |')
        lines += ['', 'CORE means exact concept presence across three sites. Tabular outputs are feature-only, strictly before baseline, with the existing 1,826-day window. No dates or missing baselines were invented, and cohort memberships were not resplit. Event streams are full history and require downstream prediction cutoffs.', '',
                  'Every successful output has acceptance.json; examples.json has aggregate QC counts. See audit/baseline_issues.csv and audit/people_outside_all_patients_cohort.csv for local identifiers requiring ETL review. Reports are in reports/. All feature lists are in variable_sets/.', '',
                  'Reuse --variables-file variable_sets/custom.json with export --format tabular or --format events and the canonical cohort names above. No PILOT cohort is relabelled as TEST.']
        (args.out / 'README.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
        announce(json.dumps({'source_unchanged': source_unchanged, 'examples': result['counts'], 'baseline_issues': ledger['baseline_issues'], 'all_cohort_omissions': len(set(db.person_sites()) - members(db, 'SMASH All Patients'))}))


if __name__ == '__main__':
    main()
