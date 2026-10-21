# Nextcloud: setup and README download test

The client reads local credentials and makes authenticated HTTPS WebDAV requests. It never uploads, creates shares or edits server files. A file manifest is not needed for this connection test. For the interactive setup wizard and manifest-driven downloads, start with [MENU.md](MENU.md).

## 1. Local credentials

The recommended persistent login is `smash-hcm-databank-client setup` with the optional `secure` extra and native OS credential vault. Session-only and explicit plaintext `.env` storage are also available. Existing `.env` settings remain compatible; setup never automatically migrates or deletes them. Scripted `nextcloud` commands prefer a saved setup profile when no `--env-file` is supplied, otherwise use `.env`. An explicit `--env-file` bypasses the menu profile. Session-only profiles must be set up again in a later process.

For dotenv-based access, put the following in `.env` using your editor:

```dotenv
NEXTCLOUD_URL=https://smash-hcm.ucd.ie
NEXTCLOUD_USERNAME=your-login
NEXTCLOUD_PASSWORD='your-app-password'
NEXTCLOUD_REMOTE_ROOT=databank
```

The first three settings are required. `NEXTCLOUD_REMOTE_ROOT` is optional if `--remote-root databank` is supplied on the command line. A non-secret template is provided in `.env.example`.

Use a dedicated app password from Nextcloud **Personal settings → Security** where possible. Do not put passwords in command arguments or chat. `.env` is plaintext local configuration, not an encrypted vault, and is excluded from Git along with `.env.*`; only `.env.example` is included. The parser does not execute shell expressions or expand variables. Single-quote a value containing `#` or spaces. Values in the selected file override process variables; `--remote-root` overrides either source's folder setting. No new Python dependencies are required.

The browser URL `https://smash-hcm.ucd.ie/apps/files/files/324?dir=/databank` identifies the mounted folder **databank**. The number `324` is not part of a WebDAV path. Group folders are accessed through the user's mounted Files hierarchy, normally:

```text
https://smash-hcm.ucd.ie/remote.php/dav/files/<account-id>/databank/README.md
```

The client initially uses `NEXTCLOUD_USERNAME` as the account ID. If the login name/email differs, copy the WebDAV URL from Nextcloud Files settings into an additional local setting:

```dotenv
NEXTCLOUD_WEBDAV_URL=https://smash-hcm.ucd.ie/remote.php/dav/files/your-account-id/
```

Use the WebDAV **user root**, with `databank` still supplied separately as the remote root. The override must have the same HTTPS origin as the server URL. TLS certificates are verified and redirects are refused, so credentials are not forwarded to a different endpoint or host.

## 2. Check access

The repository-local environment is already installed for this checkout. Otherwise follow [SETUP.md](SETUP.md).

```powershell
.\.venv\Scripts\smash-hcm-databank-client.exe nextcloud check --env-file .env --remote-root databank
```

This makes a `PROPFIND` request with `Depth: 0` to the configured folder. A successful result reports `PASS` and `HTTPS WebDAV`. No OMOP database is required. Credentials, authorization headers, account IDs and server error bodies are not printed.

If a path needs investigation, explicitly request a shallow listing:

```powershell
.\.venv\Scripts\smash-hcm-databank-client.exe nextcloud list --env-file .env --remote-root databank
```

That lists only immediate names/types/sizes; it does not walk the data bank recursively or download its files. Use `--path subfolder` for a folder under the configured root. Folder names and file names are case-sensitive.

## 3. Download README.md

```powershell
.\.venv\Scripts\smash-hcm-databank-client.exe nextcloud download README.md --env-file .env --remote-root databank --out downloads\readme-test
```

The output directory must be new. It contains the downloaded `README.md` and `download_receipt.json`. The `downloads/` directory is excluded from Git. The client checks remote metadata, uses the remote ETag with `If-Match` where available, stages the transfer, checks byte counts, calculates SHA-256 and publishes only a completed download. It refuses HTML login pages, unsafe relative paths, corrupt/incomplete transfers, unexpected redirects and existing output directories. `download_receipt.json` is reserved for the local receipt and cannot be selected as a remote filename.

The single-file command's default maximum is **16 MiB**, suitable for this small smoke test. `--max-bytes` can set an explicit larger bound for a selected file. Manifest-driven menu downloads instead use each entry's recorded size and hash, including large databases/archives. Cohort/modality batch selection and cache verification are implemented in the menu; retry/resume and ZIP extraction remain future work.

For a trusted expected checksum from your manifest:

```text
smash-hcm-databank-client nextcloud download README.md --env-file .env --remote-root databank --out downloads/readme-verified --sha256 <expected-sha256>
```

An ETag is a version marker, not an independent content hash. Without `--sha256`, the receipt records a local checksum and `expected_sha256_verified: false`. It does not claim that a trusted release manifest was checked.

## Live result — 15 October 2026

Authenticated folder access passed. The live test downloaded only `databank/README.md`:

