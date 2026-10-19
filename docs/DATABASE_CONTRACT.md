# SQLite database contract

The clinical input is a supplied versioned SQLite file. The exporter opens it using `mode=ro` and `query_only`, reads one transaction, and never checkpoints, repairs or imports source data into it. PostgreSQL custom dumps are rejected by the core client.

## Implemented discovery

Standard logical tables resolve as flat or flattened schema names (`cdm.person`, `cdm_person`, `cdm__person`, etc.). Full-ETL CDM/results cohort collisions use the embedded `smash_export_metadata` results-schema mapping. Other unresolved ambiguities fail rather than choosing by row count or merging memberships. A release must expose an unambiguous table/schema map for each contract.

The minimum person table has `person_id`. Fact table discovery supports condition, measurement, observation, procedure, drug and device. Concept names come from `concept(concept_id, concept_name)` when present. Exact overlap is keyed by fact table and target concept ID, excludes concept 0 and concept names beginning `SMASH cohort membership:`, and includes full loaded history. Unknown concepts are shown with their IDs and a blank name.

Site attribution uses an embedded `person.site` column or `smash_fact_provenance(omop_table, fact_id, site)` person rows, rejecting conflicting evidence. Recognized SMASH databases may use the project's existing ID partition as a compatibility fallback: Florence 1–99,999,999, Rennes 100,000,000–199,999,999, Tampere 500,000,000–599,999,999. SMASH identity must be established by its extension metadata table or `cdm_source_name`; arbitrary generic IDs are not silently labeled Florence. Unknown sites prevent a purported three-site overlap report.

`cohort_definition(cohort_definition_id, cohort_definition_name)` and `cohort(cohort_definition_id, subject_id)` supply canonical discovery and selection. There are no hardcoded ID limits or PILOT-to-TEST aliases in the new client. Names match consistently across case, spaces, underscores and hyphens; numeric IDs can be supplied directly. Membership counts use distinct people because cohort rows can overlap.

`smash_release_metadata(key,value)` may contain a JSON `build_manifest`. Public reports expose only release, scope and generation time; they do not echo source file paths or private rejected-row/person lists. The external expected database hash is optional for local reporting and required only when a trusted checksum comparison is requested. A self-contained DB cannot carry its own finalized hash without a circular definition.

## Recognized study capabilities

- Baseline anchors: populated `smash_endpoint_censor` with `person_id`, `baseline_date`, `baseline_age`.
- Endpoint labels: populated `smash_endpoint_event` with `person_id`, `endpoint`, `status`.
- External file catalog: populated `smash_asset` with `asset_id`, `person_id`, `relative_path`; byte validation also requires expected `sha256`, and checks `size_bytes` where present.
- Existing imaging metadata: `image_occurrence` with `person_id`, `local_path` is discovered separately; a complete file inventory/checksum catalog is still necessary for rigorous asset validation.

Discovery is not proof that every record has a valid anchor/outcome/asset. Baseline export validates the selected people's dates/ages and requires unique anchors. Detailed endpoint eligibility, timestamp precision and clinical interpretation remain additional release contracts. Empty tables are unsupported capabilities. They do not trigger a source-CSV fallback or inferred labels.

The forthcoming full v1.4 database should embed cohorts/splits/folds, clinical anchors, endpoint/censor definitions, portable source-variable annotations and asset patient/exam/lineage records. Variable aggregation and reviewed unit/context rules are versioned in the exporter, supplemented by embedded annotations where available. No WP2 report or mapping directory is a runtime requirement. Actual signals/images stay external; a remote transport manifest may describe archives/shards.

## Event stream

The implemented `export --format events` emits the seven-column dated event contract: `person_id,domain,concept_id,event_date,value_as_number,value_as_concept_id,unit_concept_id`. It excludes `SMASH:*` release-management observations and retains numeric zero. Optional cohort selection uses database memberships. Missing supported value columns become blank rather than invented values.

Rows are sorted by person, date, domain, concept and fact ID. Default streams contain full history, including post-baseline facts. Explicit `--event-scope baseline` requires cohort anchors and applies the configured prediction-time mask/lookback. Domains, calendar dates and optional source/fact/site/baseline-relative metadata are configurable. The manifest records the source/output hashes and exact policy; no outcome labels or risk sets are generated. Source-file change/nonempty WAL prevents publication. No date is derived from cohort creation dates.

`--vars core`, `core+two-site` or `all` can filter event exports using variables calculated directly from this database. The selected variable identities are recorded in the export manifest.

## Baseline tables

`export --format tabular --cohort <name-or-id> --vars core` implements feature-only baseline tables. It requires populated cohort membership and unique valid `smash_endpoint_censor` anchors for all selected people. Every selected person remains in the output, including all-missing rows. Stable table/concept columns use only exact-day evidence under the versioned post-assessment/pre-intervention availability mask, with four metadata fields and one column per selected feature. No prior values or derived window features are included by default. Baseline-day measurements can enter; unclassified actions and outcome/administrative information are held out. Missing dates are not inferred. `--tabular-mode latest-history --lookback-days <N> --availability-policy strict-before` preserves the older diagnostic control explicitly. See [BASELINE_AVAILABILITY.md](BASELINE_AVAILABILITY.md). Numeric unit identity is checked across the release; unknown/multiple units and conflicting latest values remain missing with QC reasons. Positive-only facts do not imply negative status when absent. Medication observation 3021806 remains held pending class-context rules.

Outputs include data, samples, concept/unit dictionary, source/feature definitions, provenance and hashed manifest. Explicit history options add previous values/recency/count/numeric summaries; explicit family presets carry their versioned category mapping. Standard layout uses `DATA_DIR/<group>/train.csv,test.csv`; low-level bundles retain `data.csv`. No outcome labels or fitted transformations are included. Optional event metadata includes source text. Annual indices/risk sets/labelled recipes remain separate. See [DATASET_EXPORTS.md](DATASET_EXPORTS.md); legacy outputs retain their historical contracts.

Full-ETL collision names such as `results__cohort`/`cdm__cohort` are resolved through the embedded `smash_export_metadata` manifest; analytical cohorts use its results-schema mapping. No membership is merged or inferred from row counts. Full-vocabulary lookups load referenced clinical concepts rather than millions of unused names. Ledger validation now reports missing/invalid anchors and duplicate/unmatched endpoint keys.
