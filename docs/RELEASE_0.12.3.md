# 0.12.3 — PostgreSQL dump downloads and checked startup status

- Display the client version beneath the logo and in the status-table border.
- Complete server reachability and configured login checks before the first status table; successful checks print `SUCCESS`. The login is not checked a second time before the startup update prompt.
- An unchanged catalogue with no tracked-file repairs prints only `Checking Databank manifest ... SUCCESS`. Changed/new catalogues identify their release; pending file repairs still appear even when the catalogue is unchanged. Data downloads retain full progress bars.
- Recognize PostgreSQL custom/SQL dumps regardless of their filename extension. Download, cache, select, discover and validate dump artifacts without treating them as SQLite or requiring psycopg.
- Recover recognizable dumps left by earlier successful transfers followed by incorrect SQLite checks. Preserve checksum validation, old-version retention and explicit confirmation.
- Report transfer completion only after artifact registration/validation. Invalid dump signatures cannot replace an active database or retire an older verified version.

The current published `.db` is a PostgreSQL dump. Its availability does not imply a queryable database. [POSTGRES_DUMPS.md](POSTGRES_DUMPS.md) describes byte validation and the separate restore/analysis workflow, including the current portable-menu limitation. Earlier SQLite snapshot analysis remains compatibility functionality.
