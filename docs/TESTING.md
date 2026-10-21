# Client verification

Run tests in a local environment:

```sh
python -m pip install ".[dev,ui,secure]"
python -m pytest tests
python -m build
```

Tests use temporary synthetic files and mock/loopback WebDAV responses. No developer-specific data-drive paths or real credentials are required. The synthetic PGDMP fixture tests recognition/transport only and is not claimed to be a restorable clinical dump.

Coverage includes credentials redaction/vault selection, fixed-origin HTTPS, path containment, catalogue validation and compatibility, cohort/modality/feature filtering, dataset/report bundles, checksums/cache reuse, missing/changed files, atomic updates and old-version retention, native/plain menu prompts, startup order and colors. Tests also verify that the client exposes no analysis/publishing commands and imports no SQLite/PostgreSQL driver.

PostgreSQL report/export tests moved to `digitaltwin_moe/tests/data_export/`. They use disposable schemas in an isolated PostgreSQL instance; no SQLite fixtures or training fits are involved. Frozen executable checks cover startup, native-vault detection, live authorised login/manifest checks and private-file exclusion. CI builds Windows, Linux and Intel/Apple Silicon Mac candidates after the client checks pass.

## Local 0.13.0 acceptance — 21 October 2026

The download client passes **239 tests**. The moved native PostgreSQL exporter passes **109 tests** in disposable schemas. An isolated restored RC5 smoke run produced seven reports, six tabular datasets and two event datasets; the client accepted the generated manifest and all 101 file sizes/SHA-256 hashes and ZIP CRCs verified.

RC5 itself still fails the required-baseline validation: 151 ledger rows lack baseline date/age, including 124 Florence Training and 21 Florence Pilot members. The complete Florence baseline export is deliberately blocked. No patient exclusion/anchor inference was introduced. The publisher's [RC5 validation report](https://github.com/SMASH-HCM/digitaltwin_moe/blob/codex/databank-publisher/docs/methods/omop_export/RC5_MIGRATION_VALIDATION.md) records the aggregate findings. Clinical outputs remain private and were not uploaded to Nextcloud.
