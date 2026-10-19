# RC4 database feedback for the ETL/database agent

**19 October update:** the file at the original RC4 path has changed to a 573,896,232-byte PostgreSQL custom-format dump. The findings below describe the SQLite snapshot tested on 18 October. The current client needs a SQLite export; see [the format-change handoff](RC4_FORMAT_CHANGE_2026-10-19.md).

Validated 18 October 2026 against `K:/SMASH_DATA/smash-data-bank/SMASH_v1.4_rc4.db` using omop-exporter 0.9.0. This handoff contains aggregate findings only. Patient-level audit records remain in the protected validation directory.

## Scope and overall result

SQLite integrity, checked person links, endpoint keys and train/holdout disjointness passed. The database contains 2,984 people, 23 cohort definitions, 2,984 unique anchor-ledger entries and 11,936 endpoint-ledger entries (four endpoint types per person). Five report types and cohort-specific tabular/event examples were generated. The exporter suite passed 226 tests, including read-only RC4 integration checks.

The database is usable for descriptive reports, full-history event exports and selected exact-day tabular exports. Full FLORENCE Training/Pilot tabular exports remain blocked by incomplete baseline anchors. Successful technical extraction does not establish prediction readiness or clinical equivalence.

All database access was read-only. Source size: 3,632,111,616 bytes. SHA-256 before and after validation: `48bbb9835ed403c6a53b4e4bb9bdd20334a9b91bbf08376772895d1efbae3843`. No independently published expected release checksum was available for comparison.

## 1. Release blockers and naming corrections

### A. Complete or explicitly account for 151 missing baseline date/age pairs

The anchor ledger has a row for each person, but 151 rows lack baseline date/age values; all affected people are FLORENCE.

| Cohort/group | Members | Missing baseline date/age |
|---|---:|---:|
| SHaRe Training (intended label FLORENCE Training), ID 1101 | 2,140 | 124 |
| SHaRe Pilot (intended label FLORENCE Pilot), ID 1100 | 536 | 21 |
| FLORENCE people outside the named All Patients cohort | 6 | 6 |
| Total affected distinct people | | 151 |

The first two rows account for 145 affected members of the **2,676-person** source FLORENCE/SHaRe All Patients cohort. The person table contains 2,682 FLORENCE people, including the six outside that cohort. These groups must be reconciled without double counting.

**Requested action:** restore protocol-defined baseline dates and ages from source evidence where possible. If unavailable, record an explicit reason and define analytical eligibility/exclusion rather than silently filling dates from a later measurement or outcome. Check `smash_endpoint_censor.baseline_date` and `baseline_age` and the ETL source mapping that populates them.

**Impact:** the exporter refuses a full selected-cohort tabular export with missing anchors; it does not silently drop patients or invent prediction dates.

**Acceptance:** each intended prediction-cohort member has a valid protocol-defined anchor, or a separately documented exclusion/eligibility rule makes the intended export population explicit.

**Evidence:** `audit/baseline_issues.csv` and `audit/cohort_baseline_coverage.csv`.

### B. Reconcile six people absent from All Patients/source cohorts

`person` contains 2,984 people; SMASH All Patients (ID 1000) contains 2,978. FLORENCE has 2,682 person rows but its source/All Patients cohorts contain 2,676. The six-person discrepancy coincides with the six additional missing-baseline cases above.

**Requested action:** determine whether these are intentionally retained but analytically ineligible records, missed cohort assignments, or another ETL issue. If exclusions are intentional, encode the reasons and clarify the meaning of “All Patients.” Do not automatically add them to cohorts without resolving their status.

**Acceptance:** cohort membership reconciles to the intended person population with explicit reasons for any difference.

**Evidence:** `audit/people_outside_all_patients_cohort.csv` and `audit/cohort_baseline_coverage.csv`.

### C. Rename exported analytical cohort labels from SHaRe to FLORENCE

Affected definitions include ID 1100 `SHaRe Pilot`, 1101 `SHaRe Training`, 1200 `SMASH Source SHaRe`, and 1202 `SHaRe All Patients`.

**Requested action:** use FLORENCE as the canonical site label in cohort definitions and other user-facing site metadata. Retain SHaRe as source provenance/alias where appropriate; preserve stable IDs and membership.

The exporter currently supplies a display-name adapter, so its FLORENCE output labels do not mean the source database names have been corrected.

**Confirmed naming convention:** PILOT versus TEST is only a naming distinction for this workflow. Preserve distinct cohort IDs and memberships. The standard exporter layout can use `test.csv` for a Pilot held-out cohort while retaining its original name and ID in provenance; no membership changes or new split are implied.

