# 0.14.0 — cohort download categories and annotated browsing

- Remove the optional OMOP dump from the startup status table. Advanced download/byte validation remains available.
- Organize Download into cohort clinical data, curated bundles, event streams, cohort summaries, advanced PostgreSQL dump, advanced ETL output, and specific files/folders.
- Recognize explicit manifest kinds, existing cohort/ETL paths, and optional clinical/event preprocessing selections. Dataset-specific landmark files can share their clinical dataset tags.
- Add optional file/folder comments and aligned name/size/comment columns in browsing, checkboxes and batch review.
- Remove broad directory-download actions at the databank, zips and curated roots. Reject whole-container checkbox selections there; narrower folder recursion remains available.
- Preserve schema 1.0 and existing release manifests, settings, credentials, progress reporting and byte integrity checks.

See [manifest publishing](MANIFEST.md) for exact fields and examples. The client remains download-only; no ETL or dataset transformation runs locally.
