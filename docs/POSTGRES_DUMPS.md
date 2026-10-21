# PostgreSQL dump validation

Published SMASH `.db` files are PostgreSQL dumps. The client recognizes custom-format (`PGDMP`) and plain SQL dump signatures; SQLite is unsupported. Download completion requires the manifest size/hash checks and successful artifact registration. A previously completed transfer left by older incorrect SQLite checks can be discovered at the application's normal download depth and selected without re-downloading.

**Validate downloaded files** compares saved/manifest byte sizes and SHA-256s. **Validate local OMOP database** checks the dump signature, stable-file status and any available trusted hash/size. Scripted use:

```sh
smash-hcm-databank-client validate --db ./SMASH_v1.4_rc5.db --sha256 <trusted-64-character-sha256>
```

Without an independent expected hash, comparison is NOT_REQUESTED. A recognizable header does not establish restorability, OMOP schema validity, clinical completeness or imaging availability. No SQL commands are executed by this client. PostgreSQL restore, reports and cohort/feature exports live in [digitaltwin_moe](https://github.com/SMASH-HCM/digitaltwin_moe/blob/codex/databank-publisher/docs/methods/databank_publishing.md).