**Acceptance:** newly generated reports and exports can obtain the intended FLORENCE labels directly from database metadata, with original source provenance retained.

## 2. Data semantics requiring review

### D. Explain missing censor dates and the event-after-censor case

There are 152 missing censor dates and one dated positive OVERALL endpoint after its recorded censor date. The 152 censor-date gaps are a separate finding from the 151 baseline gaps; their overlap should be checked rather than assumed.

**Requested action:** audit censor derivation and explain missingness. For the event-after-censor case, establish whether censor means last clinical contact, last outcome ascertainment, or another endpoint-specific follow-up boundary. The existing observed-event policy can allow a flagged event after last clinical contact, so this is not automatically a corrupt event or a reason to truncate/move its date.

**Acceptance:** documented censor semantics, explicit missingness/ascertainment reasons, and an intentional disposition for the flagged event. Do not manufacture dates simply to make validation pass.

**Evidence:** `audit/events_after_censor.csv`, anchor/censor ledger and endpoint reports.

### E. Preserve context for conflicting same-day measurements

In the Rennes Training exact-day CORE export, conflicting same-day values leave 139 systolic and 132 diastolic blood-pressure feature cells blank. These are counts of affected patient-feature cells, not necessarily disjoint people or raw-row counts. Example concept IDs: systolic 4152194; diastolic 4154790. Troponin T (4005525) also needs review for incompatible unit evidence flagged by the exporter.

**Requested action:** review source variables, assessment context, units and timestamps. Determine whether repeated BP values represent different settings, such as rest/exercise, duplicates or inconsistent mapping; that explanation has not yet been established. Preserve distinguishable contexts in the database and specify a clinically reviewed selection rule where a single snapshot value is intended. For troponin, verify the analyte, assay and unit mapping before any conversion.

**Acceptance:** snapshot selection can distinguish the intended measurement without averaging incompatible observations or choosing arbitrarily. Valid contextual repeats should remain available in full event history.

**Evidence:** exact-day `snapshots/rennes-training-core/feature_provenance.csv`, `variables.csv`, and distribution/unit reports. The provenance file contains patient-level records.

### F. Expose assessment-versus-treatment-decision provenance

The agreed prediction point is post-assessment, pre-intervention. Baseline-day clinical measurements can be eligible; new prescriptions, treatment changes and therapeutic decisions made at that visit must be excluded. RC4 does not provide a general source-role/intraday ledger sufficient to classify every relevant row reliably.

**Requested action:** where supported by the source, embed roles/provenance that distinguish diagnostic assessment, established therapy documented at the visit, new treatment initiation/change, therapeutic procedures and retrospective outcome/administrative facts. Preserve actual times when available and explicit unknowns where they are not. Diagnostic procedures must not be excluded simply because they occur on the baseline date.

**Impact:** the exporter uses an initial conservative allowlist/holdout policy. Some same-day facts remain unavailable because their role is unresolved. This is a shared data-contract requirement, not proof that every held fact was a new treatment.

**Acceptance:** a versioned, source-reviewed availability contract embedded in the database, sufficient for the agreed baseline policy. The exporter must continue to work from the database alone, without a separate WP2 report.

### G. Document Rennes date precision and source timing

All 10,537 loaded Rennes measurements occur on the baseline day. This is compatible with baseline assessment data, but strict-before extraction omits all of them.

**Requested action:** confirm that this reflects source availability and intended ETL dating, rather than a fallback that collapsed historical observations onto baseline. Document date precision and whether earlier measurements genuinely exist in the source.

**Acceptance:** transparent timing provenance. This finding alone is not evidence of incorrect dates, and dates should not be shifted to accommodate the exporter.

## 3. Release metadata and feature-contract improvements

### H. Embed an explicit release identifier

No explicit embedded release-version tag was found; `v1.4_rc4` is currently identified by the supplied filename. Existing ETL manifest metadata is readable.

**Requested action:** embed release ID, database schema/export-contract version, build timestamp and relevant ETL/vocabulary/source provenance in the database. Publish the completed file size and SHA-256 in the adjacent databank manifest. A checksum of the entire completed database belongs outside that same file to avoid a self-reference problem.

**Acceptance:** renaming the local file does not lose release identity, and downloads can be verified against a publisher-provided checksum.

### I. Agree and version the CORE feature definition

Current structural overlap is **37 `(table, concept_id)` pairs** across all three sites, plus **32 exclusive two-site pairs**. The illustrative expectation of 36 features should be reconciled against the actual list; it is not grounds to drop a feature automatically.

