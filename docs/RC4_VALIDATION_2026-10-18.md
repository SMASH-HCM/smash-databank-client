# RC4 validation and exact-day examples — 18 October 2026

Source: `K:/SMASH_DATA/smash-data-bank/SMASH_v1.4_rc4.db` (3,632,111,616 bytes). All access used SQLite read-only mode. SHA-256 before/after the export runs matched: `48bbb9835ed403c6a53b4e4bb9bdd20334a9b91bbf08376772895d1efbae3843`. No independent expected release checksum was supplied.

Requested output root: `K:/SMASH_DATA/omop-exporter/rc4-validation-2026-10-18/`. Its README indexes reports, current snapshots, explicit history examples and prior controls. It contains patient-level data; it is not a public release artifact.

## Current default

Version 0.9 uses an exact-day snapshot: `person_id`, `site`, `cohort`, `snapshot_date`, followed by exactly one column for each selected `(table, concept_id)`. RC4 has 37 CORE pairs, producing 41 CSV columns. No averaging, carry-forward, sliding-window, recency/count, previous-value or previous-age features are introduced. Conflicting same-day values remain blank with QC reasons. Separate companion files retain ages, units, source evidence and availability audits.

The agreed post-assessment/pre-intervention mask admits eligible baseline-day measurements and explicit clinical/diagnostic roles, while holding unclassified actions and administrative/outcome-derived observations. Its source-role coverage remains conservative, not a complete intraday ledger. See [BASELINE_AVAILABILITY.md](BASELINE_AVAILABILITY.md).

FLORENCE labels replace SHaRe in exported cohort names and filenames. Original cohort IDs/names remain in provenance and resolve as aliases; patient membership and PILOT/TEST roles are unchanged.

| Exact-day example | People | Features | Total columns |
|---|---:|---:|---:|
| Rennes Training — CORE | 161 | 37 | 41 |
| Rennes Test — CORE | 40 | 37 | 41 |
| Tampere Training — CORE | 74 | 37 | 41 |
| Tampere Pilot — CORE | 27 | 37 | 41 |
| Rennes Test — ECG-labelled measurements | 40 | 3 | 7 |
| Tampere All Patients — ALL | 101 | 250 | 254 |
| Rennes Training — custom | 161 | 7 | 11 |
| Rennes Test — custom | 40 | 7 | 11 |

CORE snapshots populated 3,603/5,957 feature cells in Rennes Training and 908/1,480 in Rennes Test. The ECG-labelled Rennes snapshot is entirely missing and is identified as a coverage finding. A 365-day Tampere history example requires explicit `--tabular-mode latest-history --lookback-days 365`. Earlier history controls remain separately indexed; they are not the current default. Annual/shifted prediction indexes remain a separate explicit risk-set workflow.

## Reports and checks

The full release has 2,984 people and 23 cohort definitions. Five report templates succeeded: inventory, cohorts, endpoints, exact overlap and unit-stratified numeric distributions. Overlap is 37 CORE and 32 exclusive two-site variables; it is structural, not proof of baseline completeness or clinical equivalence.

The full ETL's `results__cohort`/`cdm__cohort` collision names required an exporter adapter fix using the embedded schema map. Its 4,085,317-concept vocabulary also required sparse cached clinical-name lookup. These were exporter compatibility/performance issues, not absent ETL cohort tables.

Source-reconciled validation covers membership/uniqueness, selected columns, source values and latest eligible dates, time boundaries, availability/QC guards, event ordering, complete event-field fingerprints and output checksums. Event streams remain full history. The initial run produced 14 successful historical/event examples and two blocked requests; eight post-assessment history comparisons and eight exact-day defaults plus one explicit history example were subsequently added. Empty/all-missing cases are flagged separately from extraction correctness.

## Findings requiring review

- **151 missing baseline date/age pairs**, all FLORENCE. FLORENCE Training has 124 affected members and Pilot 21; another six people are outside the named all-patients cohort. Full FLORENCE tabular requests remain blocked; no dates were inferred or people silently dropped.
- **SMASH All Patients contains 2,978 members**, six fewer than `person`. Private identifiers are in `audit/people_outside_all_patients_cohort.csv`.
- **152 missing censor dates; one dated OVERALL endpoint after censor.** The documented observed-event policy permits a flagged event after last clinic contact, subject to ascertainment review; dates were not moved.
- **Unitless NYHA numeric classes remain held by the generic numeric unit rule.** This is an exporter type-handling limitation needing a reviewed ordinal representation, not proof that NYHA needs a physical unit.
- **Conflicting same-day blood-pressure measurements** remain blank: Rennes Training has 139 systolic and 132 diastolic affected cells. Source assessment contexts need review; no arbitrary average was substituted. Cross-release troponin unit conflicts are also held.
- ECG-labelled measurement coverage is absent for some examples; this preset is not all ECG diagnoses/history and does not process adjacent waveforms.
- The database has no explicit embedded release-version tag; RC4 is the supplied filename label. External asset availability was not verified by this database-only exercise.

Required-anchor validation therefore reports FAIL even though SQLite integrity, core link checks, duplicate-key checks and available cohort/endpoint capabilities pass. Source and clinical limitations are retained explicitly rather than hidden by a blanket PASS.

## Verification

The final suite passed **226 tests**, including read-only RC4 integration checks, exact-day/no-carry-forward/no-averaging contracts, explicit history configuration and FLORENCE/source-name resolution. Prior temporal-window tests were changed to opt into history explicitly. Local results: `.local-reports/rc4-snapshot-final-tests-20261018.xml`.

Reproduction scripts are `tools/validate_release_examples.py` (explicit historical controls), `tools/validate_post_assessment_examples.py` (post-assessment history comparisons), and `tools/validate_snapshot_examples.py` (current snapshots, display labels and explicit history). Existing output directories are preserved; these scripts are intended for a new/known RC4 validation folder, not arbitrary unattended filesystem changes. No real patient rows or source identifiers are stored in this repository report.
