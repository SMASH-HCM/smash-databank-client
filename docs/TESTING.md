# Tests and release acceptance

Install the development extra in the local environment as described in [SETUP.md](SETUP.md).

## Canonical repository and main release candidates — 19 October 2026

Repository: [SMASH-HCM/smash-hcm-databank-client](https://github.com/SMASH-HCM/smash-hcm-databank-client). The reviewed source base remains 0.11.0; CI derives immutable candidate versions/tags per main push. Package/command compatibility is retained. The final local run passed **281 tests in 21.54 seconds**, including RC3 read-only integration and seven release-helper cases for PEP 440 candidate identity, atomic matching-version patches, complete six-artifact checksums and rejection of missing/tampered/unexpected assets. Evidence: `.local-reports/main-release-final-tests.xml`.

The main candidate workflow gates publication on the reusable contracts/package matrix and four native platform builds. Windows/Linux test Python 3.9 and 3.12; both Mac architectures test 3.12. Python shell steps explicitly add the checkout to their import path before loading release helpers. Candidates publish as prereleases with `latest=false`; reruns preserve published candidates and can resume a same-commit draft. Stable tags retain an intentional draft workflow. YAML/inline-Python checks and public-file/secret exclusion checks are performed before the push; remote Actions outcomes are assessed separately from local verification.

## Startup/data updates and Python distribution — version 0.11.0

On 19 October 2026, **274 tests passed in 20.24 seconds**, including read-only RC3 SQLite integration and 28 new startup/update cases. Coverage includes first manifest retrieval after consent, unchanged ETags with cache verification, invalid manifests, changed checksums without a changed release label, stable-ID path changes, missing-file repairs, no guessed legacy matches, login failures/404, cancellation/final confirmation, keep/archive/replace, modified-file deletion refusal, containment checks, failed transfers, SQLite validation before database activation, durable old-receipt recovery after interruption, home/legacy Python profiles and setup-to-startup handoff. Evidence: `.local-reports/0110-complete-tests.xml`.

The requested RC4 integration initially failed because `K:/SMASH_DATA/smash-data-bank/SMASH_v1.4_rc4.db` now contains a 573,896,232-byte PostgreSQL custom-format dump (PGDMP), rather than the 3,632,111,616-byte SQLite snapshot validated on 18 October. No conversion or write was attempted. The complete passing run used the available RC3 SQLite file plus complete synthetic cohort/anchor/endpoint fixtures. The client correctly rejects a PostgreSQL dump regardless of its `.db` suffix. See [RC4_FORMAT_CHANGE_2026-10-19.md](RC4_FORMAT_CHANGE_2026-10-19.md).

The Python wheel and source archive built with the existing local build tools. The wheel was installed without dependencies into a separate environment and tested outside the checkout: CLI help/version, no PostgreSQL/YAML core import, automatic consented manifest retrieval and an entire stable-ID archive update using synthetic files/fake transport. The Windows folder executable passed version/doctor/offline startup, a synthetic standard-layout tabular export, per-file/archive checksum checks and private-file exclusion. Evidence: `.local-reports/acceptance-0110/acceptance.json`. Defender reported no matching detections with real-time protection enabled (`.local-reports/defender-0110-scan.json`).

A live configured-account check returned HTTP 500 from Nextcloud. The app continued into its local workflow and downloaded no clinical files. Live manifest/data updating could not be verified against that server state; synthetic transport checks passed. The original credentials/profile were unchanged. Native Mac Apple Silicon/Intel and Linux build/test workflows are prepared, with draft-release publication only, but were not dispatched from this task. Workflow YAML parsing/platform-matrix checks passed; local Windows tests do not establish native Mac acceptance.

## Configured datasets and patient inventory — version 0.10.0

On 18 October 2026, **246 tests passed in 54.25 seconds**, including read-only RC4 integration and actual Questionary key-binding checks. The normal Windows environment was required for asyncio's local socket pair; the network-restricted sandbox blocks that loopback operation. Nextcloud requests remain mocked. A pre-existing logo-test terminal stub was corrected to return the real tuple-shaped terminal-size contract, so pytest itself can safely read it while reporting results.

New cases exercise standard DATA_DIR paths and preserved split memberships; no-overwrite/collision and failed-batch behaviour; history opt-in, previous distinct dates, duplicate/conflicting days, numeric/category/unit guards and future exclusion; rare-grade family union, saved-family reuse and unchanged availability masks; event domains/calendar boundaries/baseline masks/source metadata; patient observation/visit/file/endpoint summaries and unknown training-index counts; the CLI and all three configured menu paths. Results: ignored `.local-reports/0100-complete-tests.xml`.

`tools/validate_configured_examples.py` generated 12 protected RC4 examples and seven reports under `K:/SMASH_DATA/omop-exporter/configured-exports-2026-10-18/`. Four default CORE snapshots contain 37 features plus four metadata columns. Other examples cover eight starter measurements, a candidate 36-feature consolidated CORE schema, explicit 365-day history columns and masked event streams with metadata. Acceptance reconciles population membership, baseline alignment, schema, temporal boundaries and checksums. The patient report has 2,984 rows, 180 unlinked file-catalogue records are separately reported, and training-index counts remain unknown without an explicit ledger. Two FLORENCE snapshot requests remain blocked by missing baselines. Source SHA-256 was unchanged.

The Windows AMD64 folder-mode 0.10.0 application passed archive/per-file checksum and private-file exclusion checks. Its snapshot, explicit history, consolidated family, masked events and per-patient CSVs matched audited Python outputs byte-for-byte. A complete plain-menu export selected the eight-measurement set and persisted DATA_DIR in an isolated profile. The user's actual credentials/profile were not changed. See `tools/check_configured_binary.py` and protected `binary-acceptance/acceptance.json`. A local Defender custom scan reported no matching detections with real-time protection enabled; this is a point-in-time observation, not a guarantee about future scans. Evidence: ignored `.local-reports/defender-0100-scan.json`.

## RC4 and exact-day default — version 0.9.0

On 18 October 2026, **226 tests passed** in 53.02 seconds, including read-only RC4 integration checks. New coverage verifies full-ETL results/CDM table mapping, sparse vocabulary lookup, incomplete anchors, post-assessment intervention/diagnostic masks, exact-day selection with no implicit carry-forward, one selected concept per column, no averaging of conflicting values, explicit history configuration and FLORENCE labels with original source names retained. The earlier history-specific schema regression was updated to opt in explicitly. Evidence: `.local-reports/rc4-snapshot-final-tests-20261018.xml`.

Actual RC4 reports and source-reconciled export examples were written to the saved protected download location, including eight current exact-day snapshots and an explicitly configured 365-day history example. Source SHA-256 remained unchanged. The detailed aggregate findings and limitations are in [RC4_VALIDATION_2026-10-18.md](RC4_VALIDATION_2026-10-18.md). No patient-level outputs are committed with these test records.

## Historical local database workflows — version 0.7.0

On 16 October 2026, the expanded suite passed **213 tests** in 16.77 seconds, including four read-only RC1/RC3 integration cases. The final discovery/progress refinements also passed 72 focused tests. Coverage includes persistent directory creation/migration, valid/invalid/multiple startup database candidates, gating all Local OMOP actions on a readable person schema, aggregate endpoint/cohort reports, unit-stratified distribution statistics, ECG measurement filtering, saved custom concept lists, shared columns across cohort exports, atomic batch failure, CLI feature-list reuse and progress completion only after successful publication. Results: ignored `.local-reports/local-workflows-tests-070.xml`.

The Windows folder executable passed startup discovery in a confirmed directory, report viewing without login/manifest, custom variable-list creation/reuse through the real menu, a two-cohort baseline tabular batch, a cohort-filtered event export and all five JSON/CSV report templates, using synthetic fixtures outside the checkout. Archive per-file hashes and exclusion of credentials/clinical files passed. The native console showed green directory/database indicators and the Local OMOP section available while remote downloads were disabled without a manifest.

Aggregate-only checks against both existing RC snapshots passed inventory, overlap and numeric distribution reports; cohort and endpoint templates explicitly returned UNAVAILABLE for their missing/unpopulated ledgers. RC3 produced 31 CORE variables and 105 site/unit distribution rows. No real patient-level exports were generated.

The packaged client downloaded only the authorized 586-byte Nextcloud README with its expected SHA-256, showing start/completion byte, percentage, speed and ETA progress. The generic `nextcloud` CLI test used `--remote-root databank`; the menu fixes that folder automatically. A prior CLI attempt without the folder returned 404 and published no file. New folder-build Defender scan and post-execution records showed zero matching detections with real-time protection enabled (signature 1.461.43.0). Local scan results are not a malware-free guarantee. Ignored evidence: `.local-reports/frozen-local-070/`, `.local-reports/real-070/`, `.local-reports/live-070-readme/`, `.local-reports/defender-070-*.json`.

## Historical status indicators and folder packaging — version 0.6.0

On 16 October 2026, **192 tests passed** in 16.49 seconds, including four read-only RC1/RC3 integration cases. New tests cover credential-free startup HEAD requests, HTTP/network failure sanitization, a bounded timeout even with slow DNS, late-result isolation, one startup check per menu launch, offline exit, folder/database availability, authenticated-result precedence, native green/red styles and monochrome output. Menu tests replace the startup probe with an offline fake; probe tests inject fake HTTPS transports, so ordinary tests never contact Nextcloud. Results: ignored `.local-reports/status-full-tests-20261016.xml`.

The real startup HTTPS probe also passed against the fixed SMASH endpoint, without reading credentials or downloading data. The builder now exclusively uses `--onedir`, with Python/libraries in `_internal` and checksums alongside the ZIP. The historical 0.5.0 one-file executable was subsequently quarantined by Defender; its previous functional smoke tests below are not a security clearance. See [the incident and review guidance](BINARY_RELEASES.md#defender-detection-of-the-historical-050-one-file-build).

The 0.6.0 Windows AMD64 folder build passed a targeted Defender custom scan (start/finish events confirmed; signature version 1.461.43.0, real-time protection enabled). No matching detections were recorded during subsequent executable checks. The executable passed version/help, bundled UI/YAML/native-vault detection, plain-menu exit/status rendering, credential-free live HTTPS reachability, and a two-person CORE tabular export from a synthetic database outside the checkout. Archive file checksums and exclusion of credentials/databases were verified. These are point-in-time local observations, not a malware-free guarantee or a clearance of the old one-file artifact. Ignored records: `.local-reports/defender-060-folder-scan.json`, `.local-reports/defender-060-post-execution.json`, `.local-reports/frozen-status-060/`.

## Historical menu and manifest browser — version 0.5.0

On 15 October 2026, the full suite passed **183 tests** in 15.75 seconds, including four read-only RC1/RC3 integration cases. Twenty new tests cover exact root/Setup labels, consistent plain-menu numbering, the boxed status panel with long paths, immediate versus recursive folder selection, individual and multiple files, parent navigation, cancellation, unlisted/unsafe paths, sibling-folder boundaries, file/folder conflicts, multiple cohort/data-type pairs and explicit rejection of missing pairings. Action-level menu tests inject navigation; separate public-menu tests exercise the actual five-item root/submenu flow. Results are in ignored `.local-reports/manifest-browser-tests-20261015.xml`.

The current root is Setup / Download / Validate / Data Access Request / Exit. The status title is SMASH-HCM DATABANK EXPORTER, with the four requested boxed fields. Cohorts are selected before data types. The virtual directory tree is built from validated manifest file paths and makes no remote listing requests. File/folder selections use the same reviewed, size/hash-checked downloader as cohort selections. Actual clinical folder contents remain dependent on the published manifest.

The Windows single-executable 0.5.0 build passed a frozen-app check of the new hierarchy, recursive selection of three synthetic files, destination confirmation, cached checksum verification and subsequent Validate navigation. Native console checks confirmed the title/box, five main choices, four Setup choices, colors/disabled states, Back and Exit. The executable also loaded the local README example manifest, selected its root contents through the browser, downloaded only the 586-byte README over verified HTTPS and validated its expected SHA-256. No clinical files, credentials or user download settings were changed. Ignored results are under `.local-reports/frozen-browser-050/` and `.local-reports/live-browser-050-*`; the ZIP/checksum are under `dist/binary/`.

## Synthetic tests

```powershell
.\.venv\Scripts\python.exe -m pytest tests -m "not integration"
```

Small temporary SQLite fixtures include all three sites, overlapping concept IDs in different tables, exact pairwise overlap, cohort names/memberships, clinical anchors, positive/negative/unascertained endpoint examples and an asset catalog. They contain no real participant data. Tests cover:

- Read-only connections, missing-file rejection, dump rejection, flattened table names, empty/partial database capabilities and orphan facts.
- Direct database inventory and exclusive overlap, concept 0/cohort-management exclusions, coverage denominators and canonical PILOT names.
- Installed CLI/config precedence, no core psycopg/YAML import, checksum exit status, staged publication and refusal to overwrite existing output.
- Deterministic cohort-filtered event output and packaged legacy SQL.
- Strict index boundaries, lookback windows, null dates, unknown/mixed units, valid zeros, nonfinite numbers, real quartiles/IQR, singleton SD and patient-level partition separation.
- Asset traversal/absolute/drive path rejection, missing files, sizes and hashes.
- The legacy sparse-export regression: known-unit and unknown-unit numbers must not be averaged together.

## Baseline, menu and manifest contracts

`test_future_contracts.py` retains three original executable requirements: preserve selected people with entirely missing features; preserve the requested schema when a variable is absent at a site; and reject annual training indexes for a PILOT holdout cohort. These now pass as ordinary tests of the baseline exporter; there are no remaining expected failures. Annual indexes are explicitly unsupported for every cohort until their endpoint/risk-set policy is implemented.

`test_tabular.py` checks strict date/lookback boundaries, latest-value conflicts, unknown/mixed units, release-wide unit consistency, missing anchors, documented-positive versus unknown status, feature provenance and event variable filtering. Synthetic complete fixtures exercise the full menu path from manifest/database download through core baseline export, without reading real credentials or exporting actual patients.

Manifest/workspace tests cover schema/types, traversal, exact cohort/modality tags, no inferred cohort subsets, expected-size/hash validation, corrupt-cache repair/reuse, folder verification and database version registration. Credential/menu tests cover hidden-input failure, session expiration, native-backend restrictions, sanitized vault errors, plaintext opt-in, template protection, profile precedence, partial database event exports and operation without a published manifest. Real vault writes are not performed by tests. Additional longitudinal, labeling, format-validation and resume tests should ship with those implementations.

## External OMOP database tests

Explicitly provide the protected `.db` to avoid committing it or hardcoding a developer's paths:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -m integration --omop-db 'K:\SMASH_DATA\smash-etl\releases\v1.4_rc1\SMASH_OMOP_v1.4_rc1.db'
```

Repeat `--omop-db` for multiple snapshots; `OMOP_EXPORTER_TEST_DB` supplies a single default. Include `tests` in the command so pytest discovers its custom path option reliably. A nonexistent explicitly supplied database fails rather than silently skipping. Without a path the two external-test templates are skipped.

External tests run full SQLite integrity, SHA-256 before/after, schema/person-link validation, table/site reconciliation and direct overlap. They never mutate the database, restore a dump, generate real patient CSVs, or access Nextcloud. Counts are calculated from the selected release; they do not hardcode candidate counts as expectations for the upcoming full v1.4 database.

Development fixtures used on 13 October 2026:

| Fixture | Use |
| --- | --- |
| v1.4 RC1, 285,003,776 bytes | Older available OMOP SQLite integration case |
| v1.4 RC3, 335,187,968 bytes | Current partial clinical snapshot, direct reporting and capability checks |
| Synthetic complete SQLite | Cohort/anchor/endpoint contracts before full v1.4 arrives |

The requested approximately 550 MB clinical `OMOP.db` was not located in the searched data-bank/ETL locations. Vocabulary indexes and ECG caches are not substituted for a clinical database. Use `--omop-db` to run these same tests against it when its path is available. No source database was copied into Git.

## Packaging and CI

The GitHub Actions workflow installs the development package, runs synthetic/contract tests, builds wheel and source archives, then installs the wheel into a clean temporary environment and checks CLI/legacy resources outside the checkout. Its matrix covers Windows/Linux and Python 3.9/3.12. Configuring CI does not mean those remote jobs have run; local verification results are recorded separately.

On full v1.4 arrival, run the external suite, inventory, overlap and required capability validation against that file. Reconcile cohort roles/anchors and asset indexes with its embedded data. Add full clinical-value, baseline/export/endpoint integration assertions when those features are delivered. Passing technical integrity does not establish clinical comparability, endpoint validity or asset acceptance.

## Local verification — 13 October 2026

The complete local run on Windows/Python 3.9.0 collected 53 cases: **50 passed and three strict expected failures** for the future wide/longitudinal exporter. Four passing cases exercised RC1 and RC3 read-only, including database hashes before/after. The current RC3 direct overlap command produced 31 core candidates and 36 exclusive two-site candidates.

Wheel and source builds passed. The wheel was installed without dependencies into a second local environment, then exercised outside the checkout: core/legacy help, packaged SQL, synthetic event export, real RC3 checksum validation and overlap. The clean core installation contained neither psycopg nor PyYAML. Dependency checks passed. Remote CI and live PostgreSQL/Nextcloud operations have not been run. Detailed machine-readable local results are in ignored `.local-reports/verification-summary.json` and `all-tests.xml`.

## Nextcloud verification — 15 October 2026

The updated complete run collected 80 cases: **77 passed and three existing expected failures**. The 27 new Nextcloud tests cover literal dotenv parsing and secret redaction, URL/origin/path validation, redirects, authenticated WebDAV metadata, nonrecursive listings, staged downloads, checksum/size/ETag mismatches, HTML login responses, transfer interruptions, reserved receipt paths and database-independent CLI use. These tests use synthetic credentials and fake responses; they never load the real `.env` or make network requests.

The sandbox's system temporary directory initially denied directory rename; the suite passed using a writable workspace temp directory. The local command used `--basetemp .local-reports/pytest-nextcloud-full-20261015`. Test results are in ignored `.local-reports/nextcloud-tests-20261015.xml`.

Separately, an explicitly authorized live test checked `databank` access and downloaded only `README.md` from the user's configured Nextcloud server over verified HTTPS WebDAV. The 586-byte file's local hash matches its receipt. No independent expected manifest hash was supplied. No server writes, broad crawl or clinical data download were performed. See [the repeatable Nextcloud guide](NEXTCLOUD.md).

## Menu verification — 15 October 2026

The menu implementation supersedes the historical counts above. Final verification passed **129 tests**, including four RC1/RC3 read-only integration cases, on Windows/Python 3.9.0 in 16.33 seconds. No cases are marked expected-failure. The Windows native credential-vault backend was detected in the local environment; actual credential storage is left to the user's interactive setup choice. A live authenticated menu connection check passed and its header displayed embedded `v1.4_rc3` metadata. A real manifest/database/archive download has not been tested because the server manifest is not yet published.

Wheel and source archive builds passed. Archive inspection confirmed the new modules, optional secure extra and source example/documentation, while excluding real credentials, `.smash`, downloads and clinical files. The updated wheel was reinstalled without dependencies in a second local environment: its no-argument menu opened and exited outside the checkout with neither keyring nor psycopg installed. Secure storage remains optional; the core menu and local exports work without it. Remote CI has not been run.

For restricted Windows environments where the system temp directory denies rename, use a new workspace temp path, for example `--basetemp .local-reports/pytest-menu-final`. Machine-readable menu test output is written to ignored `.local-reports/menu-tests-20261015.xml`. Do not rerun live network operations as part of the ordinary unit suite.

## Portable application and arrow menu — 15 October 2026

Version 0.3.0 passed **138 tests**, including RC1/RC3 read-only checks and actual Questionary key binding navigation that skips disabled choices. New cases cover local availability transitions without network/vault-secret access, missing/corrupt manifests, expired session credentials, disabled numbered actions, grouped navigation/back/cancel, Data Access Request browser dispatch only when selected, and local validation without login. The native Windows event loop needs a loopback socket pair; the restricted sandbox blocked it, so this run used the authorized normal local environment. It did not contact Nextcloud. The ordinary CI test matrix now installs the UI extra; the core package's dependency list remains empty.

Both Windows AMD64 PyInstaller folder and single-executable bundles passed help/version, no-argument plain menu, bundled-library/native-vault detection, synthetic SQLite validation and a two-person core baseline export outside the checkout. Both include Questionary, PyYAML and the native Windows vault backend. Archive hashes/exclusion checks passed. These local Windows builds are unsigned; Linux/macOS jobs and public publishing have not run. The separate portable workflow is manually dispatched. See [BINARY_RELEASES.md](BINARY_RELEASES.md).

The folder executable also completed an authorized live HTTPS WebDAV download of `databank/README.md`: 586 bytes, SHA-256 `9cb38b348beb23f7094dd8956995d36257dcbe1d9325468a8114208f6776b468`. No independent manifest checksum was supplied. The test used the existing local `.env`, did not change credentials, and wrote only an ignored local download/receipt. No clinical files were downloaded. Final ZIPs are under `dist/binary/`, with matching `.zip.sha256` files.

The user-supplied ASCII artwork was transformed by replacing only `A` characters with a continuous `SMASHHCM` pattern. Its original 4,134 bytes, whitespace and 158-by-26 character layout were preserved. The complete artwork is a packaged resource; compact terminals retain the smaller logo. Detailed local results are in ignored `.local-reports/binary-menu-tests-20261015.xml` and `.local-reports/frozen-acceptance-20261015-v2/results.json`.

## Guided downloads and replacement logo — 15 October 2026

Version 0.4 supersedes the 0.3 menu/logo described above. **158 tests passed** in 16.73 seconds, including four read-only RC integration cases. The 19 download-flow cases cover three selected cohorts downloading exactly their ECG ZIPs, shared-bundle deduplication, no ALL-to-TEST inference, published CORE CSVs without a local database, confirmation/cancellation of the home-directory suggestion, changing destinations without moving previous data, missing/modified files, verification with a missing manifest copy, partial transfer failures, combined connection/manifest steps, stable home-based frozen settings, logo fitting and actual Questionary checkbox key bindings. An additional Windows console regression verifies that an inherited `TERM=dumb` does not disable the native arrow UI, while explicit plain/color preferences are respected. Tests use synthetic files and fake credentials, with no clinical download or patient export. Results: ignored `.local-reports/userflow-tests-20261015.xml`.

The replacement logo resource is copied byte-for-byte from the supplied block-character artwork. Display scaling uses quadrant characters instead of substituting letters. The new basic menu is Set up and connect → Download data → Check downloaded files, with advanced tools separate. Portable settings default to `~/.smash/omop-exporter`; the download suggestion `~/SMASH-HCM` is never created or saved without an affirmative UI confirmation.

Final Windows 0.4.2 acceptance passed in both folder and single-executable modes: bundled libraries/native vault detection, cached three-cohort ECG selection plus CORE CSV selection, destination confirmation, five-file integrity checks, later missing-file detection, synthetic SQLite validation and a two-person baseline export. A native console smoke check exercised Questionary arrows, disabled-choice skipping, submenu Back and Exit. Color preferences remain respected (`NO_COLOR` and explicit prompt-toolkit depth); Windows console navigation does not depend on a Unix TERM hint. After the color refinement, all 29 focused UI/download-flow tests passed again. Local frozen results are in ignored `.local-reports/frozen-guided-042/results.json`.

The 0.4.2 folder executable also downloaded only the authorized Nextcloud README through the actual menu, loaded the local README example manifest, confirmed a workspace test destination and verified its expected 586-byte size/SHA-256 afterwards. No real login was changed, no home download folder was created, and no clinical files were transferred. Local test artifacts are under ignored `.local-reports/frozen-live-menu-042-*`. Actual multi-cohort clinical downloads still depend on publishing the corresponding manifest entries/artifacts.

## Missing manifest diagnosis — 15 October 2026

Version 0.4.3 passed **163 tests** in 15.80 seconds, including five new regressions for structured HTTP status, URL whitespace/display separation, manifest-only 404 with a successful connection, retained cached manifests, root-access failure and authentication failure. The complete run includes the RC1/RC3 read-only integrations; results are in ignored `.local-reports/manifest404-tests-20261015.xml`.

Separate live authenticated metadata checks returned PASS for the databank root and README, and HTTP 404 for `manifest.json`; none of the constructed request URLs contained whitespace. The rebuilt single-executable Windows app then reproduced that situation and correctly showed Connection PASS / Manifest NOT AVAILABLE, retained the successful connection result in the header and exited normally. No clinical file was downloaded and no server file, credential or user download-folder setting was changed. The release ZIP and checksum are under `dist/binary/` with version 0.4.3.
