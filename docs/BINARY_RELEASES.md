# Portable application releases

Releases include Python, HTTPS support, the Questionary menu and native credential-vault support. Collaborators extract the complete ZIP and run the client without installing Python. PostgreSQL, SQLite and model-training libraries are not required or bundled. Datasets are separate authenticated downloads.

## Run a release

1. Extract the whole ZIP. Keep the executable beside its `_internal` folder.
2. Run `smash-hcm-databank-client.exe` on Windows, or `./smash-hcm-databank-client` from a Mac/Linux terminal.
3. Choose **Setup → Setup / Change User Login**. Prefer an app password stored in the OS credential vault.
4. Accept **Check for data updates now?** to retrieve the catalogue. Startup checks server reachability and configured login before showing the status table.
5. Choose **Download**, then published CSVs, event streams, reports, cohort modality ZIPs, individual files/folders or an optional PostgreSQL dump. Confirm **Download these files to: …** with Yes, No or Change location. The initial suggestion is the OS Downloads folder; confirmed choices are remembered.
6. Use **Validate** to check tracked files' presence, size and SHA-256. It does not restore or query a database.

The five main choices are Setup, Download, Validate, Data Access Request and Exit. Arrow keys move, Space ticks multiple selections and Enter confirms. Unavailable actions are grey. `menu --plain` provides numbered navigation. [Menu guide](MENU.md).

Existing profiles remain under `~/.smash/omop-exporter/` for compatibility. Source checkouts with `.smash/state.json` or a working-directory `.env` still work. `--state-dir` and `--env-file` can select another profile. Credentials and local state are never release inputs.

## Build locally

Build on the target operating system and CPU architecture, in a local environment:

```sh
python -m venv .venv-build
# Activate for your OS, then:
python -m pip install -e ".[binary,dev]"
python -m pytest tests -m "not integration"
python tools/build_binary.py --out dist/binary
```

The builder uses PyInstaller **folder mode (`--onedir`)** exclusively, with no UPX compression. It creates a version/platform ZIP, archive and file checksums, build information and dependency license notices. It refuses an existing release destination and packages an explicit public-file allowlist. Build from a clean source checkout; bounds on dependencies are not a lockfile or a promise of byte-identical builds.

The historical 0.5.0 one-file executable was quarantined by Defender. Folder packaging avoids unpacking a runtime at every launch and resolved the reported local trigger, but it does not establish that any build is independently audited. Keep protection enabled; signing and official stable-release review are separate release steps. See the historical [PyInstaller discussion](https://github.com/orgs/pyinstaller/discussions/5877).

## Automated artifacts and acceptance

Each push to `main` runs client tests and native Windows, Linux, Apple Silicon and Intel Mac builds before publishing an immutable prerelease candidate. Candidates do not replace latest stable. Manual portable builds and draft stable releases remain available. [Release policy](GITHUB_RELEASE.md).

Acceptance checks cover executable help/version, plain-menu navigation, native backend detection, authenticated manifest retrieval when authorized, archive checksums and exclusion of credentials, databases and analysis modules. PostgreSQL dataset/report tests belong to `digitaltwin_moe/tests/data_export/`. A local Windows build does not establish native Mac/Linux acceptance; only passing platform jobs do that. [Verification](TESTING.md).