**Requested action:** compare the concept lists with the intended clinical CORE specification and publish a versioned definition inside the database where feasible. Confirm domain, meaning, unit/category representation and prediction-day availability. Shared concept presence in full history does not guarantee complete baseline coverage or equivalent source definitions.

**Acceptance:** an agreed concept-level feature list and documented structural-versus-clinical definition. The current default CSV has four metadata columns plus one column per selected feature: 41 columns for the observed 37 CORE pairs.

**Evidence:** overlap reports and frozen `variable_sets/` / snapshot `variable_set.json` files.

### J. Clarify ECG-derived fields and external-asset linkage

The current ECG-labelled measurement preset yields an entirely missing Rennes Test snapshot and an empty Tampere Pilot event example. This preset is name-based and narrow: it does not cover every ECG diagnosis, procedure or waveform. These results do not prove absence of raw ECG data.

**Requested action:** identify the intended ECG-derived concepts and sites/cohorts where they should exist. Review their domain and timing mappings. Document how `associated_file` and image-related tables link to adjacent ECG/MRI/Echo files; no `smash_asset` table was found, which is not itself a requirement to add one. Include stable relative paths/asset identifiers, modality, processing representation, cohort linkage and publisher checksums in a documented database/manifest contract as appropriate.

**Acceptance:** consumers can distinguish unavailable clinical features from unmapped feature presets and missing external downloads. Actual adjacent-file availability was not validated in this database-only exercise.

### K. Review 180 file-catalogue records without person linkage

The per-patient inventory found 68,390 `associated_file` catalogue records (10,278 ECG, 30,272 Echo and 27,840 MRI). Of these, 68,210 have a non-null person link; 180 do not. These are catalogue-record counts, not evidence of downloaded files or distinct imaging studies.

**Requested action:** review `patient_linkage_status` and source keys for unlinked records. Restore valid linkage where supported, or record why linkage is intentionally unavailable. The patient report cannot attribute these records to individual patients.

**Acceptance:** unlinked assets are explicitly accounted for. Per-patient totals reconcile to attributable catalogue records rather than incorrectly assigning or silently counting unlinked records.

### L. Training-index count is unavailable in RC4

No recognised explicit training-index ledger was found. The patient report therefore leaves `training_index_count` unknown and supplies a status explanation; it does not report zero or manufacture annual indices from follow-up duration. Baseline and endpoint ledgers are present.

**Requested action:** if multiple training prediction indices are intended to be supplied by ETL, document/embed their ledger and eligibility semantics. Otherwise designate their generation as an exporter/model workflow with an explicit endpoint/risk-set policy. This is a contract gap, not a claim that baseline anchors or endpoint ledgers are absent.

## 4. Exporter-owned findings: do not report these as database corruption

- **NYHA numeric classes:** concept 35621756 is unitless; the generic exporter numeric-unit guard currently holds these values. This requires reviewed ordinal/categorical handling in the exporter. Do not invent a physical unit to bypass the guard. ETL should confirm the intended encoding.
- **Full ETL schema names:** `results__cohort`/`results__cohort_definition` coexist with empty CDM cohort tables. The exporter now reads the embedded schema map and handles these names; the analytical cohort tables were not absent. Preserve a documented unambiguous mapping.
- **Large vocabulary performance:** sparse cached clinical-concept lookup fixes the exporter's previous handling of the 4,085,317-concept vocabulary. A full vocabulary is not itself a database defect.
- **Tabular layout:** default output is now an exact-day snapshot with no implicit carry-forward, averaging or derived history columns. Latest-history lookup requires explicit mode and lookback. This was an exporter correction, not an ETL repair.
- **Outcome/risk-set construction:** the validation examples are feature exports. Endpoint-specific eligibility, risk sets and outcome labels still need an explicit modelling contract; their absence from a feature-only CSV is not proof that endpoint ledgers are missing.

## Evidence and requested return from the database agent

Protected output root: `K:/SMASH_DATA/omop-exporter/rc4-validation-2026-10-18/`. Start with its `README.md`; aggregate cohort evidence is in `audit/cohort_baseline_coverage.csv`. Patient identifiers in other audits/provenance should remain in protected storage.

Please return an item-by-item disposition: confirmed defect, intentional policy, source limitation, or consumer/exporter issue; the affected cohort/concept/source; the chosen remediation or explicit exclusion; and the release in which it will be addressed. Prioritise anchor completeness and population reconciliation, then canonical labels and censor semantics. Re-run the same audits after regeneration so count changes can be explained.
