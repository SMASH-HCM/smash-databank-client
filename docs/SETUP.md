# Install the download client

Use a native portable ZIP from [Releases](https://github.com/SMASH-HCM/smash-hcm-databank-client/releases), extract the entire folder, and run the executable beside `_internal`. No Python, PostgreSQL server, psycopg, SQLite or Docker installation is required on the collaborator's machine.

For Python users, create/activate a local virtual environment and install:

```sh
python -m venv .venv
python -m pip install ".[ui,secure]"
python -m smash_hcm_databank_client setup
```

The core has no third-party runtime dependencies; `ui` adds Questionary, `secure` adds the native credential vault, `dev` adds test/build tools, and `binary` adds portable-build dependencies. Use the wheel from Releases instead of `.` when installing without a checkout. Metadata is defined once in `pyproject.toml`; `setup.py` is a compatibility shim.

Setup asks for a username and hidden Nextcloud app password, then offers native OS vault, session-only or explicit plaintext `.env`. The fixed service is `https://smash-hcm.ucd.ie`, mounted folder `databank`. No credentials should be pasted into chat or committed. A homemade encrypted file is not used; the OS vault protects the secret separately from settings.

Startup checks reachability/login before displaying status and offering updates. Download location defaults to OS Downloads, including Windows relocation; a confirmed custom path is remembered in nonsecret state. No default directory is created/saved until confirmation. [MENU.md](MENU.md) explains the complete flow.

The optional OMOP `.db` download is a PostgreSQL dump for advanced use. Queries, reports and exports have moved to [digitaltwin_moe](https://github.com/SMASH-HCM/digitaltwin_moe/blob/codex/databank-publisher/docs/methods/databank_publishing.md), with separate local `requirements-export.txt`. The download client has no SQL engine or PostgreSQL dependency. Existing vault/profile IDs and legacy database environment-variable alias are retained only to preserve saved settings.
