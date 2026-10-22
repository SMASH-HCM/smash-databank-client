# Download menu

Run the portable application or `python -m smash_hcm_databank_client`. The supplied logo and client version appear above a versioned status table. Connectivity and configured login are checked **before** that table. Their successful checks print SUCCESS. The table separately shows server reachability, login, download location and cached manifest release/schema. There is no local database row.

1. **Setup**: change login, check connection, retrieve manifest, select download location, check for updates.
2. **Download**: Cohort clinical data; Cohort data bundles (MRI / Echo / ECG); Cohort event stream datasets; Cohort summaries; Harmonized OMOP PostgreSQL dump (advanced); SMASH-HCM ETL output (advanced); Download specific file(s) / folder.
3. **Validate**: downloaded sizes/hashes, local dump bytes, existing folder versus manifest, local manifest loading and local dump selection.
4. **Data Access Request**: opens the approved Google form.
5. **Exit**.

Use Up/Down and Enter; Space ticks multiple cohort/data-type choices. Missing login, missing catalogue, or unpublished artifact categories disable the relevant action and state why. A database is not required for any ready-made dataset/report download. There is no Local OMOP/export menu.

Review cohort scope, filenames and sizes before one **Download these files to: <location> [Yes / No / Change location]** confirmation. Yes starts the batch and is selected by default. Change lets you edit and reconfirm; No transfers nothing and does not persist a new path. Initial suggestions use the OS Downloads location, including redirected Windows Downloads; confirmed custom paths take priority on later launches. Locations are nonsecret profile settings.

Clinical downloads include train/test CSVs and dataset-specific landmark/companion files with matching tags. Select a variable set, cohort(s) and any published preprocessing formats (for example baseline or history-730d). The client does not calculate history features or transform records. Cohort summaries contain the general cohort definitions, summary tables and landmark ledgers. ETL output is a separate advanced file selection. See [manifest categories and comments](MANIFEST.md) for publishing fields.

Specific files/folders supports multi-file checkboxes (Space, then Enter), immediate contents and recursion. The databank root, `zips/` and `curated/` do not offer whole-folder downloads, and an entire-container checkbox selection is rejected there. Open a narrower folder such as `curated/FLORENCE/Clinical/` for recursive downloading. File sizes and optional file/folder comments are shown in aligned columns. All paths are limited to the loaded manifest. ZIPs remain intact and are not extracted automatically.

Startup asks **Check for data updates now?** after successful login. An unchanged catalogue with no needed repairs prints only **Checking Databank manifest ... SUCCESS**. Changed tracked files or missing/size-changed downloads remain offered for explicit selection. New catalogue products stay in Download. Keep/archive/replace requires an explicit old-version policy and final location confirmation. Failed checks retain the existing cache/files.

Progress reports bytes, percent, speed and ETA. Success is dark green, failure red, user cancellation orange. Ctrl+C is CANCELLED, not FAILED. `NO_COLOR=1`, redirected output and custom writers remain plain.

Profiles retain the established `~/.smash/omop-exporter` location and OS-vault service for compatibility. Source checkouts with existing `.smash/state.json`/`.env` remain supported; `menu --state-dir ... --env-file ...` overrides them. Passwords are never saved in state JSON. Prefer the OS vault; plaintext `.env` is an explicit alternative, not encrypted storage.

The optional `.db` is a PostgreSQL dump, not a queryable SQLite file. The client checks its signature and byte integrity. Schema/clinical validation and dataset generation belong to [digitaltwin_moe](https://github.com/SMASH-HCM/digitaltwin_moe/blob/codex/databank-publisher/docs/methods/databank_publishing.md).
