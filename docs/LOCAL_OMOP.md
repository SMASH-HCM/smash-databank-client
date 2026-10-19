# Local OMOP reports and datasets

Open **3. Local OMOP** after downloading or selecting a database. This section works without a login, internet connection or remote manifest. It is greyed out unless the selected SQLite file is readable and contains an OMOP `person.person_id` column. A corrupted/non-OMOP `.db` file does not enable it.

At startup the app rechecks its selected database. If unavailable, it checks registered download receipts and the confirmed download folder at the fixed release/artifact depths (at most two subdirectories). A single readable OMOP database is selected and remembered. Full ETL `results__cohort` tables are resolved using the embedded `smash_export_metadata` schema map; ordinary duplicate table names still fail as ambiguous. Multiple candidates require **Validate → Select a local OMOP database**; no version is silently preferred. Unrelated drives and project folders are not searched. You can also launch `smash-hcm-databank-client.exe menu --db <path>`.

See [BASELINE_AVAILABILITY.md](BASELINE_AVAILABILITY.md) for the agreed baseline-day protocol, excluded treatment/outcome roles, strict-before controls and remaining intraday limitations.

## Reports

**View / save summary reports** has seven built-in templates, calculated on demand from the local database:

| Report | Contents |
| --- | --- |
| OMOP inventory | Table/view counts, columns, variable/concept counts by site, patient counts by site and cohort membership counts |
| Cohorts | Embedded cohort definitions and distinct membership counts |
| Endpoints | Distinct people by recorded endpoint, outcome status and site |
| Variable overlap | CORE (three-site) variables and an exclusive two-site table |
| Numeric distributions | CORE plus two-site observation counts, mean, median, quartiles, IQR, min, max and population standard deviation, separately by site and unit |
| Patients | One row per person: observation bounds/ages, visits, logged file counts, baseline/training-index availability, censor and endpoint summaries |
| Feature sets | Named sets and complete source concept lists, including explicit category-family mappings |

Reports can be viewed in the terminal and saved as JSON/CSV. Endpoint/cohort ledgers that are missing or empty are reported as **UNAVAILABLE**; outcomes and cohort memberships are not invented. Distribution counts represent observations, including repeat observations per patient, over the full loaded history. Unknown units remain a separate unit-0 group; no unit conversion or pooling across units occurs. These descriptive summaries are not baseline modelling datasets. Distribution plots remain future work.

Examples:

```powershell
.\smash-hcm-databank-client.exe report inventory --db .\OMOP.db --out .\reports\inventory
.\smash-hcm-databank-client.exe report endpoints --db .\OMOP.db --out .\reports\endpoints
.\smash-hcm-databank-client.exe report distributions --db .\OMOP.db --out .\reports\distributions
```

## Choose variables once and reuse them

**Export tabular / event datasets** lets you select one or several existing cohorts, a variable set, output format, temporal options and DATA_DIR. Presets include ALL, CORE, CORE plus two-site, two-site only, CORE measurements, eight starter measurements, all measurements, all conditions, ECG-labelled measurements and explicit consolidated CORE. CORE is exact `(fact table, concept_id)` overlap, not a claim of clinical equivalence. [DATASET_EXPORTS.md](DATASET_EXPORTS.md) lists the concepts, counts, options and caveats.

The ECG-labelled preset selects only measurement concepts whose names explicitly mention ECG/EKG/electrocardiography, QRS, QTc, or QT/PR/RR interval. It excludes ECG diagnoses/procedures and generic heart rate without an ECG-specific name. It is a transparent name filter, not a complete source-modality catalogue; use an inspected custom list for a definitive model feature set. A preset with no matching variables or insufficient three-site metadata is disabled with a reason.

Choose **Choose variables from the database list** to filter by concept name, ID or fact table, tick variables, and give the list a name. The app saves a JSON list under its profile's `variable_sets` folder, containing table/concept pairs, names and release metadata. Saved sets appear in future sessions. You can also load a JSON file copied from a collaborator. Empty, invalid or unsupported selections are rejected; existing files are not overwritten.

Each generated dataset includes `variable_set.json`. Tabular datasets also include `variables.csv`, `samples.csv`, feature provenance and a dataset manifest with database/output checksums. Reuse the exact JSON list to keep training and test columns consistent:

```powershell
.\smash-hcm-databank-client.exe export --db .\OMOP.db --format tabular --cohort FLORENCE-TRAIN --vars shared-clinical --out .\train
.\smash-hcm-databank-client.exe export --db .\OMOP.db --format tabular --cohort RENNES-TEST --variables-file .\train\variable_set.json --out .\test
.\smash-hcm-databank-client.exe export --db .\OMOP.db --format events --cohort RENNES-TEST --variables-file .\train\variable_set.json --out .\events
```

Saved concepts absent from another release/site are retained as blank tabular columns, with a menu notice. Concept IDs alone do not resolve unit/context conflicts; export quality rules still apply. Menu batches freeze one ordered list, preserve database memberships and write `DATA_DIR/<group>/train.csv,test.csv` with split audit subfolders, or `DATA_DIR/event_stream/<cohort>/`. CLI `--data-dir` uses the same layout; explicit `--out` still writes a new low-level bundle with `data.csv` or `omop_events.csv`. The legacy Python `export_cohorts` bundle helper retains its `cohort-<id>` API for existing callers. Failed batches publish no partial datasets. Default tabular output has four metadata columns and one column per source feature; only explicitly configured families/history change that schema.

Tabular exports require populated clinical cohort memberships and baseline anchors. They use the fixed clinical baseline, eligible evidence only on the exact baseline day, using the versioned post-assessment/pre-intervention mask. Earlier-history carry-forward requires explicit latest-history mode and a lookback, and feature-only columns; absence remains missing. Annual training landmarks and outcome-label exports are not inferred. Event streams contain full history, including post-baseline observations, and require downstream prediction cutoffs. Partial RC1/RC3 snapshots can still support inventory/overlap/event exploration when their cohort/anchor/endpoint ledgers are unavailable. Full v1.4 exports require those embedded tables.

## Local settings and downloads

On first use the directory is red **[NO] &lt;unset&gt;**. Confirming a download location creates it and saves it in nonsecret `state.json`, under `~/.smash/omop-exporter` for the executable. Login passwords remain in the chosen OS credential vault, session or explicit `.env`; paths do not belong in the credential vault. The same saved location survives application upgrades and changes in launch folder. Startup creates a previously confirmed directory if an older version saved it before creating it; an inaccessible location stays red with a message. No unconfirmed home-directory default is created.

The menu retrieves the fixed `/databank/manifest.json` path with no filename prompt. The server administrator still needs to publish the actual manifest; the bundled README example is not automatically treated as the databank catalogue. All manifest, database, CSV and archive downloads show transferred bytes, percentage (when total size is known), transfer speed and ETA. Completion follows size/hash checks and atomic publication. Cached entries are labelled as verified cached files. Failed transfers remain failures; unknown totals are shown explicitly. Command-line download progress goes to stderr, leaving JSON stdout machine-readable.

The default menu uses exact-day snapshots. Opt-in history is configurable in the menu or with `--tabular-mode latest-history --lookback-days <N>`. Optional previous-value/recency/count/mean/min/max columns require explicit selection. Events can be configured by domain, calendar dates, baseline mask/lookback and source metadata. Reports use `DATA_DIR/reports/<kind>.txt` and tables, with JSON companions. Rolling/annual or shifted prediction indices remain separate. Source SHaRe names display as FLORENCE; source names/IDs are retained. PILOT and TEST remain distinct memberships and can use the held-out `test.csv` filename.
