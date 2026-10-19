# Startup checks and data updates — 0.11

The application and `python -m omop_exporter` share this flow:

1. Check fixed SMASH server reachability and discover/check the local database.
2. If credentials are configured for this session, check authenticated access to the databank. A reachable server is not proof that the account can access the folder. Authentication failures leave local exports/reports and cached files available.
3. On successful access, ask **Check for data updates now? [Y/n]**. Choosing No makes no manifest/data download. The account/root check has already run.
4. Choosing Yes automatically checks `/databank/manifest.json`. An intact cached copy with the same server ETag needs no new JSON transfer. Otherwise the client downloads and validates the manifest, then installs the new cache. Without ETag support, it fetches the small JSON and compares contents. A missing/invalid manifest or connection error preserves the previous valid cache.
5. Show updated tracked files and missing/size-changed downloads. Select the files to download, choose **Archive (recommended)**, **Keep**, or **Replace/delete**, then confirm the action. Untracked new catalogue files remain available in the normal Download menu; the app does not download the whole databank automatically.

This runs after startup and after login setup/change. **Setup → Check for data updates** reruns it. Manual connection/manifest options remain available for diagnosis. Configured authentication requests have an eight-second socket timeout per request; server reachability has the existing three-second bound. A vault may require an operating-system unlock. Offline/failing startup continues into the local menu.

These are **databank data updates**, not automatic executable replacement. Application releases are downloaded separately from GitHub.

## Version detection

Per-file SHA-256 and size are authoritative for detecting a changed tracked version; the manifest's display release name need not change. The quick check also tests file presence and size. It does not rehash multi-gigabyte local files on every startup; use Validate for complete local integrity checking.

An optional stable `artifact_id` lets a publisher move an artifact to a new versioned path. Use a separate ID for each database, cohort/modality/representation ZIP, or cohort/feature-set CSV. IDs must be unique within a manifest. Never reuse an ID for a different population or representation. `version` is an optional human-readable per-file label.

```json
{
  "schema_version": 1,
  "release": "v1.4",
  "files": [
    {
      "artifact_id": "omop-database",
      "version": "v1.4_rc4",
      "path": "releases/v1.4_rc4/SMASH_v1.4_rc4.db",
      "kind": "database",
      "size_bytes": 3632111616,
      "sha256": "REPLACE_WITH_THE_ACTUAL_64_CHARACTER_SHA256"
    }
  ]
}
```

The checksum placeholder deliberately requires replacement; this is a publisher template, not a valid live manifest. Suggested further IDs: `rennes-test-ecg-npz`, `florence-train-mri-nifti`, `tampere-test-echo-dicom`, `rennes-test-tabular-core-v1`. Change an ID when its clinical scope or feature definition changes materially.

Entries without IDs retain exact-path matching. An older receipt without an ID can be matched at the same path and acquire its ID on a subsequent download. If its path has already changed, explicitly download the new artifact; the client does not guess equivalence from similar filenames or cohort tags. Server-side removed paths do not cause automatic local deletion.

## Keep, archive, replace

All modes first create a new verified copy in the confirmed download root. Size/hash failure leaves the old file intact. A database must also open as an OMOP SQLite file before replacing the selected database. The app then selects the verified new database; it does not rewrite the old database.

- **Keep:** retain the previous file in place, with its receipt in local version history.
- **Archive:** copy the old file into `DATA_DIR/archive/<UTC timestamp>-<unique ID>/`, verify the copied bytes, persist an archive receipt/history entry, then unlink the exact original file. Locally modified bytes can be archived and are recorded with their actual hash.
- **Replace/delete:** delete only the exact tracked previous file, after the new copy has passed verification and old-version history is durable. A locally modified old file cannot be deleted by this action; choose Keep or Archive. A locked file remains in place with a cleanup notice.

No mode recursively removes a download folder, generated CSVs/reports or adjacent imaging. Old receipt files may remain beside retired files. Registered external databases without a download receipt are not automatically replaced. Symlink/containment checks constrain retirement to managed paths inside registered download roots. Archiving needs room for the old copy and the new download before the original is removed; it is not a filesystem-atomic multi-file transaction.

The old receipt is journalled before new receipt installation. If the process stops mid-update, old paths remain in `state.json` under `download_history` with a pending status. Startup reports this; it does not automatically resume deletion. Validate checks retained/archived/pending historical versions against their own hashes, rather than comparing them to the newest release. Keep state/receipts in protected local storage and review pending paths before manual cleanup.

## Settings and credentials

New Python and executable installations use `~/.smash/omop-exporter` for nonsecret settings and the optional profile `.env`. Existing Python checkouts with `.smash/state.json` keep that profile; an existing working-directory `.env` remains supported. Explicit `--state-dir` and `--env-file` take precedence. Neither changing the executable folder nor running Python from a new folder changes a new installation's default home profile.

The OS vault is still the preferred password store: Windows Credential Locker, macOS Keychain or a supported Linux secret service. Session-only and explicit plaintext `.env` remain available. Startup does not migrate, print or rewrite passwords.

## Application versus database releases

The application version, e.g. `0.11.0` or candidate `0.11.0rc42`, is independent of an OMOP release, e.g. `v1.4_rc4`. [SMASH-HCM Databank Client releases](https://github.com/SMASH-HCM/smash-hcm-databank-client/releases) contain application code/runtime only; clinical data stays in authenticated Nextcloud. Main pushes automatically publish tested candidates; stable tags use reviewed drafts. These GitHub application releases are not installed by the Nextcloud data-update flow. See [GITHUB_RELEASE.md](GITHUB_RELEASE.md) and [DATASET_EXPORTS.md](DATASET_EXPORTS.md).
