# SMASH-HCM Databank Client menu

Repository: [SMASH-HCM/smash-hcm-databank-client](https://github.com/SMASH-HCM/smash-hcm-databank-client). The compatible executable/command remains `omop-exporter`.

For the portable Windows application, extract the ZIP and run `omop-exporter.exe`. Python is included. The title is **SMASH-HCM DATABANK EXPORTER**. The boxed header shows the databank URL, selected local directory, local OMOP version and manifest release; missing database/manifest values are `<unavailable>`. Long paths wrap inside the box. Use Up/Down and Enter to open a section, and Space to tick items in multi-select lists. You can cancel or go Back without downloading anything.

## Everyday workflow

From 0.11, startup automatically checks configured login/databank access, then asks **Check for data updates now? [Y/n]**. Yes refreshes the manifest automatically and offers tracked-file updates, with archive/keep/replace selection and final confirmation. This also runs after login setup; manually selecting connection then manifest is no longer necessary for ordinary use. Failures leave cached manifests and local tools available. See [UPDATES.md](UPDATES.md). Setup also contains **Check for data updates**.

1. **Setup → Setup / Change User Login.** Enter your Nextcloud username and hidden app password. Prefer the OS credential vault to remember the login.
2. **Startup → Check for data updates? → Yes.** Successful configured login/access is checked automatically. Yes refreshes `/databank/manifest.json` as needed and offers tracked-file updates. Manual connection/manifest actions remain in Setup for diagnosis. Downloads show byte/percentage/speed/ETA progress.
3. **Download.** Choose the OMOP database, ready-made train/test CSVs, cohort ZIPs or specific files/folders. CSV downloads do not require a local database. For ZIPs, tick the cohorts first, then one or more data types (MRI, Echo, ECG, etc.). For example, tick FLORENCE-TRAIN, FLORENCE-TEST and RENNES-TEST, then ECG. Types missing for any selected cohort are disabled with a reason. CSVs can also be filtered by a published variable set, such as CORE.
4. **Review and confirm.** Review every selected file, its cohort scope and the total size. The suggested destination is `SMASH-HCM` inside your home folder. Confirm that folder or choose another, then explicitly confirm the download. Declining either confirmation transfers no files. The confirmed folder is created and remembered in the local nonsecret profile, and is shown and confirmed for each batch.
5. **Validate → Validate downloaded files.** Recalculate sizes/hashes to identify deleted or modified files. This works offline from saved download records. The same section provides database/folder validation, local manifest loading and existing database selection.

Available actions are highlighted. Missing prerequisites disable an action and explain what is needed. A new user's download section stays grey until a login and valid manifest are available. Categories absent from a manifest stay grey too. A configured login means a connection can be attempted, not that access has already been granted. The Data Access Request link remains available from the main menu.

If the folder connection passes but the manifest returns HTTP 404, the menu reports **Connection: PASS** separately from **Manifest: NOT AVAILABLE**, keeps any previously loaded valid manifest and explains that the file needs to be published/shared at the fixed `/databank/manifest.json` path. The last check is tracked only for the current session. The boxed databank URL is the requested friendly label; authenticated requests continue to use the configured HTTPS WebDAV user root and mounted `databank` folder.

The application displays the logo once and updates release/location status after actions. The newly supplied block-character heart/SMASH/HCM logo is used, with a scaled version for ordinary terminals; the previous repeating-letter fill is no longer used.

The header shows green **[OK]** or red **[NO]**, also readable without colour. Startup first performs a credential-free server probe bounded to three seconds, then checks configured authenticated databank access. Server reachability alone is not account validation; the authentication result takes precedence. The update prompt controls manifest/data transfer. Offline/failed checks still open the local menu. Passwords are not displayed or rewritten by startup checks.

On first use the directory shows red `[NO] <unset>`. Confirming a location creates it and saves it across sessions. Startup also creates an already-confirmed location saved by older versions. Inaccessible directories remain red. The directory indicator requires a selected folder that currently exists. A database must be present and readable; the manifest must be locally available and pass its schema validation. Missing or invalid resources are red. Startup never creates an unconfirmed default download directory. These availability indicators do not replace **Validate**, which checks downloaded file sizes and hashes. Status checks are session-only and are refreshed after actions; the HTTPS probe runs once per launch.

## Source installation

From the exporter checkout in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[secure,ui]"
.\.venv\Scripts\omop-exporter.exe setup
```

`setup` asks for your username and a hidden app password, then opens the menu. On later visits run `omop-exporter` with no arguments, or `omop-exporter menu`. Use a Nextcloud app password from Personal settings → Security. The server `https://smash-hcm.ucd.ie` and mounted folder `databank` are fixed in the menu. The browser's folder ID `324` is not part of its WebDAV path.

With the optional `ui` extra (included in portable builds), Up/Down and Enter navigate grouped submenus. Available actions are colored; unavailable actions are grey, cannot be selected, and state the missing prerequisite. Availability is recalculated after actions using local state, with no background login/network request. A configured login means a connection can be attempted; it does not prove credentials are valid or access has been granted. Use the connection check for that. `menu --plain` forces numbered menus; piped input and installations without `ui` use numbered output automatically, with explicit availability labels.

Windows users can instead extract and run the [portable application](BINARY_RELEASES.md), with no Python install. `doctor` reports the bundled libraries and native-vault backend without reading saved passwords.

The SMASH logo appears above local status. Use **Validate → Select a local OMOP database**, or `omop-exporter menu --db <path>`. Version information comes from embedded metadata or the download manifest; otherwise it is labelled unknown. The saved download locations are checked for a unique usable SQLite database; unrelated drives are not scanned.

The full logo is 158 columns wide. Smaller terminals use quadrant block characters to scale the supplied image while preserving its layout; terminals without Unicode support use an ASCII rendering of the same silhouette.

## Login storage

The recommended option is the operating system credential vault through the optional `secure` extra: Windows Credential Locker, macOS Keychain, or an available supported Linux secret service. The application accepts only its supported native backends and does not silently choose a plaintext keyring. See [keyring's documentation](https://keyring.readthedocs.io/en/latest/) for platform requirements. A home-made encrypted file would also need a separately protected decryption key; the OS vault avoids keeping that key beside the password.

Other explicit choices are session-only storage and a plaintext `.env`. If no native vault is available, session-only is the default. The existing `.env` remains compatible and is never automatically migrated or deleted. After choosing the vault, remove an old `NEXTCLOUD_PASSWORD` entry yourself if you no longer need that plaintext copy. Windows file permissions follow the containing directory; `.env` is not described as encrypted or universally private.

Passwords are not written to state JSON, download receipts or exports. Portable builds keep nonsecret state and manifest references under `~/.smash/omop-exporter/`; if explicitly selected, plaintext storage uses `.env` there. This location is stable when the executable moves or launches from a different directory. Source installations retain the existing `.smash/` and `.env` defaults in the working directory. `menu --state-dir <directory> --env-file <file>` can select an older portable profile explicitly. A session-only password expires when the process closes.

Data files go into the confirmed download folder, organized by release and named artifact subfolders with a receipt. Existing files are not moved when the folder changes; an explicit download to a new folder creates a new copy. Tracked files in previous confirmed locations can still be checked. Keep credentials and clinical data in protected storage outside Git.

## Menu sections

| Section | Actions |
| --- | --- |
| 1. Setup | Setup / Change User Login; Check Databank Connection; Retrieve manifest; Select Download location; Check for data updates |
| 2. Download | OMOP db; published train/test CSVs; cohort/data-type ZIPs; specific files/folders; generate new local OMOP exports |
| 3. Local OMOP | Configured tabular/event exports; summary/patient/feature-set reports; saved custom variable sets |
| 4. Validate | Downloaded files; local database; an existing folder; local manifest; database selection |
| 5. Data Access Request | Open [the SMASH Google Form](https://forms.gle/nNDDBbX8ah15dNcs8); no form is submitted automatically |
| 6. Exit | Close the application |

The server manifest was not yet created when this workflow was implemented. The manifest step needs that file to be published. Validate can load the supplied `manifest.example.json`, which describes only the tested README; database/CSV/bundle categories correctly stay disabled for that example, while the file browser can select README. Database tools work offline. The scripted `nextcloud download` command remains available for explicit single-file downloads without a manifest.

## Browse specific files and folders

Choose **Download → Download specific file(s) / folder**. The virtual tree is built from file paths in the loaded manifest; it makes no remote directory crawl. Open a `[Folder]`, use `< Parent folder` to go up, or cancel to return to the main menu.

Each folder offers immediate files, all files recursively beneath that folder, a multi-file selector and individual file entries. The root offers the same choices for the whole catalog. Counts/sizes are shown for folders; selecting a folder then opens the normal file/size/location confirmation review. Only selected manifest entries are transferred, once each, with their expected sizes and hashes. Existing archives remain intact. Remote relative paths remain in receipts; local storage uses the existing release/artifact-folder layout.

Directory choices are derived from validated relative paths. Parent navigation is a menu operation within the catalog; absolute paths, `..` escapes and folders absent from the manifest are rejected. Sibling names such as `site` and `site2` remain separate. Empty remote folders cannot be represented by this file-only manifest.

## Preparing the manifest

Copy `manifest.example.json` and add actual published artifacts. Each entry requires a unique safe relative `path`, exact `size_bytes` and SHA-256 of the stored file. Schema version is `1`; `release` is required. For example, the following is a template: replace the path, size and checksum before use.

```json
{
  "schema_version": 1,
  "release": "v1.4",
  "files": [
    {
      "path": "releases/v1.4/csv/FLORENCE-TRAIN-core.csv",
      "kind": "tabular-export",
      "cohorts": ["FLORENCE-TRAIN"],
      "variable_groups": ["core"],
      "format": "csv",
      "size_bytes": 123,
      "sha256": "REPLACE_WITH_64_HEXADECIMAL_CHARACTERS"
    },
    {
      "path": "releases/v1.4/SMASH_OMOP_v1.4.db",
      "kind": "database",
      "size_bytes": 123,
      "sha256": "REPLACE_WITH_64_HEXADECIMAL_CHARACTERS"
    },
    {
      "path": "releases/v1.4/rennes_all_ECG.zip",
      "kind": "archive",
      "cohorts": ["rennes_all"],
      "modalities": ["ecg"],
      "representation": "npz",
      "size_bytes": 123,
      "sha256": "REPLACE_WITH_64_HEXADECIMAL_CHARACTERS"
    }
  ]
}
```

Upload the completed JSON as `databank/manifest.json`, or enter another relative path under Setup → Retrieve manifest. The exporter only reads the server. Keep release artifacts immutable. Tags match exactly after case/space normalization: `rennes_test` does not implicitly select a `rennes_all` archive. Add tags only when their published scope is understood. Archives are downloaded intact, with no automatic extraction or patient filtering. Detailed patient/exam linkage belongs in the controlled OMOP asset catalog.

Publish one record per actual file; add each available cohort's CSVs/archives separately. `kind: tabular-export` or a `.csv`/`.csv.gz` extension identifies a published table. Cohort bundles require `.zip`, `cohorts` and `modalities` tags. Use `representation: npz`, `nifti`, etc. Raw/DICOM representations are excluded from the main processed-bundle chooser and remain accessible as explicit files in Advanced tools. A multi-cohort selection matches any selected cohort, AND the chosen modality/variable set; a shared tagged archive is downloaded only once. A requested cohort with no matching published file is never silently substituted. Blank/unsupported cohort tags disable guided selection for that category.

Downloads are staged, checked for size and SHA-256, then published. Verified cached files in the chosen location are reused; an explicit repeat download repairs a corrupt cache entry into a fresh directory. Failed files are listed without discarding successful transfers. Verification distinguishes a manifest reference from a local receipt; saved expected hashes still work if the manifest copy is unavailable. An external database without an expected hash is reported as `NO EXPECTED CHECKSUM`. Checksums validate bytes, not clinical completeness or image/signal format. Technical database/schema checks remain available through `omop-exporter validate --db <path>`.

## Local variable exports

Version 0.10 menu configuration and output locations are documented in [DATASET_EXPORTS.md](DATASET_EXPORTS.md). The menu selects cohort(s), variables, format and exact-day/history or event-specific options, then confirms DATA_DIR and the destination paths. Tabular splits go to `<group>/train.csv,test.csv`; events to `event_stream/<cohort>/`; report text/tables to `reports/`. Patient-level reports are saved without printing patient rows. History columns are opt-in, and event metadata can include source-variable text. Older low-level CLI bundle examples below remain valid with `--out`.

The main CSV download retrieves existing published files. Separately, **Download → Generate new exports from local OMOP** calculates core and exclusive two-site variables from the supplied database alone and generates new local outputs. First select an existing database under Validate when needed. It offers baseline tabular output first, with full-history event output as an alternative.

```text
omop-exporter export --db /protected/omop.db --cohort florence_train --format tabular --vars core --out /protected/exports/florence-train
```

Baseline tabular output requires embedded cohorts and valid, unique clinical baseline dates/ages for every selected person. It produces `data.csv`, `samples.csv`, `variables.csv`, `feature_provenance.csv` and a reproducibility manifest. Every selected person remains present, including people with all features missing. Feature columns are stable table/concept keys. The 0.9 default selects only the exact baseline day under the post-assessment/pre-intervention mask, with no carry-forward. The main CSV has four metadata columns and one column per selected feature. Earlier-history lookup requires both explicit latest-history mode and a lookback. Baseline-day measurements and explicit clinical/diagnostic allowlists are eligible; unclassified same-day actions and administrative/outcome-derived observations are held out. Future evidence is excluded. Strict-before remains an explicit CLI control; see [BASELINE_AVAILABILITY.md](BASELINE_AVAILABILITY.md). Unknown/mixed units or conflicting latest values remain blank with QC reasons; no unit conversion or imputation is fitted. Presence-only facts mean documented positive evidence; absence remains unknown. Medication observation 3021806 is held blank pending class-context rules.

This is a feature-only baseline export. It does not attach outcome labels, create annual training landmarks or establish clinical equivalence from concept overlap. Provenance includes concept/unit/date/QC companions; optional event metadata includes source-variable text. The partial RC3 has no usable cohort/anchor ledger, so baseline export correctly stops there. Its inventory, overlap and optionally core-filtered full-history events remain available. Full-history event streams include post-baseline facts; explicit baseline scope applies the conservative prediction mask. Downstream risk-set/label handling remains separate.

Retry/resume, automatic archive extraction, imaging/ECG format validation, multimodal copy/reference exports, annual indexes and distribution plots remain planned work. No network request is made by a local-only export.

## Local database tools

The main menu is **1. Setup / 2. Download / 3. Local OMOP / 4. Validate / 5. Data Access Request / 6. Exit**. Local OMOP provides tabular/event exports, preconfigured reports and reusable variable selection. All three actions are disabled until a readable OMOP database is selected or discovered at startup. The Download section remains for remote files and published datasets. See [LOCAL_OMOP.md](LOCAL_OMOP.md) for discovery rules, report contents, custom feature lists and multi-cohort exports.
