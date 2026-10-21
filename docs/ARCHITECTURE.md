# Download client and dataset publisher

The user-directed split starts with client **0.13.0**:

```text
Versioned PostgreSQL OMOP dump -> restored PostgreSQL
  -> digitaltwin_moe / smash_omop: reports, feature sets, tabular/events, ZIPs + manifest
  -> reviewed Nextcloud publication alongside curated MRI/ECG/Echo archives
  -> smash-hcm-databank-client: login, browse/download, update, verify bytes
  -> collaborator's train/test files, event streams and curated assets
```

The client never restores or queries the dump, computes summaries, selects patient rows, fits transforms, creates labels, or trains models. Dataset/feature choices are catalogue tags, not requests to run SQL. It can optionally download and validate a PostgreSQL dump. The temporary SQLite analysis path has been removed from its source, dependencies, menu, CLI, tests and packaged runtime.

The PostgreSQL exporter is in [digitaltwin_moe](https://github.com/SMASH-HCM/digitaltwin_moe/blob/codex/databank-publisher/docs/methods/databank_publishing.md), package `smash_omop/`, tests `tests/data_export/`, configs `configs/data_export/`. It is independent of the downloader package and model-training imports. Its local virtual-environment dependencies are in `requirements-export.txt`. It reads native schemas in a read-only, repeatable-read snapshot, writes versioned local bundles and a transport-compatible manifest, and performs no automatic upload.

The move carries the existing cohort/feature/baseline/event policies and pre-existing research scripts/examples. A migration source/hash manifest is supplied in that repository. Existing historical training inputs and results are not regenerated or overwritten. Legacy projection scripts are retained there as inert historical text, not as a supported SQLite backend.

The catalogue declares schema version, release, safe relative file path, stored-file byte size/SHA-256, and optional stable artifact ID, version, cohort, modality, variable group, representation and kind. Published ZIP kinds are `tabular-export`, `event-stream` and `report`. `dataset-file` marks browsable individual companions so they are not duplicated in default bundle choices. Existing curated/database manifest entries remain compatible.

Publishers must upload generated artifacts and a reviewed combined `manifest.json`; new menu choices stay grey until the live manifest advertises them. Credentials, clinical bytes and server/database runtimes are never bundled in application releases.
