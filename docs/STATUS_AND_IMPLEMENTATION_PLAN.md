# SMASH-HCM Databank Client: historical status review and implementation plan

Current repository: [SMASH-HCM/smash-hcm-databank-client](https://github.com/SMASH-HCM/smash-hcm-databank-client). This document preserves the 13–15 October review and implementation history. Current startup/data-update behaviour, dataset configuration and automatic main release-candidate policy are documented in [the current index](README.md); old missing-feature statements below are dated review findings.

Originally reviewed 13 October 2026 against exporter commit `427cbc1`, the working-tree documentation, and v1.4rc3 SQLite. The original review/backlog is preserved below; the implementation update describes what is now available.

**Input requirement clarified:** clinical reporting and dataset generation must run from the supplied `omop.db`. They must not require a WP2 report, WP2 checkout, source/mapping CSVs, or an external clinical dictionary. The reviewed RC3 is an intentionally partial clinical candidate, not evidence that the complete ETL database lacks study metadata. The design below makes the complete database the clinical source of truth; external files are the actual assets and optional transport/checksum manifests.

**Development inputs confirmed:** the complete v1.4 database is forthcoming. Use RC snapshots where appropriate, older PostgreSQL dumps for legacy compatibility, and synthetic complete SQLite fixtures for contracts not yet present in RC3. Framework, scripts and documentation can be developed now; only final full-release integration/acceptance depends on the forthcoming database.

## Implementation update — 13 October 2026

**Menu and catalog browser update, 15 October:** version 0.5.0 adopts the SMASH-HCM DATABANK EXPORTER title, aligned four-row status box and five-item main menu. Setup has the four requested login/connection/manifest/location options. Downloads select cohorts before one or more data types, with incomplete cohort/type combinations disabled. The manifest browser supports individual/multiple files, parent navigation, immediate-folder files and recursive subfolder contents, followed by the common size/location/transfer review. Plain and Questionary menus share the same hierarchy. The complete suite passes 183 tests. No remote catalog, clinical file or credential is invented or changed by this UI update.

**Manifest error clarification, 15 October:** live authenticated checks confirm that the databank folder and README are accessible while `manifest.json` returns 404. Version 0.4.3 separates the server/folder display, retains the last explicit connection result for the current session, and treats an absent manifest as a catalog availability issue after verifying root access. It keeps any cached valid manifest and explains how to publish/share the file or choose its actual path. HTTP status codes are carried structurally; authentication and root-access failures are not mislabeled as a missing manifest. No server file or credential is changed.

**Guided workflow update, 15 October:** version 0.4.2 reorganizes Questionary into setup/connection, downloads and verification, with advanced tools separate. It checks connection and retrieves the manifest in one step; offers databases, published cohort CSVs and MRI/ECG/Echo ZIPs; supports multi-cohort checkboxes with exact tags; reviews all paths/sizes; confirms a home-based download location; and verifies tracked files offline. Portable profile state is stable under the user's home directory. The new block-character logo replaces the earlier repeating-letter version and scales to regular terminals. The full suite passes 158 tests, both Windows bundle modes pass the selection/verification smoke flow, and native console navigation plus an authorized live menu README test pass. Data publication still needs the real server manifest and finalized artifacts; no cohort file names or patient subsets are invented.

**Portable/UI update, 15 October:** version 0.3.0 adds optional Questionary arrow-key grouped menus, disabled-choice explanations based on local prerequisites, a Data Access Request form link, menu database validation and bundled-runtime diagnostics. Both Windows portable bundle formats include Python/UI/vault/YAML support and pass frozen-executable validation/synthetic-export smoke checks; 138 tests pass. The supplied ASCII artwork now uses repeating SMASHHCM characters, with a compact-terminal fallback. Build scripts/checksums and a manually dispatched Windows/Linux/macOS artifact workflow are included. Only the local Windows builds have been exercised; public releases/signing and other-platform acceptance are still outstanding. See [BINARY_RELEASES.md](BINARY_RELEASES.md).

**15 October additions:** `setup` and the default interactive SMASH menu now provide a logo/local release display, hidden password entry, optional native OS vault storage, connection checks, remote/local manifest loading, checksum/cache verification, database selection/download, exact cohort/modality downloads and local variable exports. The URL/root are fixed to the SMASH service. Existing `.env` credentials remain compatible. No real server manifest has been created yet; `manifest.example.json` is supplied. Resume and archive extraction remain planned. See [MENU.md](MENU.md).

The packaging/local-foundation slice is implemented: installable SQLite CLI, optional PostgreSQL adapter, read-only validation, inventory/overlap, cohort discovery and full-history events. Core runtime dependencies remain empty; native vault support is an optional `secure` extra. Baseline feature-only tabular export now reads embedded cohorts/anchors, retains all-missing people, uses strict pre-baseline windows and writes concept/unit/QC companions. The three former wide-export expected failures now pass as ordinary contracts. Annual indexes, outcome-label recipes, distribution plots and multimodal packaging still require implementation. See [SETUP.md](SETUP.md), [TESTING.md](TESTING.md) and [DATABASE_CONTRACT.md](DATABASE_CONTRACT.md).

An authorized live test downloaded `/databank/README.md` (586 bytes), with a credential-free checksum receipt. A later live menu connection check passed and displayed the actual RC3 version. Final verification passed 129 tests, source/wheel builds and an installed-wheel menu smoke test outside the checkout. Manifest/database/archive downloads are tested against fake servers; baseline exports use synthetic complete databases. RC1/RC3 tests remain read-only. No real credentials were migrated into the vault and no clinical download or patient export was performed. The tables and verification notes below are the original review snapshot; they do not override this update.

## 1. Recommendation

Make this repository the collaborator-facing client for a **versioned SMASH data release**: open or download the database, inspect its contents, validate the requested clinical and asset components, and export reproducible datasets. Use SQLite directly for the normal workflow, with a wide tabular CSV as the default. Retain the event-stream contract and isolate the existing PostgreSQL workflow as a legacy adapter.

The first deliverable should be a useful local client: **database validation, inventory/overlap reports, and a wide baseline export**. Generate every clinical report by querying the database directly. Secure Nextcloud setup and downloads should follow once release publication is defined. A downloader cannot compensate for study metadata absent from a partial candidate, so complete ETL snapshot packaging is an upstream release task.

Keep curation, DICOM-to-NIfTI conversion, ECG digitization, clinical harmonization, and authoritative cohort/endpoint construction in the ETL/data-bank workflow. The exporter should manage access, selection, validation and packaging of those versioned products. It should not silently recreate clinical definitions from raw files.

## 2. Verified current state

### Repository

The repository consists of seven Python scripts, a PostgreSQL export SQL file, a YAML example, and documentation. There is no package configuration, installed `omop-exporter` entry point, committed test suite, or CI configuration in the reviewed checkout. The existing `README.md` was already modified and `docs/EXPORT_METHODOLOGY.md` was already untracked; both were included in the review and left unchanged.

| Requested capability | Current status | Reuse or gap |
| --- | --- | --- |
| Open a versioned OMOP `.db` | Missing | `main.py` uses psycopg against PostgreSQL; restore requires a dump and optional Docker client. |
| OMOP event stream | Implemented for PostgreSQL | Five clinical domains, then an age stream. Preserve compatibility while adding SQLite and optional provenance fields. |
| Wide patient table | Missing | `export_omop_tabular.py` writes sparse patient/landmark/domain/concept rows, not one row with named variable columns. |
| Cohort selection | Partial | Sparse exporter accepts cohort IDs/site/split filters; SQL limits memberships to IDs 1000–1410 and preparation hardcodes six study splits. No general cohort catalog or aliases. |
| Prediction indexes | Partial | Annual training landmarks and fixed test baselines exist. Main YAML runner does not forward annual-policy settings, follow-up policy, or the same-day inclusion option. |
| Endpoint labels | Implemented for the old ledger contract | Uses endpoint/censor CSVs exported from PostgreSQL. Historical fallback reads Florence/Rennes source files; it is unsuitable as an implicit RC3 fallback. |
| Three-site/two-site report | Existing reference implementation in WP2, not here | Its exact overlap SQL is reusable. Implement a database-only report here; do not require its generated report or its source/mapping-file enrichment. |
| Distribution report with plots | Missing here | Existing overlap report has min/max, but not a complete mean/SD/quartile/IQR comparison and plot set. |
| Curated/raw assets | Request-list prototype | `build_asset_request_manifest.py` links externally supplied CSVs and checks path existence. No checksum/content validation, temporal selection, copying, download or release binding. |
| Nextcloud setup/download | Missing | No Nextcloud client or credential store. WP2's existing downloader is a Google Drive implementation. |
| Release validation | Missing | Optional dump SHA-256 recording does not compare to an expected hash or validate SQLite, cohorts or assets. |

The separate `build_harmonized_echo_table.py` reads Florence/Rennes curated CSVs, uses a legacy Rennes linkage and expects 201 linked patients. It is not a generic three-site OMOP table builder and is not called by `main.py`.

### v1.4rc3 database

Inspected read-only: `K:/SMASH_DATA/smash-etl/releases/v1.4_rc3/SMASH_OMOP_v1.4_rc3.db`.

| Check/content | Result |
| --- | --- |
| SQLite integrity | `ok` |
| File size | 335,187,968 bytes |
| SHA-256 | `6a00744b13b2e518f9ea8974c47ec25b08530da4af8f7ec70a2a9e4f49f21fba` |
| Expected hash | Matches external ETL `reports/v1.4_medications_2026-10-13/build_manifest.json` |
| Persons | 2,984: Florence 2,682; Rennes 201; Tampere 101 |
| Clinical records | Measurement 580,588; observation 53,015; condition 41,080; procedure 48,313; drug exposure 1,447; death 383 |
| Observation periods | 2,978; six people have no period |
| Concepts | 304 referenced/project concepts; not a full vocabulary distribution |
| Provenance | 919,777 fact provenance rows; no duplicate `(omop_table, fact_id)` keys found; person-level site provenance agrees with site counts |
| Medication companions | 11,907 evidence rows; 13,367 rows in the class feature view, including parent roll-ups |
| Study metadata | `cohort` and `cohort_definition` both empty; endpoint/censor tables absent |
| Asset metadata | `image_occurrence` absent; separately ingested imaging excluded from this candidate |
| Other metadata | `smash_release_metadata` includes a build manifest; `cdm_source` is empty |

The database identifies its scope as paired clinical mappings without PostgreSQL results/endpoint ledgers or separately ingested imaging. The RC builder's source confirms this intentionally limited scope. **This particular file can support clinical inventory and full-history overlap reports now; it is not the full ETL database or a complete supervised dataset release.** A search including ignored files in `K:/SMASH_DATA/smash-etl` found clinical RC snapshots and older PostgreSQL dumps, but no complete v1.4 SQLite snapshot. The user confirmed the complete v1.4 database will be available soon and authorized these existing inputs for development. Observation periods are first-to-last clinical envelopes and must not be substituted for endpoint censoring or clinical baseline dates.

The main file's size/mtime stayed stable during the recorded audit. It uses WAL mode with a zero-byte WAL observed. Release production should publish a finalized standalone snapshot: a main-file hash is insufficient if committed content is still in a nonempty WAL. SQLite documents consistent snapshots through its [Backup API](https://sqlite.org/backup.html) and the [WAL lifecycle](https://sqlite.org/wal.html). Finalize and hash the distributable snapshot in ETL; never checkpoint or modify a user's source database from the exporter.

### Existing overlap and cohort evidence

Independent read-only grouping reproduces the WP2 RC3 report:

| Exact site presence | Variables |
| --- | ---: |
| All three sites | 31 |
| Florence + Rennes only | 21 |
| Florence + Tampere only | 13 |
| Rennes + Tampere only | 2 |
| Exactly two sites, total | 36 |

Here a variable is `(fact table, target concept_id)` with at least one fact in each site, over the entire clinical history. Concept 0 and cohort-management concepts are excluded. Demographics, death and class-derived medication features are outside these counts. The 31 comprise 23 measurements, six conditions, one observation and one procedure. These are **overlap candidates**, not 31 proven comparable baseline predictors.

WP2's existing v1.4 split CSV has 2,984 rows: SHARE-TRAIN 2,145; SHARE-PILOT 537; RENNES-TRAIN 161; RENNES-TEST 40; TAMPERE-TRAIN 74; TAMPERE-PILOT 27. It has not been verified as a cohort companion for this RC3 hash. The current exporter calls SHARE-PILOT and TAMPERE-PILOT “TEST” internally. The new client must expose the canonical names and the study role separately; any `florence_test` or `tampere_test` alias needs an explicit release/study definition.

Detailed aggregate evidence: [v1.4rc3-audit.json](reviews/2026-10-13/v1.4rc3-audit.json). These are reference counts for the partial candidate, not acceptance counts for a fuller database. No patient-level exports were written by this review.

## 3. Issues to resolve in the design

| Issue | Required treatment |
| --- | --- |
| Reviewed RC3 is partial | Locate or publish the full ETL-generated `.db`, including cohort memberships, clinical anchors and endpoint/censor tables. Do not redesign the normal exporter around missing components of this candidate or add mandatory clinical sidecar reports. |
| “Common” is ambiguous | Report exact three-site overlap and **exclusive** two-site overlap, grouped by pair. Separately assess units, acquisition context, ascertainment and landmark coverage. Distinguish “observed”, “comparable”, and “export-enabled”. |
| Equal concept IDs can hide different variables | Registry keys need table, concept, value type and clinical context. Medication observation 3021806 holds different class histories; reducing it to one category loses class identity. Use the RC3 medication class companions with distinct class/status/context fields. |
| Source availability is not prediction availability | Preserve event/assessment time, date precision, source phase and availability status where provided. Never include a post-index exam because its result is broadly called “baseline”. Keep same-day policy explicit. |
| Positive-only OMOP facts cannot establish negative answers | Missing hypertension/arrhythmia/procedure facts mean no documented positive in the selected window, not necessarily “No”. Produce an evidence indicator or a tri-state clinical status where explicit negatives/ascertainment exist. |
| Units and measurement meaning | Never aggregate known-unit and unknown-unit values as though equivalent. Partition by canonical unit and context; convert only reviewed compatible units. Retain source unit, conversion and QC information. Assay differences, rest/provoked gradients and indexed/absolute quantities may remain separate. |
| Operators and literal grades | Check numeric/text encodings, inequality thresholds and ordinal categories. All loaded measurement operators are currently null/0; their absence does not establish that the source had no inequalities. Do not average NYHA/MR class IDs or treat thresholds as exact values. |
| Repeated records dominate distributions | Default comparison to one selected value per person at a fixed baseline. Full-event summaries are an explicit secondary view with both patient N and fact N. Annual training landmarks must not become the default denominator for site comparisons. |
| Held-out data influence model preparation | Descriptive reports may inspect all sites. Freeze model feature definitions and transformations before evaluation; choose coverage thresholds, imputation, encoding and scaling on training data only. Do not silently regenerate `core` columns from test values. |
| Cohorts overlap | `*_all` includes development and held-out people. Persist source split and study role, detect overlap between explicitly declared train/test/evaluation outputs, and keep every person's repeated landmarks in the same partition/fold. An external-site `rennes_all` evaluation can be valid for a Florence-only development study; the protocol must record that choice. |
| Endpoint eligibility changes sample counts | Preserve all selected people for unlabeled baseline exports, including entirely missing feature rows. For supervised tasks, enumerate and report endpoint-specific exclusions. Do not silently require outcome eligibility for a feature-only export. |
| A hash is not a complete validation | Validate bytes, schema, release identity, joins, values, temporal policies, split integrity and selected assets separately. Record PASS/FAIL/UNSUPPORTED/NOT REQUESTED rather than one misleading success flag. |
| File existence is not asset usability | Verify readability, size/hash, sidecars, patient/exam linkage, conversion lineage, dates and QC. Empty directories, corrupt NPZs or unrelated NIfTIs must fail the appropriate checks. |
| Raw and curated modalities differ | Separate modality (`ecg`, `mri`, `echo`, etc.) from representation (`npz`, `nifti`, `dicom`, source PDF/MAT/XLSX). A raw DICOM and its derivative need distinct IDs and a lineage link. |
| Candidate ECG data are not a validated release | Current ECG documentation contains candidate signals with unresolved timing, calibration, lead identity and some patient linkage. Preserve QC states; default modeling exports use released/eligible assets. Candidate downloads can be explicit, but must retain their restrictions. |
| Site ZIPs cannot provide true fine-grained transfer | Use indexed per-asset files or manageable shards. If only a site ZIP exists, announce the complete archive download size and filter locally; do not claim that a subset cohort was the only data transferred. |
| Source paths/provenance can leak or become stale | RC3 provenance uses machine-specific CSV/mapping paths; many OMOP source-value fields are blank. Store portable provenance/annotations in the database and read only its fields. Report unavailable `source_var` as unknown rather than reopening source files. Raw source identifiers and unreviewed free text should not be default model columns or logs. |

A synthetic test confirmed that the sparse exporter correctly excludes same-day/future events under its strict default. It also confirmed that values 10 with a known unit and 100 with an unknown unit become a mean of 55, with `unit_conflict=0`. Fix this before carrying aggregation into the new wide exporter. A patient with no facts is absent from sparse output by design; the new wide output must retain that person.

The older methodology's 2081xx numeric anomaly was not present in RC3 in the reviewed range query. Keep legacy QC findings attached to their original release rather than presenting them as current RC3 failures.

## 4. Release contracts and ownership

### ETL/data-bank publishes

1. A finalized, complete SQLite database with a release ID, schema/contract version and scope/capability flags. Include `cdm_source`, study extensions, concept names and the needed custom concepts. Preserve authoritative PostgreSQL results/clinical tables when materializing SQLite instead of rebuilding only mapped clinical CSVs. Reconcile current facts and regenerated study metadata together; do not merge RC3 with older unrelated ledgers by filename/version alone. A complete OHDSI vocabulary can remain optional if its absence and limited hierarchy capabilities are explicit.
2. Inside that database, a cohort catalog with canonical keys/IDs/names, memberships, site/ID crosswalk, source split, study role and preserved fold assignments. Clinical prediction anchors must be explicit, distinct from cohort import/definition dates.
3. Inside that database, prediction anchors and endpoint/censor tables: age/date basis, synthetic-calendar flag, endpoint definition version, status, prevalence, precision, follow-up provenance and eligibility. Provide explicit unsupported status when a site's endpoint cannot be used; the current code rejects modeled Tampere follow-up, so use a versioned capability rather than a permanent site-name prohibition.
4. Inside that database, portable feature/provenance annotations where needed: stable feature keys, concept/table mapping, category/class/context, units/conversions, source variables, negative ascertainment, date/availability policy and restrictions. Exporter-owned versioned selection/aggregation rules provide sensible defaults. Optional richer embedded annotations must not make descriptive reports depend on an external dictionary or mapping checkout.
5. Inside that database, an asset catalog binding patient/exam/file IDs, dates, modality, representation, paths, expected hashes, processing/QC status and source/derivative lineage to the release. Actual DICOM/NIfTI/NPZ files remain external. A remote archive/shard index can supplement transfer details.
6. For distribution, an external `release.json` with artifact paths, byte sizes, SHA-256 hashes and component versions. Internal metadata identifies the release; the transport manifest hashes the finalized `.db` without a self-referential database-hash cycle. This is a download/integrity contract, not an input report needed for clinical queries.

For RC3, database-only inventory and exact overlap can be implemented and verified immediately. When the supplied file lacks clinical anchors/cohorts/labels, report precisely which operations it cannot support. Normal cohort and supervised exports consume the corresponding tables in the complete `.db`; they never silently attach an unrelated clinical CSV. Develop those paths with synthetic SQLite fixtures now, then verify them against the complete v1.4 snapshot when it arrives. Candidate limitations are not full-release limitations.

### Exporter owns

Reading the database and external asset files, capability checks, cohort/feature selection, index/window application, local validation, reports, reproducible output bundles, credential configuration, Nextcloud retrieval and local cache management. Build inventory, variable intersections and distributions from SQL over the supplied `.db`, and read any richer annotations from its own embedded tables. It may build indexes in its own cache, but it must open the source `.db` read-only and never “repair” it in place.

Recommended modules: `release`, `database`, `cohorts`, `variables`, `landmarks`, `exports`, `reports`, `assets`, `nextcloud`, `credentials`, and a thin `cli`. Use a small shared Python API underneath the commands so report and export semantics cannot drift.

SQLite via the standard library is sufficient for the first database adapter. Keep table identifiers on a discovered/validated allow-list and bind values as parameters. Stream event output and use indexed cohort joins; do not load the whole database per landmark. Stage outputs and publish them only after checks pass. Package dependencies for reporting, cloud, asset format checks and legacy PostgreSQL as separate extras where practical.

## 5. User workflow and defaults

Prefer verbs/subcommands over combinations of unrelated top-level flags. Support the user's intent through a small documented workflow. Examples are proposed syntax, not available commands:

```text
omop-exporter configure nextcloud
omop-exporter releases list
omop-exporter download database --release v1.4
omop-exporter cohorts list
omop-exporter validate --assets all
omop-exporter report inventory --out ./reports/inventory
omop-exporter report overlap --out ./reports/overlap
omop-exporter report distributions --vars core+two-site --index baseline --out ./reports/distributions
omop-exporter export --cohort florence_train --out ./data/florence_train
omop-exporter export --cohort florence_test --out ./data/florence_test
omop-exporter export --cohort rennes_all --out ./data/rennes_all
omop-exporter export --cohort florence_train --index annual --out ./data/florence_train_annual
omop-exporter export --cohort tampere_test --format events --out ./data/tampere_test_events
omop-exporter download assets --cohort rennes_all --modality ecg --representation npz
omop-exporter download assets --cohort tampere_all --modality mri --representation dicom
omop-exporter export --cohort rennes_all --assets ecg:npz --asset-mode reference --out ./data/rennes_multimodal
```

`florence_test`/`tampere_test` resolve only when an explicit approved alias exists. The catalog should display the current canonical SHARE-PILOT/TAMPERE-PILOT labels and requested analytical role, rather than infer a test definition. Accept any discovered OMOP cohort by canonical key or ID, not just the example aliases. Accept underscores/hyphens/case consistently but fail on ambiguous or unknown selectors.

The download example uses final `v1.4` for the intended future workflow. During development require explicit `--release v1.4rc3 --allow-prerelease`; downloading “latest” must not silently switch a locked local release. An existing local file can be registered with `omop-exporter release use /path/omop.db`. Read its release metadata/capabilities directly. An optional `--manifest /path/release.json` supplies trusted expected checksums; absence of that transport manifest must not prevent database-only clinical reports.

| Setting | Proposed default |
| --- | --- |
| Format | Wide tabular CSV; events and legacy sparse views explicitly selectable |
| Variables | Deterministic `core` set resolved from the selected database and versioned exporter rules; lock this definition for a study. Exactly-two-site features added with `core+two-site` or a named pair set; custom list/file supported |
| Row grain | One person and fixed baseline for feature-only output; explicit `(person, endpoint, landmark)` grain for supervised/annual tasks |
| Index policy | Fixed clinical baseline; annual indexes opt-in for approved training members only, initially baseline plus up to five annual anniversaries while at risk |
| Time boundary | Strictly before index unless release metadata establishes a reviewed same-day availability policy; record the policy and excluded baseline-day coverage |
| Lookback | Most recent eligible value in the previous five years for time-varying measurements; registry overrides for immutable attributes and explicit history features; never treat five years as a universal validity rule |
| Value selection | Latest eligible exam/value in canonical units; same-exam duplicates resolved using dictionary rules; unresolved ties/conflicts become missing with QC reasons |
| Missing values | Blank/null plus documented semantics; retain all-missing people. No automatic imputation, scaling, outlier removal or categorical ordinal conversion |
| Metadata | `person_id`, site, stable sample/index identifiers and age coordinate; clinical variables have stable names. No default raw source ID, free text or source path |
| Outcomes | Separate labels table when endpoint requested; never use labels or censor dates as predictor columns |
| Optional history | Previous distinct exam value, previous observation age, elapsed time, window summaries and count/recency by explicit option |
| Optional provenance | Long companion `feature_provenance.csv` keyed by sample and feature; concept/unit/source fields can be requested without expanding every default wide column |
| Assets | None unless selected; references by default, copy mode for portable bundles; missing-required-assets error, explicit partial mode with a missing-assets report |
| Existing output | Refuse overwrite; explicit replacement policy with staged atomic publication |

The five-year lookback and strict date boundary are transparent provisional software defaults. Report their impact; variables first measured on the baseline date may otherwise be absent. Clinical review can approve variable/source-specific baseline-day availability without globally admitting future information.

Define “previous” as the previous distinct eligible exam/time point, not the previous row of a UNION. Preserve exact dates/offsets for selection and add age coordinates for model compatibility; avoid reconstructing boundaries from rounded age values. Keep source availability unknown when it is unknown. Never estimate a Tampere anchor or an ECG acquisition date from an unrelated record.

An export directory should contain `data.csv`, optional `labels.csv`, `samples.csv` (roles, anchors and weights), `variables.csv`, optional `feature_provenance.csv`, optional `assets.csv`, a QC/exclusion report, and `dataset_manifest.json`. A study recipe can name outputs `train.csv`, `test.csv`, and `evaluation.csv`; it must validate declared partition overlap. Record release/database hash, embedded metadata/rule revisions, exporter version, resolved config, cohort IDs, resolved variable-set hash, endpoint policy, windows, boundary, ordering, row counts, missingness and output checksums. Deterministic IDs/order and compatible columns must survive sites with completely absent variables. These dictionaries/manifests are exporter outputs, not mandatory WP2 inputs.

## 6. Reports

### Inventory report

Produce HTML and machine-readable CSV/JSON: release/capabilities, populated/empty tables, table column/type dictionary, patients by site/cohort/split, demographics, dated coverage/observation periods, clinical variables by domain, fact counts and distinct-patient coverage, missing numeric/category/unit fields, source provenance completeness and asset availability/QC. Clearly mark absent cohorts/labels/assets in RC3. Reconcile patient/fact denominators, avoid double-counting people in overlapping cohorts, and distinguish eligible supervised sample counts from cohort membership counts.

### Core and two-site report

Implement database-only overlap calculation in reusable functions. The existing WP2 SQL/tests are useful development references, but the exporter must calculate intersections itself from OMOP facts, site/cohort metadata and `concept` in the supplied `.db`. Publish a three-site table and a second combined two-site table with a site-pair column, optionally separate pair tabs. Each row includes table/concept/name, category/class/context where available, per-site patient/fact N and coverage, recorded units, available embedded source lineage and comparability restrictions. Missing optional source-variable annotations must not stop the report.

Maintain an exact full-history view comparable to the current 31/36 counts for this candidate, and a separate landmark-eligible view when clinical anchors are present. Resolve `core` from the database plus versioned exporter rules, expose the precise included/excluded variables, and freeze its schema in the study/export manifest so test/export commands do not alter columns based on observed values. Apply embedded clinical restrictions where present; mark unresolved equivalence clearly. Database-derived structural overlap may use all sites' concept availability, but outcome-sensitive selection and learned transformations remain training-only. Demographic essentials can be a clearly listed companion feature set, without silently adding them to the exact-concept overlap count.

The existing WP2 report reads machine-specific curated/mapping files to enrich source notes. Do not carry that dependency into the exporter. Use database provenance/embedded annotations if present, otherwise display the available OMOP source fields and mark unavailable detail explicitly. No WP2 report, WP2 import, mapping directory or source CSV is needed to run the new report.

### Distribution report

Use the same database-derived variable resolver, unit/availability rules and value selector as exports. Default to one person/variable at the fixed baseline, with optional full-history/fact-weighted summaries labeled separately. If the supplied candidate lacks valid anchor tables, offer full-history descriptive distributions and mark baseline mode unsupported. A complete ETL `.db` supplies the necessary clinical anchors internally.

For continuous variables, include eligible patient N, available patient N, numeric N, missing N/%, mean, sample SD, min, Q1, median, Q3, IQR = Q3 − Q1, max, canonical unit and QC/exclusion counts. Document the quantile interpolation method; a single observation has undefined sample SD. For categorical/ordinal variables, show category counts/proportions and missing/unknown status rather than calculating means of concept IDs. Presence-only facts need documented-positive coverage, not a fabricated negative denominator.

Include a bar plot for every reported variable: aligned histogram bars with shared bins/units and within-site proportions for continuous variables; grouped category/proportion bars for categorical variables; documented-positive/coverage bars for presence features. Supplement continuous variables with box plots for median/IQR when useful. A mean-only bar hides distributions. Never pool incompatible units or assay/context definitions just to draw a comparable plot. Shared histogram bins are a descriptive report choice, not a fitted model transformation. State denominator, value-selection policy, bin edges and missingness on the plot or linked dictionary. Export HTML plus PNG/SVG and CSV/JSON statistics; avoid free-text source values and patient identifiers in plots.

WP2's `build_cohorts_v1_4.py` summary labels min–max as “IQR”. Do not reuse that calculation: implement actual quartiles and IQR with a hand-checkable fixture.

## 7. Asset validation and multimodal exports

Read patient/exam asset records from OMOP imaging extensions or an embedded `smash_asset` catalog in the complete database. The actual files stay adjacent or in the user's cache. An optional remote bundle manifest describes archive/shard layout and transfer checksums; it is not a substitute for database patient/cohort/exam linkage. An adjacent directory listing alone cannot tell the client which patient/cohort a file belongs to, whether it is an accepted derivative, or when it was available.

Minimum asset fields: `asset_id`, release/schema version, `person_id`, site, exam ID, modality, representation, acquisition date/age and precision, availability status, relative path, size, SHA-256, bundle/shard ID, source/derived-from IDs, processing/version/config, required sidecars, QC status and reason. DICOM entries also need study/series identity and expected instance inventory; NIfTI entries need conversion lineage, geometry/orientation and sidecars; ECG entries need schema version, channel/lead identity, masks, rate/time axis, units/calibration and synchronization status.

Validation layers:

1. Manifest/schema/release binding; duplicate/unmatched person and exam links; representation and expected-file coverage.
2. Resolved path containment, readable regular file or indexed series, byte size and checksums for selected expected artifacts. Symlink/junction escapes must fail.
3. Format checks: NIfTI header/dimensions/affine and required sidecars; NPZ load with `allow_pickle=False`, expected arrays/shapes and valid mask/time/lead consistency; DICOM series membership/instances and declared modality.
4. Modeling eligibility: matched patient, usable index/date/availability, accepted QC and applicable study role. Technical validity must remain separate from clinical acceptance.

Modeling selection should not join all patient files indiscriminately. Resolve assets by person, exam, modality, temporal window and eligibility. Preserve multiple eligible examinations as a linked asset list; do not multiply tabular rows by the number of series/files. Record assets shared across multiple training landmarks without physically duplicating them per row.

Reference mode writes asset IDs and relative paths under a declared asset root with hashes; it requires that root at use time. Copy mode produces a self-contained `assets/` tree and includes sidecars, with lineage and checksums. Both have explicit absent/held/unsupported modalities. A requested multimodal export should fail if required assets are unavailable; an intentional partial export records missingness and must not implicitly drop patients based on modality availability.

Support raw DICOM and curated NIfTI/ECG independently. Original DICOM metadata can contain identifying information: keep original/raw representations an explicit controlled choice and record de-identification status. Source filenames and raw headers should not flow into normal model tables or public reports.

Current ECG artifacts are candidates, not universally validated clinical signals. The corrected-ID Florence, current Tampere bundle/page, and Rennes collections have different date/calibration/linkage limitations. Old collections must not be combined with their replacements; the index must distinguish canonical records, superseded derivatives and quarantined/mixed-patient records.

## 8. Nextcloud and credential design

Use authenticated HTTPS WebDAV, with a named user configuration and an app/device password. Nextcloud documents authenticated file paths under `/remote.php/dav/files/{user}/`, `PROPFIND` listing and `GET` downloads in its [WebDAV API](https://docs.nextcloud.com/server/latest/developer_manual/client_apis/WebDAV/basic.html); device passwords can be revoked separately through [connected-device settings](https://docs.nextcloud.com/server/latest/user_manual/en/session_management.html). Verify the deployed server's version, authentication and mounted release path during setup; its configuration was not inspected in this review.

Prefer the operating system's credential vault through [Python keyring](https://keyring.readthedocs.io/en/latest/), including Windows Credential Locker, instead of maintaining an encrypted file and its decryption key in the application folder. Save only URL, username, remote release root, local cache and a vault reference in the config. Require a supported secure backend; never silently fall back to plaintext. Provide explicit environment-based credentials for unattended/container use. If a portable encrypted credential file is required, make it an optional backend with a separately supplied unlock secret and vetted encryption, not a key stored beside the ciphertext. Do not log secrets, include them in command arguments or persist them in dataset manifests.

Publish a curated transport release index/manifest on Nextcloud. WebDAV listings can confirm remote existence, but they cannot replace clinical cohort/asset records in the `.db` or trusted expected SHA-256 values. Treat ETags as remote version markers, not database integrity hashes. Keep participant/asset manifests access-controlled; the downloader uses the user's existing permissions and never creates shares or uploads by default.

Downloader requirements: release pinning; selection by cohort/modality/representation; dry-run list/size estimate; local cache keyed by release/artifact identity; bounded retries/timeouts and connection concurrency; `.part` staging; resume only when supported and the remote object identity is unchanged; checksum verification; atomic completion; sufficient-space checks; and a download receipt. If range resume is unsupported, restart safely. Validate archive entries and extraction size/path limits; reject traversal, absolute paths and unsafe links. Verify extracted files against the asset index rather than relying only on ZIP CRC.

Start with immutable database and prebuilt site/representation bundles. Add selective files/shards as the manifest allows. A request for `rennes_all` ECG NPZ may resolve to a full Rennes archive; a request for `rennes_test` should download only its files where available, or explicitly report that a larger shared archive is required. Do not infer archive names from cohort strings: resolve IDs and remote paths from the manifest.

After initial setup, the target experience is: download/register one release, validate requested components, select a cohort, export data. Add an opt-in recipe that fetches missing required components and exports in one operation once the separate commands are reliable. Network retrieval should never happen unexpectedly during a local-only export.

## 9. Implementation backlog and acceptance gates

| Phase | Deliverable | Acceptance gate | Dependencies |
| --- | --- | --- | --- |
| 0 — full database contract | Define the forthcoming complete SQLite contract and synthetic fixtures; embed cohort/anchor/endpoint/asset metadata; preserve legacy contracts | RC3 candidate scope is distinguished from the full release. A complete `.db` is the sole clinical input. An ETL checklist owns full snapshot packaging, aliases and external asset publication. No mandatory WP2 reports or clinical sidecars. | ETL/data-bank coordination; existing inputs sufficient to start |
| 1 — local foundation | Installable package/CLI; read-only SQLite release adapter; explicit release selection; validation; inventory/cohort discovery; legacy PostgreSQL adapter | Install/help work in a clean environment. RC3 hash/counts/integrity reproduce audit. Missing cohorts/labels are reported as unsupported. Unknown selectors, mismatched manifests, partial writes and corrupt DBs fail clearly. | Phase 0; existing `.db` sufficient for inventory |
| 2 — variables and reports | Database-only overlap logic; embedded annotation reader; exporter feature rules; exact vs eligible coverage; distribution stats and all-variable plots | On the partial RC3, reproduce 31 three-site and 21/13/2 pairwise variables. Full DB has independently calculated counts. Run with only `.db`, exporter and config. True IQR and denominators pass fixtures; unit ambiguity remains explicit. | Phases 0–1; embedded anchors for baseline reports |
| 3 — standard exports | Wide baseline CSV; compatible event export; general cohort selection; locked schema/rules; labels/provenance outputs; study recipe | Read memberships/anchors/labels directly from `.db`. Verify synthetic complete fixture now, then real v1.4. One baseline row per eligible selected person including all-missing rows. Identical feature columns; no post-index values, implicit negatives or declared train/test overlap. | Phases 0–2; fixtures for development; full v1.4 for integration acceptance |
| 4 — longitudinal configuration | Annual training landmarks, endpoint-specific eligibility, prior-exam/age/recency/windows, sample weights | Holdout people cannot receive annual training samples. All landmarks for a person stay in one partition. Date precision, leap years, same-day policy, conflicts and horizon censoring have verified behavior. No accidental endpoint collapse. | Phase 3; compatible endpoint ledger |
| 5 — multimodal local datasets | Embedded asset catalog reader; checksum/format/eligibility validation; reference/copy exports; raw/curated representation selection | Missing, corrupt, unmatched, unsafe-path and temporally ineligible assets handled explicitly. Copy bundle is portable with asset sidecars and validated lineage. No patient-row explosion or silent modality-based exclusions. | Phases 0–3; database asset catalog and external derivatives |
| 6 — secure downloads | Nextcloud setup/vault; release index; database/bundle/asset retrieval, retries/resume/cache | Fake WebDAV tests plus authorized integration smoke test cover permissions, corrupt content, partial transfer, changed ETag, missing files and hostile archive paths. Secrets absent from logs/config/exports. Offline reuse works. | Phases 1 and 5; approved remote manifests/bundles |
| 7 — collaborator workflow | Quickstart, recipes, Python API docs, clean-install checks, end-to-end release acceptance | On a fresh machine: configure, fetch pinned release, validate, report, export Florence development/holdout and Rennes/Tampere selections; reproduce hashes/contracts and explain unsupported labels/assets. Final v1.4 replaces RC only when ETL release gates pass. | All preceding applicable gates |

Phases 2 and 3 should deliver an immediately useful local exporter before advanced longitudinal options. Database-only download can be delivered early in phase 6 once the release manifest is fixed; it need not wait for all ECG packaging. Full multimodal workflow depends on phase 5. Do not make local reporting wait for final v1.4 promotion.

First implementation slice: package entry point, `.db` registration/read-only adapter, release capability validation and database-only RC3 inventory, alongside a synthetic complete SQLite fixture. Second slice: direct overlap calculation and exporter feature/unit rules with optional embedded annotations. Third slice: wide baseline export from database cohort/anchor tables, then distribution reporting against that same selector. Exercise the existing PostgreSQL event workflow against a historical release only for compatibility; never attach historical ledgers to RC3 as current truth. These slices establish the foundation for cloud retrieval without forcing PostgreSQL/Docker or WP2 setup on collaborators.

Development and final acceptance are separate: unit/contract tests should use small synthetic databases with cohorts, indexes, precision, explicit missing/negative outcomes and asset records. RC3 is the real-data fixture for database discovery, direct reports, units, provenance and partial-capability handling. The older dump is a historical event/ledger contract reference. The forthcoming full v1.4 database is the final end-to-end fixture, with newly calculated cohort/overlap counts; 31/36 is not a hardcoded expected result for that release. No collaborator command should require running any of these fixture generators or WP2 reports.

## 10. Verification and outstanding decisions

Use small synthetic fixtures for time boundaries, mixed/unknown units, explicit negative vs missing evidence, medication-class disambiguation, cohort/split overlaps, equal-day duplicate exams, ordinal/threshold values, censored horizons, entirely missing patients and deterministic output schemas. Test asset/path/checksum/format failures and download recovery separately. Add a read-only RC3 integration check of aggregate counts/hash/overlap; keep its database and patient-level outputs outside Git. Preserve a legacy event-contract fixture while extending provenance fields.

Current verification was limited to read-only SQLite inspection, full SQLite integrity, external manifest SHA-256 comparison, aggregate overlap recalculation, source/provenance/unit checks, syntax parsing of seven exporter scripts and a synthetic sparse-export check. No PostgreSQL end-to-end run was performed. The default Python environment lacks PyYAML, so `main.py --help` currently fails at import; that is an environment/setup finding, not proof that the documented workflow fails once its requirements are installed. No Nextcloud login/download, exhaustive asset validation, clinical-equivalence assessment or baseline distribution report was attempted.

Decisions for implementation, with proposed defaults already given above:

- Agree the forthcoming full v1.4 SQLite table contract with its ETL producer; develop against existing RC/legacy inputs and synthetic fixtures in the meantime. Resolve canonical PILOT versus analytical TEST aliases and preserve frozen membership/folds.
- Approve exporter feature rules and any embedded comparability/availability annotations, including baseline-day sources, units/assays, positive-only evidence and medication history/class contexts. The report can calculate and list unresolved candidates directly from the database while model export requires defined behavior.
- Confirm which cohorts have usable endpoints. Permit unlabeled feature/transfer datasets where outcomes are unsupported; do not permanently encode “Tampere has no outcomes” in the exporter.
- Confirm the Nextcloud release root and server authentication, and whether distribution offers per-file assets, shards or only site archives. Publish the release index before implementing filename assumptions.
- Define the ECG/NIfTI/DICOM accepted-versus-candidate release status and asset-date/linkage completeness. Packaging and transfer can begin independently of clinical feature acceptance, but model eligibility must remain explicit.

The plan uses sensible provisional defaults without requiring these decisions to block database validation and descriptive reporting. Supervised exports, baseline-sensitive features and multimodal modeling should only claim support when their specific release contracts are available and validated.
