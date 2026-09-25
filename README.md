# smash-omop-export

Small, standalone tools for extracting SMASH OMOP history, landmark labels, sparse tabular views, and optional asset request lists. This repository contains no training code or patient-level results. Python dependencies are limited to PyYAML and psycopg. Outputs belong in a protected directory outside Git.

## Run

1. Create an empty PostgreSQL database and set `PGPASSWORD` in your shell. Docker Desktop is required only for the optional `restore` command; it runs the PostgreSQL 14 client against the host database. The database must already exist and be reachable through `host.docker.internal` from Docker.
2. Copy `config.example.yaml` to `config.yaml` and set the dump, connection, sidecar, output, and optional asset paths. Do not put a password in the YAML.
3. Install `pip install -r requirements.txt`.
4. Run `python main.py restore --config config.yaml` on an **empty** database if the dump has not yet been restored. This does not drop an existing database; a partially restored database requires operator review.
5. Run `python main.py all --config config.yaml`. Alternatively run `export`, `prepare`, `tabular`, or `assets` separately. Run `python main.py --help` for commands.

`export` reads OMOP `cdm` and `results` tables into five CSVs through PostgreSQL COPY. `prepare` creates a patient manifest, age-indexed stream, provisional source-derived labels, and rolling landmarks. `tabular` makes a sparse landmark-concept view; site, cohort, domain, source, concept, and lookback filters can be set in YAML. `assets` makes requests for separately stored files when an image occurrence CSV is supplied. The dump path identifies the release and is used by `restore`; set `hash_dump: true` to record its SHA-256 during export.

When exporting from `landmarks.csv`, each sparse row includes its `landmark_id` and endpoint. Use `tabular.endpoints` to select a study endpoint; use `tabular.landmarks: false` for one generic age-anchor view per patient. A patient may have different eligibility and follow-up for different endpoints, so endpoint-specific rows must not be silently collapsed.

The current provisional label builder needs curated Florence and raw Rennes clinical sidecars because endpoint cohort dates in the v1.2 database are import dates. It uses a unique clinical fingerprint to link the two Rennes source files. Replace that linkage with a governed crosswalk when the corrected ETL release supplies a dated endpoint ledger. Check output audits and the release manifest before model training. The current SQL and event age stream also lack source provenance and explicit availability times; source filtering requires an enriched future release. Do not treat a successful export as clinical endpoint validation.

The export SQL is versioned here. The model repository consumes only the exported CSV contract, so it can be installed and run independently.
