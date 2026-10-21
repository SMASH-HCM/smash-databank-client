# 0.13.0 — download client only

- Move native PostgreSQL reports, features, cohort/tabular/event exports, publisher, examples and research helpers to digitaltwin_moe (`smash_omop/`).
- Remove the temporary SQLite adapter and local-analysis menu/commands from the client. No SQL driver or model stack is required or bundled.
- Add manifest-driven download choices for published event-stream and report bundles, alongside train/test CSV bundles and curated modality archives. Database dump download is advanced/optional.
- Preserve the versioned logo/table, checked login status, single Yes/No/Change location prompt, progress bars, colored outcomes, catalogue caching, integrity validation and explicit keep/archive/replace flow.
- Keep saved logins and download locations compatible. New artifact choices are available only after publication in the live manifest.

See [ARCHITECTURE.md](ARCHITECTURE.md) and the [PostgreSQL publisher guide](https://github.com/SMASH-HCM/digitaltwin_moe/blob/codex/databank-publisher/docs/methods/databank_publishing.md).
