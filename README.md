# SMASH-HCM Databank Client

Download and verify approved SMASH-HCM research datasets from Nextcloud. The client is for collaborators who need ready-made **train/test CSVs, event streams, reports, and cohort ZIPs**. It does not query databases, prepare features, train models, or require PostgreSQL on the collaborator's computer.

**[Download the client](https://github.com/SMASH-HCM/smash-hcm-databank-client/releases)** Â· **[Request data access](https://forms.gle/nNDDBbX8ah15dNcs8)** Â· **[User guide](docs/MENU.md)**

## Get started

1. Download the ZIP for Windows, Apple Silicon/Intel Mac, or Linux from Releases. Candidates are prereleases; choose the required approved version.
2. Extract the **whole ZIP** and keep `_internal` beside the executable. Run `smash-hcm-databank-client.exe` on Windows or `./smash-hcm-databank-client` in a Mac/Linux terminal.
3. Open **Setup â†’ Setup / Change User Login** and enter your Nextcloud username and app password. Prefer the OS credential vault when available.
4. Startup checks connectivity and login, then asks **Check for data updates now?** Yes retrieves/refreshes the published manifest. An unchanged check prints one SUCCESS line.
5. Open **Download** and choose the published cohort(s), feature set, data type or report. Review the size and use **Yes / No / Change location**. Yes is the default. Your OS Downloads folder is suggested initially; a confirmed custom location is remembered.
6. Use **Validate** later to detect missing or modified files by size and SHA-256.

The five main choices are **Setup, Download, Validate, Data Access Request, Exit**. Arrow keys navigate; Space selects multiple cohorts/types; Enter confirms. Unavailable choices are grey with a reason. Use `--plain` for numbered menus.

## What can I download?

| Published artifact | Selection / use |
|---|---|
| Cohort clinical data | Select variables, cohorts and published preprocessing formats; includes matching train/test CSVs and landmark files. |
| Cohort event stream datasets | Select cohort(s) and published variables/representation; timing policy is supplied with the files. |
| Cohort summaries | Cohort definitions, summary tables and general landmark ledgers. |
| Cohort data bundles | Select cohorts, then ECG/MRI/Echo or another published type. Raw representations remain accessible through manifest browsing. |
| OMOP PostgreSQL dump | Optional advanced download for people who will restore/query PostgreSQL separately. `.db` means a PostgreSQL dump here. SQLite is unsupported. |
| SMASH-HCM ETL output | Advanced selection of ETL reports and outputs. |
| Individual files/folders | Browse files and comments; select individual/multiple files or a narrower folder recursively. Bulk downloading at the databank, zips and curated roots is disabled. |

[Manifest publishing fields and examples](docs/MANIFEST.md) describe category tags, preprocessing formats, landmark files and optional comments.

Available datasets come from `manifest.json`; the client cannot generate a combination that has not been published. Published names might include shared three-site clinical (CORE), shared measurements, a small starter set, ECG measurements, ESC clinical inputs, or explicitly named historical windows. The exact concept IDs, units, feature order and baseline policy belong to the downloaded definition files, not a local recalculation by the client. ESC inputs are not themselves a calculated risk score.

Archives are downloaded intact and are not automatically extracted. Example tabular bundles contain:

```text
FLORENCE/train.csv
FLORENCE/train/variable_set.json
FLORENCE/train/dataset_manifest.json
FLORENCE/test.csv
FLORENCE/test/variable_set.json
FLORENCE/test/dataset_manifest.json
```

Train/test follow published cohort membership; the client does not split patients. Use matching release/feature definitions across cohorts. Standard baseline tables contain the specified raw day/feature values; optional carry-forward/history summaries are separate published products. Full-history event streams may include post-baseline records: consumers must enforce their prediction landmark boundaries. Curated signals/images can be linked to tables by the published patient/cohort/asset identifiers; a ZIP filename alone does not establish patient identity or prediction-time availability.

## About the databank and the exporter

The [SMASH-HCM databank](https://smash-hcm.ucd.ie/databank) contains harmonized HCM data from FLORENCE, RENNES and TAMPERE, plus separately distributed raw/processed ECG, MRI and Echo files. Access requires an approved Nextcloud account. **TODO: URL for the SMASH-HCM Databank paper.** Cite the precise data release and export definition used in any study.

OMOP-to-tabular/event preparation, feature selection, PostgreSQL reports, indexing/landmark policies and publishing now live in **[digitaltwin_moe](https://github.com/SMASH-HCM/digitaltwin_moe/blob/codex/databank-publisher/docs/methods/databank_publishing.md)** under `smash_omop/`. They use a restored PostgreSQL database; no SQLite adapter or PostgreSQL driver is part of this client. Publishers generate approved bundles and merge their checksummed catalogue with curated files before uploading to Nextcloud.

## Python and scripted use

Python 3.9+ is supported in a local virtual environment. Install the release wheel with `ui,secure` extras, or from a checkout:

```sh
python -m venv .venv
# Activate .venv for your OS, then:
python -m pip install ".[ui,secure]"
python -m smash_hcm_databank_client setup
smash-hcm-databank-client menu
smash-hcm-databank-client nextcloud check
smash-hcm-databank-client validate --db ./SMASH_v1.4_rc5.db --sha256 <trusted-sha256>
```

There is one command: `smash-hcm-databank-client`. The old analysis commands `report`, `export`, `cohorts` and `publish` are absent; use `python -m smash_omop` in digitaltwin_moe. Existing profile/vault identifiers are retained so this simplification does not lose saved logins or download locations.

Passwords are hidden on entry. Native OS vault storage is preferred; session-only or explicitly chosen plaintext `.env` storage remains available. Logs/receipts/packages contain no credentials. Downloads show bytes, percentage, speed and ETA; successful outcomes are dark green, failures red and cancellations orange. Redirected output and `NO_COLOR=1` are plain text.

[Setup](docs/SETUP.md) Â· [Nextcloud/manifest](docs/NEXTCLOUD.md) Â· [Data updates](docs/UPDATES.md) Â· [Client/exporter split](docs/ARCHITECTURE.md) Â· [Release builds](docs/GITHUB_RELEASE.md)
