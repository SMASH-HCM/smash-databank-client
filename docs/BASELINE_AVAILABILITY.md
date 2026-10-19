# Post-assessment/pre-intervention baseline availability

Version 0.9.0 keeps the agreed prediction-day measurement boundary and an initial conservative event-role mask. The design reference is `digitaltwin_moe/docs/methods/index_landmark_generation.md`, section 6 (requested 29 September 2026), also retained in the WP2 model-audit handoff. These documents inform the implementation; runtime reads only the supplied OMOP database, not a WP2 report or checkout.

## Intended prediction time

Predict after the diagnostic assessment, before new therapeutic decisions at that assessment. Measurements recorded on the baseline day can be predictors. New prescriptions, treatment initiations/changes and therapeutic procedures decided that day must not enter the pre-decision model. Earlier established history may be used only in an explicitly selected history/as-of export; it is not carried into an exact-day snapshot. This is not a blanket exclusion of diagnostic procedures, or a claim about untreated outcomes.

The ETL anchor remains `smash_endpoint_censor.baseline_date/baseline_age`; it is never inferred from a later test or selected backwards from an endpoint. No event after that date is admitted. Existing missing/duplicate-anchor and unit/conflict checks remain in force. All selected people require valid anchors; no one is silently dropped to make an export succeed.

## Policies

`--availability-policy post-assessment` is the new tabular default and menu behaviour. The default tabular layout examines only the exact baseline date, with one column per selected concept. It has no carry-forward or window-derived features. An earlier-history lookup requires explicit `--tabular-mode latest-history --lookback-days <N>`. The availability mask applies after that explicit time selection:

- Same-day Measurement facts are admitted, with the usual numeric/category/unit QC.
- Explicit diagnostic Procedure IDs are admitted: 37311810 (stress echo), 4065278 (ambulatory ECG), 4082987 (cardiac MRI), 4163951 (ECG procedure), 4230911 (echo), 42710007 (cardiac morphology/function MRI with contrast).
- A small explicit clinical Observation list is admitted on that day, including minimum heart rate, GFR, demographic/family-history and selected clinical-history/finding concepts. Exact IDs are versioned in `availability.py` and copied into every export's policy JSON.
- Other same-day condition, observation, drug, device and procedure records are held out as unreviewed or potentially therapeutic. This does not classify every excluded record as a new treatment: uncertainty is the reason for holding it out. Earlier evidence can still supply the feature.
- Administrative/follow-up/endpoint-derived observations and the specific death, generic Event and ESC ICD recommendation concepts are held out even if dated earlier. The mask is independent of the requested variable list; held features remain blank with an audit reason.
- Generic medication-history Observation 3021806 remains held for unresolved class context. A general class-aware history representation or row-level new-prescription status is not inferred from its concept ID.

`--tabular-mode latest-history --lookback-days <N> --availability-policy strict-before` preserves the historical timing control. Same-day facts are excluded. Strict timing alone does not remove every retrospective administrative/outcome-derived field, so these controls are not automatically model-ready predictors. Match the policy as well as the frozen variable list across train/test exports.

```powershell
.\smash-hcm-databank-client.exe export --db .\SMASH_v1.4_rc4.db --format tabular --cohort "Rennes Training" --vars core --availability-policy post-assessment --out .\rennes-train
.\smash-hcm-databank-client.exe export --db .\SMASH_v1.4_rc4.db --format tabular --cohort "Rennes Test" --variables-file .\rennes-train\variable_set.json --availability-policy post-assessment --out .\rennes-test
```

Event exports remain full history. The CLI rejects an availability-policy option for events to avoid suggesting that a full-history stream has already been cut at baseline. Consumers must apply their prediction-time and intervention masks downstream.

## Audit and remaining limitations

Each tabular dataset includes `availability_policy.json`, `availability_exclusions.csv`, policy/version information in `dataset_manifest.json`, and the usual feature provenance. Removed-event records include person/landmark, table, concept, fact ID, date and exclusion reason. The manifest counts removed events and affected people. These files are patient-level and stay in protected storage.

RC4 lacks a general intraday/source-role ledger identifying every new treatment decision versus previously established treatment merely documented that day. The initial explicit allowlist/holdout mask is conservative and requires further clinical/source review for broader inclusion. It does not complete every source-specific part of backlog B027, infer assessment completion times, construct endpoint-specific risk sets or generate outcome labels. The full-history reports remain descriptive and are not altered to pretend that they are prediction-time feature inventories.

Rennes illustrates why the distinction matters: all 10,537 loaded measurements are on the baseline date. Strict-before controls omit them; post-assessment exports can use the eligible measurement values while retaining intervention/outcome exclusions. Source database dates and contents are not changed.

## Snapshot layout

`data.csv` has exactly `person_id, site, cohort, snapshot_date`, followed by one column per selected `(table, concept_id)`. No mean, sliding-window, recency, count, previous-value or previous-age columns are added. Conflicting same-day values are held blank rather than averaged. Identical duplicate records do not add columns. Sample ages, units and evidence/QC audits remain in separate companion files. RC4 CORE has 37 feature keys, producing 41 main CSV columns. FLORENCE labels replace SHaRe in the export interface; the original cohort name and ID remain in provenance.
