# Download categories, dataset formats and comments

The downloader reads `databank/manifest.json`. File paths are relative to `databank/`; each downloadable file requires its stored byte size and SHA-256. Keep schema version `"1.0"`: these are optional, compatible metadata additions. `release` identifies the data release, independently of the client version.

Use explicit `kind` values to choose the Download submenu:

| Download option | Recommended `kind` | Selection metadata |
|---|---|---|
| Cohort clinical data | `clinical-data` | `cohorts`, `variable_groups`, `preprocessing`, `split`; optional `role` |
| Cohort data bundles | `curated-bundle` | `cohorts`, `modalities`, `representation` |
| Cohort event stream datasets | `event-stream` | `cohorts`, `variable_groups`; optional `preprocessing` |
| Cohort summaries | `cohort-summary` | No cohort tags required; optional tags for documentation |
| Harmonized OMOP PostgreSQL dump (advanced) | `omop-database` | Optional stable `artifact_id` and data `version` |
| SMASH-HCM ETL output (advanced) | `etl-output` | No cohort tags required |
| Download specific file(s) / folder | Any kind | Always browsable when listed in the manifest |

Older `database`, `tabular-export`, `report`, `summary-report` and event kinds remain supported. For untagged older inventories, files beneath `cohorts/` are classified as cohort summaries and those beneath `smash-etl/` as ETL output, before the generic CSV fallback. Explicit file kinds take precedence. Path-based classification does not infer patient membership or cohort tags.

## Clinical CSVs and landmarks

For example, this file entry describes an already exported baseline table:

```json
{
  "path": "clinical/v1.4/FLORENCE/baseline/train.csv",
  "size_bytes": 123456,
  "sha256": "REPLACE_WITH_64_HEXADECIMAL_CHARACTERS",
  "kind": "clinical-data",
  "cohorts": ["FLORENCE-TRAIN"],
  "variable_groups": ["shared-clinical"],
  "preprocessing": "baseline",
  "split": "train",
  "role": "features",
  "representation": "csv",
  "comment": "Exact baseline-day measurements; no carry-forward"
}
```

Replace the illustrative size/hash with real values. Publish a two-year history table as a separate file with `preprocessing: "history-730d"`. The clinical/event flow lets users select variable set, cohort(s), and one or more published preprocessing formats. Missing preprocessing metadata is shown as `unspecified` when other tagged formats are available. The client downloads these products; it does not calculate windows or apply transformations.

Put dataset-specific landmark files here too: use `kind: "clinical-data"`, `role: "landmarks"`, and **the same cohort, variable-group and preprocessing tags as their associated feature CSV**. `clinical-landmarks` is also accepted as a clinical kind. Each file needs its own path/size/hash. Selecting the matching combination includes both files. JSON definitions, labels and other companions can use the same clinical kind and tags with a suitable `role`.

Whole-cohort definitions, endpoint summaries and general landmark ledgers under `cohorts/` instead use `cohort-summary`. This keeps study-ready dataset indices separate from the broader cohort catalogue. Preserve distinct TRAIN/TEST/PILOT names; the downloader never creates a split or changes cohort membership.

## File and folder comments

Add an optional **`comment` string** to any file or directory. Comments appear in the final aligned column of the browser, file checkbox lists and download review. An empty string leaves a blank comment column. Control characters are removed for terminal display.

In the `files` layout, directory annotations are a separate optional list:

```json
{
  "schema_version": "1.0",
  "release": "SMASH_v1.4_rc5",
  "directories": [
    {
      "path": "cohorts",
      "type": "directory",
      "kind": "cohort-summary",
      "comment": "Cohort definitions, summary tables and landmark ledgers"
    },
    {
      "path": "zips",
      "type": "directory",
      "comment": "Choose individual archives or open a narrower folder"
    }
  ],
  "files": []
}
```

With an existing `entries` inventory, add `comment` directly to its `type: "directory"` records; no separate `directories` list is needed. Directory metadata is optional and needs no checksum: an existing directory digest is preserved but is never used as a downloadable-file hash. Folders can also be inferred from file paths.

A directory `kind` applies to descendant files that do not have their own explicit kind. The closest annotated parent wins. Cohort, variable-group and preprocessing tags are **not inherited**; put these on every selectable dataset/companion file. Do not label the entire `curated/` tree as clinical if it also contains MRI/ECG assets.

Example aligned listing:

```text
[File] FLORENCE_PILOT_ECG_mat.zip | 362.2 MiB | .mat files included for reference
[File] FLORENCE_PILOT_ECG_npz.zip | 384.6 MiB |
```

You can edit comments and selection tags manually, then republish only `manifest.json`. No ETL run or file rehash is needed when the downloadable bytes have not changed. Leave those files' sizes/hashes untouched. Keep annotations when regenerating a future manifest; replacing it with an unannotated inventory would lose them. The client retrieves the changed manifest through its normal update flow.

## Folder-selection boundaries

The databank root, `zips/`, and `curated/` have no **Download files in this folder** or **Download this folder and all subfolders** actions. Selecting every file in one of those containers through the checkbox list is also rejected when it would cover the whole tree. Individual files and smaller selections remain available.

Open a narrower folder, such as `curated/FLORENCE/Clinical/`, to enable immediate or recursive folder downloads. Only manifest-listed files are included; sibling paths are excluded. All downloads still use the single location confirmation, progress bars and per-file size/SHA-256 checks. ZIPs remain intact.

`manifest.example.json` demonstrates every category using **illustrative hashes/sizes**. Replace them before publishing it; it is not a live databank manifest.
