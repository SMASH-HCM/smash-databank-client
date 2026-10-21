# Published OMOP database: PostgreSQL dump

The published `SMASH_v1.4_rc5.db` is a PostgreSQL custom-format dump (`PGDMP` header). The `.db` extension is a release filename, not an indication of SQLite. The databank client downloads it without converting or restoring it, verifies the manifest's byte size and SHA-256, and remembers its local path and release version. No PostgreSQL driver or server is required for those operations.

The header shows a present, recognizable dump as **SMASH-HCM OMOP database: [OK] <version> (PostgreSQL dump)**. This means the artifact is available, not that its OMOP tables have been queried or clinically validated. Startup can recover a uniquely identifiable dump at the normal release/artifact depth, including a file left behind by older clients that completed transfer and then incorrectly attempted SQLite validation. Multiple candidates require explicit selection under Validate.

## Validate the downloaded bytes

Use **Validate → Validate downloaded files** for manifest/receipt size and hash checks, or **Validate → Validate local OMOP database** for dump signature and file integrity checks. The command line also supports:

```sh
smash-hcm-databank-client validate --db ./SMASH_v1.4_rc5.db --sha256 <trusted-64-character-sha256>
```

Without a trusted expected hash, comparison is `NOT_REQUESTED`. A recognized header alone does not prove the archive is complete or restorable. A PostgreSQL dump is not opened as SQLite. Internal OMOP table/capability checks and asset-catalogue interrogation require a restored database; explicitly requesting those capabilities against the dump fails rather than claiming they were checked.

## Restore and analyse

Custom-format dumps are restored with PostgreSQL's [`pg_restore`](https://www.postgresql.org/docs/current/app-pgrestore.html). A read-only catalogue check with installed PostgreSQL client tools is:

```sh
pg_restore --list ./SMASH_v1.4_rc5.db
```

This lists archive contents without restoring data. Restoring requires a separate, newly created PostgreSQL database and sufficient storage. The client does not silently install a server, invoke Docker or restore a dump. Keep database credentials outside Git and separate from the Nextcloud login.

For the existing optional PostgreSQL export adapter, install dependencies in a local virtual environment, configure `config.postgres.example.yaml`, and follow [the PostgreSQL workflow](LEGACY_POSTGRES_WORKFLOW.md). The adapter exports events/landmarks/tabular views after restoration; its options are different from the modern SQLite snapshot menu and do not yet implement every modern report or friendly feature preset.

The portable menu disables direct Local OMOP reports, feature selection and exports when the selected artifact is a PostgreSQL dump, with a restore/workflow explanation. Earlier SQLite snapshots retain their existing direct-file analysis adapter for compatibility; SQLite is not required or assumed for published databank downloads. Bringing the full modern analysis menu to restored PostgreSQL is separate implementation work.