| Result | Value |
| --- | --- |
| Local file | `downloads/readme-test-2026-10-15/README.md` |
| Size | 586 bytes |
| SHA-256 | `9cb38b348beb23f7094dd8956995d36257dcbe1d9325468a8114208f6776b468` |
| Protocol | HTTPS WebDAV, certificate verification enabled |
| Remote operations | Read-only `PROPFIND` and `GET` |
| Expected manifest checksum | Not supplied; local SHA-256 recorded |

The execution sandbox initially could not establish a network connection; the same authorized check/download succeeded with network access. No server configuration changes or credential changes were needed. Credentials were read from the local `.env`, and no credential values were written to the receipt or logs.

## 4. Manifest to prepare

Prefer a machine-readable JSON file in the shared folder, with paths relative to `/databank`, file sizes and **SHA-256 hashes of the actual stored files**. For example:

```json
{
  "schema_version": "1.0",
  "release": "v1.4",
  "files": [
    {
      "path": "README.md",
      "size_bytes": 586,
      "sha256": "9cb38b348beb23f7094dd8956995d36257dcbe1d9325468a8114208f6776b468",
      "kind": "documentation"
    }
  ]
}
```

The current schema version is **`"1.0"`**; the older numeric `1`, numeric `1.0` and string `"1"` remain accepted. A higher version number is accepted automatically when its required layout and integrity fields remain compatible. Unsupported layouts, unsafe paths, missing sizes/checksums and incompatible hash algorithms still fail validation. Schema version describes the JSON format, not the database release or data freshness.

The client supports both this `release` + `files` layout and the published databank inventory's `generated_utc` + `entries` layout. Inventory entries use `type: file` or `type: directory`; directory digests describe directory records and are never treated as downloadable-file SHA-256s. The top-level `database.path` identifies the OMOP download and must agree with its file entry. Without an explicit release label, the catalogue is labelled using the database filename, or generation date when no database is declared; this does not verify an embedded database version. Unknown additional metadata is retained. Cohort/modality selection still needs explicit published tags; the adapter does not infer clinical membership from filenames.

A real manifest is now published on Nextcloud. The 0.12.1 fix was tested against it on 21 October 2026: schema `1.0`, 472 downloadable file entries and 29 directory records. Only the manifest was downloaded during this check. A separate metadata request for its advertised `SMASH_v1.4_rc5.db` returned HTTP 404 with the configured account; the publisher must make that path available/share it or correct the catalogue before that database can be downloaded. Schema validation does not establish that every advertised asset is accessible. `manifest.example.json` remains a small illustrative README-only example. Add database files (`kind: database`), archives or individual assets as separate entries; don't store login URLs, passwords or app tokens in it. The selector accepts `cohorts`, `modalities` and `variable_groups` arrays. For imaging/ECG delivery also record representation, site scope, processing/QC version and archive membership/index location where applicable. Keep detailed patient/exam mappings in the controlled database/asset catalog; a directory listing alone cannot establish cohort membership.

After validation, the client keeps its authoritative copy under the local settings directory's `manifests/<ID>/` cache, and atomically saves a convenient **`manifest.json` in the confirmed download directory**. It prints that location. A failed validation cannot replace the previous valid cache or visible copy. If the download directory is unavailable/locked, a warning explains that the valid private cache remains usable. Selecting a new download directory copies the current valid catalogue there; an unchanged-ETag update check also repairs a missing visible copy without another transfer.

Use immutable versioned paths for release artifacts. Downloading a server-generated folder ZIP is less reproducible than downloading a finalized archive with a recorded hash. Menu option 3 retrieves `manifest.json` (or another entered relative path), and option 10 loads a local copy. Database and cohort/modality downloads verify size/hash automatically, then become available for local integrity checks and offline cache reuse. See [MENU.md](MENU.md) for the complete workflow and baseline export constraints.

## Troubleshooting

- **HTTP 401:** check the login and app password; an interactive browser session does not authenticate this client.
- **HTTP 403:** the account needs read/download access to the group folder and selected file.
- **HTTP 404 for manifest.json with Connection PASS:** the databank is accessible, but that manifest is missing or not visible to the account. Publish/share it at `databank/manifest.json`, or enter its actual relative path through Setup → Retrieve manifest. A cached valid manifest is retained. No file catalog is invented automatically.
- **HTTP 404 for the folder connection itself:** check the mounted folder and WebDAV account ID. Use the Files settings WebDAV URL override if needed. This is distinct from a missing manifest.
- **HTTPS connection failure:** check network/VPN and certificate trust. There is no certificate-verification bypass.
- **Redirect:** use the canonical server/WebDAV URL rather than a browser Files URL or login page.
- **Output already exists:** choose a new local test directory; no file is silently replaced.

Protocol references: [Nextcloud WebDAV API](https://docs.nextcloud.com/server/latest/developer_manual/client_apis/WebDAV/basic.html) and [device/app password settings](https://docs.nextcloud.com/server/latest/user_manual/en/session_management.html).
