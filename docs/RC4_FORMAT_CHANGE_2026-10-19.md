# RC4 file format change — 19 October 2026

Read-only inspection of `K:/SMASH_DATA/smash-data-bank/SMASH_v1.4_rc4.db` now identifies a **PostgreSQL custom-format dump**, with the `PGDMP` signature and a size of **573,896,232 bytes**. It is not a SQLite database.

The file previously validated at that path on 18 October was **3,632,111,616 bytes**, had a SQLite header, and SHA-256 `48bbb9835ed403c6a53b4e4bb9bdd20334a9b91bbf08376772895d1efbae3843`. The earlier reports and findings apply to that earlier SQLite snapshot. They are not validation of the current PostgreSQL dump's contents.

The client needs the ETL-generated **SQLite export**, including embedded cohort definitions/memberships, anchor/censor/endpoint ledgers, schema mapping and clinical tables. It does not require psycopg or a running PostgreSQL server. A `.db` filename alone does not establish the format.

Requested ETL/databank action: publish the SQLite release alongside any PostgreSQL dump, label their formats explicitly, and give them different names/manifest artifact identities. For example, use `.sqlite` or `.db` for the actual SQLite export and `.dump` for the PostgreSQL custom-format backup. A PostgreSQL backup should not be advertised as the client-installable OMOP database. Publish independent size/SHA-256 values for both.

No dump restore, conversion, source-file rewrite or deletion was performed. The 0.11 regression suite used RC3 SQLite and complete synthetic ledger fixtures while this release-format discrepancy remains unresolved.
