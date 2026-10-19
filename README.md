# SMASH-HCM Databank Client

Canonical repository: **[SMASH-HCM/smash-hcm-databank-client](https://github.com/SMASH-HCM/smash-hcm-databank-client)**. Package/command names remain `omop-exporter`, the module remains `omop_exporter`, and existing local folders/profiles remain compatible. See the [documentation index](docs/README.md).

SQLite-first tools for inspecting and exporting versioned SMASH OMOP databases. Clinical reports read the supplied `.db` directly, without a WP2 checkout, generated reports or source CSVs. The core package has no third-party runtime dependencies and does not require psycopg, PostgreSQL or Docker.

Version **0.11** adds authenticated startup checks and an opt-in data-update flow, with automatic manifest refresh and archive/keep/replace choices. [Update behaviour](docs/UPDATES.md). Every successful push to `main` automatically produces a uniquely versioned **release candidate** after tests and native platform builds pass. Stable releases use a separate reviewed draft/tag workflow. [Release guide](docs/GITHUB_RELEASE.md).

## Install locally

Collaborators can download ZIPs or Python wheels from [Releases](https://github.com/SMASH-HCM/smash-hcm-databank-client/releases). Testing builds are labelled prerelease; stable builds are reviewed separately. Portable ZIPs include Python and menu/vault libraries. Extract the whole ZIP and run `omop-exporter.exe setup` on Windows or `./omop-exporter setup` on Mac/Linux. The database/assets remain separate downloads. Native Mac builds are unsigned/not notarized. Local builds remain under ignored `dist/binary`.

Python 3.9+ is supported. In PowerShell, from this checkout:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev,secure,ui]"
.\.venv\Scripts\omop-exporter.exe setup
```

Use `pip install .` inside the local environment for the core client only. Metadata and extras are defined in `pyproject.toml`; `setup.py` is a compatibility entry. See [setup and optional dependencies](docs/SETUP.md) for Linux/macOS, configuration and wheel installation.

The [Questionary menu](docs/MENU.md) opens as **SMASH-HCM DATABANK EXPORTER**, with a boxed status panel and six sections: **Setup, Download, Local OMOP, Validate, Data Access Request, Exit**. Startup checks configured access and offers a data-update check; Yes automatically refreshes the manifest when needed. Download the database, published CSVs or cohort/modality ZIPs, or browse manifest files/folders. Review size/location and confirm before transferring. Local OMOP offers offline reports and configured exports once a readable database exists. Unavailable actions show their prerequisites. Run `omop-exporter` with no arguments, or `menu --plain`. Native vault storage is recommended; existing `.env` credentials remain compatible. The administrator must publish the actual databank manifest; `manifest.example.json` describes only the tested README.

## Use a database

```powershell
$env:OMOP_EXPORTER_DB = 'K:\SMASH_DATA\smash-etl\releases\v1.4_rc3\SMASH_OMOP_v1.4_rc3.db'
.\.venv\Scripts\omop-exporter.exe validate
.\.venv\Scripts\omop-exporter.exe report inventory --out .local-reports\inventory
.\.venv\Scripts\omop-exporter.exe report overlap --out .local-reports\overlap
.\.venv\Scripts\omop-exporter.exe cohorts list
```

Alternatively pass `--db <path>` or `--config config.json` to each command. `config.example.json` is dependency-free; optional YAML uses the `config` extra. Every output directory must be new. Databases are opened read-only.

Implemented commands:

| Command | Output |
| --- | --- |
| `validate` | SQLite integrity, schema/capabilities, person links, source SHA-256, optional trusted-hash comparison, optional embedded-catalog asset byte validation |
| `report inventory` | JSON/CSV table/column inventory, site/cohort population counts, observed variables and fact/patient coverage |
| `report overlap` | JSON and separate `core.csv` / `two_site.csv`, with exclusive site-pair counts and coverage |
| `cohorts list` | Canonical database cohort IDs/names; no silent PILOT-to-TEST aliases |
| `export --format events` | Deterministic full-history event CSV, optional cohort/variable filter and reproducibility manifest |
| `export --format tabular` | Feature-only baseline table from embedded cohorts/anchors, with variable dictionary, provenance and reproducibility manifest |
| `setup` / `menu` | Interactive SMASH login, manifest/cache downloads, integrity checks and local exports |
| `nextcloud check/list/download` | Read-only HTTPS WebDAV using the saved setup profile or an explicit `.env`, with a checksum receipt |

Example patient-level export to a protected location outside Git:

```text
omop-exporter export --db /protected/omop.db --format events --cohort <canonical-name-or-id> --out /protected/exports/events
```

The event stream includes post-baseline history; consumers must enforce prediction availability boundaries. Reports describe observed full-history overlap, not proven clinical equivalence. Unsupported study components are explicit. For strict checks, add `validate --require-capability cohorts --require-capability baseline_anchors`; trusted checksum comparison uses `--sha256`.

The available RC3 file is a partial clinical candidate: it can be inspected/reported but contains no cohort or endpoint/censor ledgers. This does not describe the scope of the forthcoming full v1.4 database. The current package calculates 31 exact three-site and 36 exclusive two-site candidates from this RC3, and does not hardcode those counts for other releases.

## Tests and implementation scope

```powershell
.\.venv\Scripts\python.exe -m pytest tests -m "not integration"
.\.venv\Scripts\python.exe -m pytest tests --omop-db 'K:\SMASH_DATA\smash-etl\releases\v1.4_rc1\SMASH_OMOP_v1.4_rc1.db'
.\.venv\Scripts\python.exe -m build
```

See [test fixtures and verification](docs/TESTING.md) and [database contracts](docs/DATABASE_CONTRACT.md). CI covers Windows/Linux/macOS and Python 3.9/3.12, including installed-wheel checks outside the checkout. Main candidates add native Windows, Linux, Apple Silicon and Intel Mac package builds. [Source checkout](https://github.com/SMASH-HCM/smash-hcm-databank-client).

Baseline tabular exports and manifest-driven batch downloads are implemented and tested with synthetic complete releases. The RC snapshots are tested read-only. Distribution plots, annual/endpoint exports, multimodal copying/format validation, and retry/resume remain forthcoming. The three original baseline contract tests now pass as ordinary tests. See [Nextcloud setup and the live README test](docs/NEXTCLOUD.md), [baseline rules and menu limits](docs/MENU.md), and the [status review and implementation plan](docs/STATUS_AND_IMPLEMENTATION_PLAN.md).

## Optional legacy PostgreSQL adapter

Only install `.[postgres]` in a local environment when working with historical PostgreSQL dumps. It supplies PyYAML and psycopg for `omop-exporter-legacy`. The core SQLite command never imports them. The top-level scripts remain installable for compatibility, including sparse tabular and landmark preparation; the known mixed/unknown-unit mean defect in the sparse exporter is fixed.

Use an explicitly supplied `config.postgres.example.yaml` copy with the legacy command. The [previous workflow](docs/LEGACY_POSTGRES_WORKFLOW.md) and [export methodology](docs/EXPORT_METHODOLOGY.md) are retained as historical contracts. Their source-sidecar fallback and PostgreSQL restore requirements do not apply to the new SQLite client.

This repository contains no training code or real patient-level outputs. Keep databases, credentials, raw images/signals and generated datasets in protected storage outside Git. Dated audits and the implementation history below describe earlier snapshots; current release and usage policy is in the linked guides. In particular, the [19 October RC4 format notice](docs/RC4_FORMAT_CHANGE_2026-10-19.md) describes a PostgreSQL dump now at the former SQLite path.

## Local database tools and portable application (0.7)

Portable builds now use a ZIP containing the executable and its `_internal` runtime folder; extract both together. Python and the required libraries are included. One-file packaging has been removed following Defender detections of the historical 0.5.0 build; see [the detection and review guidance](docs/BINARY_RELEASES.md#defender-detection-of-the-historical-050-one-file-build).

The menu header has green/red availability indicators and a three-second startup HTTPS reachability check. Server reachability and authenticated databank access are labelled separately. See [menu status meanings](docs/MENU.md).


**Local OMOP** now offers cohort/endpoint/inventory/overlap/distribution reports, cohort-based tabular/event exports, predefined feature sets and saved custom concept lists. It is enabled only with a readable local OMOP database. Confirmed download directories persist and are created when needed. Manifest, database and asset downloads have byte/percentage/speed/ETA progress; the manifest path is predefined. See [the local OMOP guide](docs/LOCAL_OMOP.md).

## RC4 validation and baseline policy (0.8)

The full ETL SQLite schema is supported, including results/CDM collision names and embedded export metadata. Vocabulary names are resolved sparsely. The tabular default now implements eligible baseline-day measurements with an explicit conservative post-assessment/pre-intervention mask; same-day treatment/unknown-role records and administrative/outcome-derived observations are held out and audited. Strict-before controls remain available. See [the baseline availability policy](docs/BASELINE_AVAILABILITY.md). Missing baselines still block a selected cohort rather than silently dropping people.

## Exact-day tabular default (0.9)

The default is now a standard patient/day table: `person_id, site, cohort, snapshot_date` plus one column per selected feature, with no averaging, sliding-window features or implicit carry-forward. RC4 CORE currently has 37 features and therefore 41 total CSV columns. FLORENCE is used for exported site/cohort labels; original SHaRe names remain in provenance. Historical/as-of selection requires explicit `--tabular-mode latest-history --lookback-days <N>`. See [the baseline/snapshot contract](docs/BASELINE_AVAILABILITY.md).

## Dataset configuration and standard output layout (0.10)

Version 0.10 adds menu configuration for cohort/feature selection, exact-day versus explicit history, optional history columns and event-stream filters. Use `--data-dir` for `DATA_DIR/<group>/train.csv,test.csv`, `DATA_DIR/event_stream/<cohort>/`, and `DATA_DIR/reports/`. Existing explicit `--out` bundles remain supported. [Dataset export guide](docs/DATASET_EXPORTS.md) describes every option, feature set, category-family mapping, patient summary and baseline caveat.
