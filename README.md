# SMASH-HCM Databank Client

Download SMASH-HCM research data, inspect a local OMOP database, and export reproducible datasets for modelling. Use the arrow-key menu for occasional work, or the command line for repeatable exports.

**[Download the client](https://github.com/SMASH-HCM/smash-hcm-databank-client/releases)** · **[Request data access](https://forms.gle/nNDDBbX8ah15dNcs8)** · **[Documentation](docs/README.md)**

## What is the SMASH-HCM databank?

The databank brings together harmonized hypertrophic cardiomyopathy data from **FLORENCE, RENNES and TAMPERE**. A versioned **OMOP SQLite database** contains clinical records and, where supplied by the release, cohort memberships, baseline anchors, endpoints and links to external assets. Larger data such as ECG signals, MRI and Echo files are distributed separately, often as cohort/modality ZIPs. Raw and processed representations may both be published; availability depends on the release.

**TODO: URL for the SMASH-HCM Databank paper.** No manuscript is bundled with the client yet. Cite the exact data release and client version used in an analysis alongside the paper when available.

The client connects to the [SMASH-HCM server](https://smash-hcm.ucd.ie); the shared Nextcloud folder is `databank`. Access requires an approved account. The client reads published files; data curation and ETL remain upstream responsibilities.

## Get started

### Portable application: no Python installation needed

1. Open [Releases](https://github.com/SMASH-HCM/smash-hcm-databank-client/releases) and select a suitable version. **Prereleases are testing candidates**; prefer a stable release for routine work when one is available.
2. Download the ZIP for your computer:

   | Computer | Filename ending |
   |---|---|
   | Windows x64 | `windows-amd64.zip` |
   | Mac, Apple Silicon | `macos-arm64.zip` |
   | Mac, Intel | `macos-x86_64.zip` |
   | Linux x64 | `linux-x86_64.zip` |

3. Extract the **whole ZIP**. Keep the executable beside its `_internal` directory. Run `smash-hcm-databank-client.exe` on Windows; from a terminal on Mac/Linux run `./smash-hcm-databank-client`. Native Mac bundles are unsigned/not notarized; see [platform notes](docs/BINARY_RELEASES.md).
4. Choose **Setup** to enter your Nextcloud username and app password. Prefer OS credential-vault storage when offered. Confirm a protected local download directory; the suggested home directory is only used after confirmation.
5. Check the connection and retrieve the manifest. On later launches, authenticated startup checks offer **Check for data updates?** Choosing Yes refreshes the manifest and offers changes to tracked downloads. You review the files and choose archive, keep or replace before an update.
6. Choose **Download**: the OMOP database, published tabular datasets, cohort/modality ZIPs, or selected manifest files/folders. Byte count, speed and ETA are displayed, and completed transfers are checked against manifest size and SHA-256.

The menu groups work into **Setup → Download → Local OMOP → Validate**, with **Data Access Request** and **Exit** alongside them. Unavailable options explain their prerequisites. Local OMOP work is available once a readable SQLite database is downloaded or selected; it works offline without Nextcloud credentials. Use **Validate** to recheck downloaded files and their presence later.

The server administrator must publish `manifest.json` before catalogue downloads work. Its entries describe paths, versions, checksums, sizes and cohort/modality tags. The client cannot offer files absent from that manifest. [Login, manifest and download details](docs/NEXTCLOUD.md) · [Update behaviour](docs/UPDATES.md).

### Python installation: Windows, macOS or Linux

Use Python 3.9+ in a virtual environment. Download the `.whl` from the same release, then install it with the menu and credential-vault extras. Replace `VERSION` with the downloaded filename's version:

```sh
python -m venv .venv
# Activate: Windows PowerShell: ./.venv/Scripts/Activate.ps1
# Activate: macOS/Linux: source .venv/bin/activate
python -m pip install "./smash_hcm_databank_client-VERSION-py3-none-any.whl[ui,secure]"
smash-hcm-databank-client setup
```

You can also run `python -m smash_hcm_databank_client`. To install from a source checkout, use `python -m pip install ".[ui,secure]"`. Minimal scripted/local-database use requires no third-party runtime dependencies; PostgreSQL, psycopg and Docker are unnecessary. [Full installation guide](docs/SETUP.md).

**Upgrading from omop-exporter:** in the same Python environment, uninstall the old distribution with `python -m pip uninstall omop-exporter` before installing the new wheel. The new distribution exposes only `smash-hcm-databank-client`. Existing download folders, saved profiles and credentials are retained. Application code now lives in `src/smash_hcm_databank_client/`. Replace old `python -m omop_exporter` invocations with `python -m smash_hcm_databank_client`; older feature-set identifiers still work.

## Inspect and report on the OMOP database

All analysis reads the local `.db` directly, read-only. It does not need a WP2 report or checkout. The file must actually be **SQLite**: renaming a PostgreSQL dump to `.db` does not convert it. Database and asset versions are independent of the client version.

Select a database under **Validate → Select a local OMOP database**, then open **Local OMOP**. For scripts, pass `--db` explicitly (or set `SMASH_DATABANK_DB`):

```sh
smash-hcm-databank-client validate --db ./data/OMOP.db
smash-hcm-databank-client cohorts list --db ./data/OMOP.db
smash-hcm-databank-client report inventory --db ./data/OMOP.db --data-dir ./analysis
smash-hcm-databank-client report overlap --db ./data/OMOP.db --data-dir ./analysis
smash-hcm-databank-client report patients --db ./data/OMOP.db --data-dir ./analysis
```

Available reports: **inventory, cohorts, endpoints, overlap, distributions, features and patients**. They cover tables/columns, site and cohort counts, exact three-site/two-site variable overlap, numeric summaries separated by concept/unit/site, feature lists, and one-row-per-person summaries. Patient summaries include observation bounds, visits, logged asset counts, baseline and endpoint information where available. Missing ledgers are reported explicitly; catalogue counts are not proof that files exist. Reports are written under `analysis/reports/`. Distribution tables are implemented; automatic per-variable plots remain planned.

## Export a standard tabular dataset

The default is deliberately simple: **one row per patient at the recorded baseline date, one column per selected clinical feature**, plus `person_id`, `site`, `cohort` and `snapshot_date`. Values must be eligible on that day. There is no implicit averaging, historical carry-forward, scaling, log transform, imputation or random splitting.

Use **Local OMOP → Export** to select cohort(s), variables, format and configuration. The database supplies memberships and anchors. SHaRe source labels are presented as **FLORENCE**. TRAIN/TRAINING produces `train.csv`, TEST/PILOT produces `test.csv`, EVAL/EVALUATION produces `evaluation.csv`, and ALL produces `all.csv`; the original cohort ID/name stays in provenance. Cohorts remain distinct.

For command-line examples below, first use `cohorts list` and substitute the exact names or numeric IDs in your release. These examples assume it contains `Rennes Training` and `Rennes Test`:

```sh
smash-hcm-databank-client export --db ./data/OMOP.db --format tabular --cohort "Rennes Training" --vars shared-clinical --data-dir ./analysis/core
smash-hcm-databank-client export --db ./data/OMOP.db --format tabular --cohort "Rennes Test" --variables-file ./analysis/core/RENNES/train/variable_set.json --data-dir ./analysis/core
```

```text
analysis/core/
  RENNES/
    train.csv
    test.csv
    train/    # frozen variables, dictionary, provenance, QC and dataset manifest
    test/
```

Reuse the **training variable list** for test/export runs to preserve columns and order. In a menu batch the schema is frozen across all selected cohorts. Use a new output root for a different configuration; existing datasets are never silently overwritten. Low-level `--out ./new-bundle` instead writes `data.csv` inside a single bundle.

A shortened, fictional example (two selected measurements) looks like:

```csv
person_id,site,cohort,snapshot_date,measurement__4152194,measurement__4108582
101,RENNES,Rennes Training,2020-01-01,120.0,62.0
102,RENNES,Rennes Training,2020-02-01,,58.0
```

`variables.csv` maps columns to names, source tables, concepts and units. Blank cells mean unavailable, withheld or conflicting evidence; they are not assumed normal/zero. Inspect `feature_provenance.csv` and QC counts to distinguish those cases. Labels/targets are **not** included: endpoints need a separately reviewed horizon, censoring and eligibility policy before supervised training.

## Choose clinical features

Friendly menu names and their CLI identifiers are:

| Feature set | `--vars` | What it selects |
|---|---|---|
| Shared clinical features — all 3 sites (CORE) | `shared-clinical` | Exact table/concept pairs observed at all three sites |
| Shared clinical features — at least 2 sites | `shared-extended` | CORE plus exclusive two-site concepts |
| Shared clinical measurements — all 3 sites | `shared-measurements` | Measurement-domain subset of CORE |
| Starter measurements — 8 fixed concepts | `starter-measurements` | Height, weight, BMI, systolic/diastolic BP, LVEF, septal thickness, LVOT gradient |
| ESC Risk-SCD clinical inputs | `esc-risk` | Relevant source concepts plus baseline age; see the definition below |
| ECG measurements | `ecg-measurements` | Name-filtered ECG concepts; does not extract signals from NPZ files |
| All clinical measurements | `all-measurements` | All recorded measurement concepts |
| Recorded diagnoses and conditions | `diagnoses` | Condition-domain concepts |
| All recorded clinical features | `all-clinical` | All observed clinical table/concept pairs, excluding management concepts |
| Clinical features shared by exactly 2 sites | `two-site-only` | Exclusive two-site concepts |
| Shared clinical features — grouped mitral regurgitation | `shared-grouped` | CORE with an explicit categorical MR-grade family |

Counts depend on the database release: **CORE is not hard-coded to 36 features**. Structural overlap does not prove equal units, acquisition context or prediction-time availability. The grouped set addresses one known category-family issue: mild/moderate/severe MR can be different source concepts despite belonging to one clinical variable. It preserves unknowns and conflicts; other families are not inferred automatically. Run `report features` for exact IDs and `report overlap` for site coverage. Old identifiers such as `core`, `core-measurements` and `ecg-derived` still work in scripts. [Full feature definitions and mappings](docs/DATASET_EXPORTS.md).

**ESC Risk-SCD inputs:** the clinical model uses age, maximum LV wall thickness, left atrial diameter, maximum rest/Valsalva LVOT gradient, family history of SCD, NSVT and unexplained syncope. [ESC definitions](https://www.escardio.org/static-file/Escardio/Guidelines/publications/HCMESC%20HCM-Web%20addenda.pdf). The new `esc-risk` set exports seven candidate source concepts (resting and provoked gradients kept separate) plus `baseline_age_years`. This is an **input-review dataset, not a calculated or clinically validated risk score**. Generic syncope is not automatically unexplained syncope, segmental thickness is not proven maximal thickness, and acquisition/history definitions need review. Missing evidence stays missing; same-day unclassified conditions can be withheld by the standard mask. Previously calculated risk scores and ICD recommendations are excluded from this set. [Exact mappings and limitations](docs/DATASET_EXPORTS.md#esc-risk-scd-clinical-inputs).

### Define your own variables

In the menu choose **Choose variables from the database list**, search/select concepts, and save the list for reuse. Alternatively create a JSON file using explicit table/concept pairs:

```json
{
  "schema_version": 1,
  "name": "Blood pressure and LVEF",
  "variables": [
    {"table": "measurement", "concept_id": 4152194},
    {"table": "measurement", "concept_id": 4154790},
    {"table": "measurement", "concept_id": 4108582}
  ]
}
```

```sh
smash-hcm-databank-client export --db ./data/OMOP.db --format tabular --cohort "Rennes Training" --variables-file ./my-variables.json --data-dir ./analysis/custom
```

That produces **3 clinical columns + 4 metadata columns**. Requested concepts absent from this release stay as blank columns. Use the menu catalogue/feature reports to verify concept meaning and units; table identity matters as well as concept ID. [Copyable five-measurement example with optional baseline age](examples/clinical_variables.json) · [Tabular train/test tutorial](docs/TABULAR_TUTORIAL.md).

### Optional history and additional features

| Option | Meaning | Status |
|---|---|---|
| Exact baseline day | Use that day's eligible facts only | Default |
| Two-year lookback | Latest eligible value within an explicit 730-day window ending at baseline | Opt-in; 730 days is an approximation to two calendar years |
| Previous value / recency | Previous distinct observation date; days from previous/latest observation to baseline | Opt-in extra columns |
| Count / mean / min / max | Summaries across eligible, QC-valid observed dates in the window | Opt-in extra columns |
| Log / log-normal | A log transform can reduce positive skew; a log-normal distribution describes values whose logarithms are normally distributed | Downstream modelling; no client option |
| Normalization / imputation | Scaling values or filling missing entries | Downstream modelling; no client option |

```sh
smash-hcm-databank-client export --db ./data/OMOP.db --format tabular --cohort "Rennes Training" --vars shared-measurements --tabular-mode latest-history --lookback-days 730 --history-features previous-value previous-age-days last-age-days count mean --data-dir ./analysis/history-730
```

No extra is automatically applied. History adds columns and changes the question being modelled; a 730-day lookback does **not** move baseline, define a two-year outcome horizon or establish continuous observation. Numeric summaries do not average category IDs or incompatible/unknown units. Fit any downstream transform using training data only, then apply the same transform to test data. [Concise options and modelling example](docs/TABULAR_TUTORIAL.md).

## Export an event stream

An event stream keeps dated clinical facts as rows rather than pivoting them into patient columns. Default fields are:

```text
person_id, domain, concept_id, event_date,
value_as_number, value_as_concept_id, unit_concept_id
```

Example: one patient may have many measurement, observation and condition rows on multiple dates. Rows are ordered deterministically by person/date/domain/concept/fact ID. No resampling or averaging is performed. Optional metadata supplies source text, fact ID/table, site and baseline-relative timing.

```sh
smash-hcm-databank-client export --db ./data/OMOP.db --format events --cohort "Rennes Test" --vars all-clinical --data-dir ./analysis/events-full
smash-hcm-databank-client export --db ./data/OMOP.db --format events --cohort "Rennes Test" --vars shared-clinical --event-scope baseline --event-lookback-days 730 --domains measurement observation --include-event-metadata --data-dir ./analysis/events-baseline
```

Files go under `DATA_DIR/event_stream/<COHORT>/omop_events.csv` with a reproducibility manifest. Full-history mode is descriptive and **includes post-baseline facts**. Baseline scope applies the clinical anchor and conservative availability mask. Use it for baseline prediction experiments; still review source-specific leakage and task eligibility.

For sequence models, build the vocabulary/encoding on training data, respect patient splits, distinguish numeric/coded/presence events, check units, and handle variable-length histories and padding explicitly. Date-only records do not establish within-day clinical order. More events can reflect longer follow-up or site recording practices, rather than worse disease. The stream does not generate labels, endpoint risk sets, missing visits or waveform tokens. [Event configuration and caveats](docs/DATASET_EXPORTS.md#event-stream-configuration).

## Combine ECG/MRI/Echo ZIPs with clinical data

Download the same release's cohort ZIPs and export the matching tabular cohorts. Extract to protected storage, then link assets using an authoritative **OMOP person-ID + asset-path + acquisition-date index** from the release. Never infer patient identity from a filename or row order. Keep each patient's assets in the same train/test split, and exclude assets acquired after the prediction boundary.

The [ECG + tabular tutorial](docs/MULTIMODAL_TUTORIAL.md) walks through downloading, guarded ZIP extraction, defining the required asset index, and producing train/test CSVs with ECG paths. A tested [preparation helper](examples/prepare_multimodal.py) creates these path-linked datasets without copying waveforms into clinical cells. It requires an explicit index and eligibility review; it cannot manufacture missing linkage from the current catalogue. The same approach can link NIfTI or curated Echo files. Automatic extraction/linkage and modality-specific model training are not menu features yet.

## Baselines, indices and landmarks

The standard export uses one fixed **clinical baseline index** per patient from the database anchor ledger. A history window changes which earlier observations can contribute; it does not move the prediction date. Repeated annual training landmarks and endpoint-specific outcome horizons are separate study designs, retained only in the legacy experiment tools. [Indexing and landmarking explained with examples](docs/INDEXING_AND_LANDMARKS.md).

## Prediction rules and current limits

Baseline prediction is **after diagnostic assessment and before new treatment decisions**. Eligible baseline-day measurements can be included; new same-day treatment decisions and outcome/administrative facts are held out. The current role mask is conservative and incomplete because date-only OMOP records do not fully describe intraday availability. Missing/invalid cohort anchors block baseline exports rather than silently dropping patients. Review the output audit files. [Baseline policy](docs/BASELINE_AVAILABILITY.md).

The client validates file bytes and technical database capabilities, not clinical completeness or model validity. Some historical release candidates lack ledgers or have known anchor/data issues; inspect the release-specific reports and [dated validation notices](docs/README.md). Retries/resume, automatic waveform/imaging validation, endpoint-specific labels and annual training indices remain outside the standard client workflow.

Keep credentials, clinical files, exports and patient-level reports in approved protected storage outside Git. Sharing a client executable does not confer databank access.

## Development and releases

```sh
python -m pip install -e ".[dev,ui,secure]"
python -m pytest tests -m "not integration"
python -m build
```

Source code is under `src/smash_hcm_databank_client/`; older PostgreSQL/CSV preparation scripts are in its `legacy/` subpackage. Release/developer utilities live in `tools/`, and collaborator examples in `examples/`.

Unit/workflow tests use temporary synthetic SQLite databases and mocked network responses; no developer-specific drive paths or real credentials are needed. External read-only database checks are optional: `python -m pytest tests -m integration --omop-db ./private/OMOP.db`. Every successful main push publishes a distinct release candidate after tests/native builds; stable releases are reviewed separately. [Tests](docs/TESTING.md) · [Release guide](docs/GITHUB_RELEASE.md) · [All documentation](docs/README.md).
