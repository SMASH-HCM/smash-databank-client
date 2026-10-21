# SMASH-HCM Databank Client installation

Source: [SMASH-HCM/smash-hcm-databank-client](https://github.com/SMASH-HCM/smash-hcm-databank-client). Clone it with `git clone https://github.com/SMASH-HCM/smash-hcm-databank-client.git`, then `cd smash-hcm-databank-client`. Release ZIPs/wheels are on the repository's [Releases page](https://github.com/SMASH-HCM/smash-hcm-databank-client/releases). The installed command/module is `smash-hcm-databank-client` / `smash_hcm_databank_client`.

The core exporter uses Python's built-in SQLite driver and has **no third-party runtime dependencies**. It does not import or install psycopg, PostgreSQL, Docker, pandas or WP2. Python 3.9+ is supported; a current maintained Python version is preferable for a new installation.

All commands below run from the exporter checkout. Dependencies are installed in its `.venv`, not global Python.

## Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev,secure,ui]"
.\.venv\Scripts\smash-hcm-databank-client.exe setup
```

For a collaborator installation without test/build dependencies, replace the editable development install with:

```powershell
.\.venv\Scripts\python.exe -m pip install .
```

Alternatively, `pip install -r requirements.txt` installs the same core package; `requirements-dev.txt`, `requirements-secure.txt` and `requirements-postgres.txt` select the documented extras. `secure` installs native credential-vault support and is recommended for persistent Nextcloud login storage. It is optional for local database commands. Dependency metadata has one source of truth in `pyproject.toml`; `setup.py` is a compatibility shim, not a second dependency list. Running the script `setup.py install` is unnecessary.

## Linux/macOS

For users installing a released wheel without cloning the repository, follow [GITHUB_RELEASE.md](GITHUB_RELEASE.md#installing-the-python-release). `python -m smash_hcm_databank_client` runs the same client/menu as the executable. New installations store nonsecret state in `~/.smash/omop-exporter`; existing checkout profiles remain compatible. Mac vault storage uses the native Keychain when available. Native Mac ZIPs require successful Apple Silicon/Intel builds and are not produced by running the Windows builder.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[dev,secure,ui]'
.venv/bin/smash-hcm-databank-client setup
```

## Choose a database

Pass `--db` to each command, set `OMOP_EXPORTER_DB`, or copy `config.example.json` to `config.json` and use `--config config.json`. Precedence is CLI, environment, config. Relative config database paths resolve relative to the config file, not the current working directory. The client never chooses a release by guessing which file is newest.

```powershell
$env:OMOP_EXPORTER_DB = './private/OMOP.db'
.\.venv\Scripts\smash-hcm-databank-client.exe validate
.\.venv\Scripts\smash-hcm-databank-client.exe report inventory --out .local-reports\rc3-inventory
.\.venv\Scripts\smash-hcm-databank-client.exe report overlap --out .local-reports\rc3-overlap
.\.venv\Scripts\smash-hcm-databank-client.exe cohorts list
```

The reports contain JSON and CSV. Each output directory must be new: completed outputs are never implicitly overwritten. Clinical reports read the database alone; no WP2 reports, source CSVs or mapping directories are needed. Use protected directories outside the checkout for patient-level event exports.

To compare a trusted expected hash, add `validate --sha256 <64-character-hash>`. For required dataset capabilities, add `--require-capability cohorts`, `baseline_anchors`, `endpoint_labels` or `asset_catalog`; the flag can be repeated. Missing optional components are `UNSUPPORTED`, while missing explicitly required components fail validation. No expected hash means checksum comparison is `NOT_REQUESTED`, even though the calculated hash is reported.

`validate --asset-root <directory>` checks every file in a populated embedded `smash_asset` catalog for containment, readability, size and expected SHA-256. A missing catalog or expected checksum fails the requested asset check. This is byte integrity only; NPZ/NIfTI/DICOM format checks and clinical QC are future work.

Optional YAML configuration uses `pip install '.[config]'`; `config.example.yaml` is the SQLite example. JSON and direct CLI options need no configuration dependency.

## Nextcloud

For users who prefer no Python installation, see [portable application releases](BINARY_RELEASES.md). Developers can add `.[ui]` for arrow-key menus and `.[binary]` for the portable build dependencies. These extras do not add PostgreSQL to the core application.

Use `smash-hcm-databank-client setup` for hidden password entry and a choice of native OS vault, session-only or explicit plaintext `.env` storage. Run `smash-hcm-databank-client` or `smash-hcm-databank-client menu` afterwards. The [menu guide](MENU.md) covers database selection, version display, manifest-driven downloads and variable exports. Login setup does not alter an existing `.env` unless that storage choice is explicitly selected. [NEXTCLOUD.md](NEXTCLOUD.md) documents scripted access and the tested `databank/README.md` download. Network access does not need a local OMOP database. The core HTTP client uses the standard library; only native vault support needs the optional `secure` extra.

New profiles suggest the OS Downloads folder, respecting a relocated Windows Downloads location. Previously saved download locations remain selected. Each download batch has one **Yes / No / Change location** confirmation, with Yes selected by default. The location is saved in nonsecret profile settings only after confirmation; it does not belong in the password vault.

## Optional historical PostgreSQL workflow

This is a separate adapter for older dumps. Install it only in a local environment when needed:

```powershell
.\.venv\Scripts\python.exe -m pip install ".[postgres]"
.\.venv\Scripts\python.exe -m smash_hcm_databank_client.legacy.main --help
.\.venv\Scripts\python.exe -m smash_hcm_databank_client.legacy.main export --config config.postgres.example.yaml
```

Set an appropriate password environment variable and configure the database yourself. The example must be copied/edited for your installation. The optional legacy `restore` still needs Docker/PostgreSQL and an existing empty target database. The SQLite client does not require these services. The historical sidecar label fallback applies only to its legacy release contract; it is not a fallback used by the SQLite client.

Historical tools now live in `src/smash_hcm_databank_client/legacy/` and are included in wheels. Invoke them with `python -m smash_hcm_databank_client.legacy.<module>`. Old top-level module/command names are retired. See [legacy export methodology](EXPORT_METHODOLOGY.md). PostgreSQL behavior is retained for compatibility; no live PostgreSQL restore or export was performed during the SQLite package tests.

## Build distributable packages

```powershell
.\.venv\Scripts\python.exe -m build
```

This produces a wheel and source archive under ignored `dist/`. The wheel includes the legacy SQL/config resources and the script modules. Install the wheel with `python -m pip install <wheel-path>` in a separate environment to verify behavior outside the checkout. Keep databases, credentials and generated datasets out of package archives.

## Source layout and upgrade

Application code and resources live in `src/smash_hcm_databank_client/`. Install the package before running it from a checkout; the src layout prevents accidentally testing an uninstalled root package. Release tools are in `tools/`, documentation in `docs/`, and reusable synthetic examples in `examples/`.

If the old `omop-exporter` distribution is installed, uninstall it from that environment before installing the new distribution: `python -m pip uninstall omop-exporter`. The new package exposes only `smash-hcm-databank-client`. Replace `python -m omop_exporter` with `python -m smash_hcm_databank_client`. Existing saved profile/vault identifiers are deliberately retained so the rename does not lose login or local-directory settings. `SMASH_DATABANK_DB` is the new database environment variable; `OMOP_EXPORTER_DB` remains a fallback.
