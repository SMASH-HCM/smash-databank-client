> This document describes the retained historical PostgreSQL/CSV preparation workflow. For the database-only SQLite client and its current scope, see [DATABASE_CONTRACT.md](DATABASE_CONTRACT.md) and [SETUP.md](SETUP.md). The sparse exporter now suppresses numeric means when numeric units are unknown or mixed.

> Current SMASH-HCM Databank Client: default tabular exports are exact-day snapshots under the post-assessment/pre-intervention mask. History/derived columns are explicit options. This document preserves the older PostgreSQL/CSV pipeline. See [DATASET_EXPORTS.md](DATASET_EXPORTS.md) and [BASELINE_AVAILABILITY.md](BASELINE_AVAILABILITY.md).

# Export methodology

This document describes what `python -m smash_hcm_databank_client.legacy.main all --config config.yaml` writes and how to interpret the event-stream and tabular outputs. The CSVs are data contracts, not a fitted model or a clinical validation. Keep patient-level outputs outside Git in a protected directory.

## Release and source tables

`restore` loads the configured PostgreSQL dump into an existing empty database. `export` runs the versioned queries in `export_smash_omop.sql` against `cdm` and `results` tables. It writes `person.csv`, `cohort_membership.csv`, `observation_period.csv`, `death.csv`, `omop_events.csv`, `smash_endpoint_censor.csv`, and `smash_endpoint_event.csv`, plus `export_manifest.json`. The event union covers condition, measurement, observation, procedure, and drug records; it preserves `concept_id`, date, numeric value, categorical value concept ID, and unit concept ID where those columns exist. It excludes SMASH registry-management observations. It does **not** join concept names, raw DICOM/ECG/PDF files, or source-column provenance. `vocabulary.concept` in the restored database contains human-readable names, including ETL custom concepts. A local vocabulary SQLite index may omit custom concepts unless those rows have been inserted.

For the current cardiac release, `prepare` uses the versioned ETL endpoint and censor ledgers. `build_etl_release_data.py` cross-checks site and cohort split membership and writes `patient_manifest.csv`, `horizon_labels.csv`, `age_omop_events.csv`, `preindex_omop_events.csv`, and `extract_audit.json`. Older dumps without ledgers use the source-CSV fallback in `build_smash_experiment_data.py`; do not mix its label assumptions with current-ledger results. The Florence calendar uses a synthetic birth anchor, so model age and elapsed time, not the apparent calendar year. Patients with missing age/date anchors or implausible derived ages are omitted from the age stream and counted in the audit.

## Event stream

`omop_events.csv` is the dated, long-form union of OMOP records. One row is one dated fact for one patient. `age_omop_events.csv` converts each valid event to a patient-age coordinate:

```text
patient_age_at_event_years = baseline_age_years
    + (event_date - index_date).days / 365.2425
years_from_anchor = (event_date - index_date).days / 365.2425
```

The age stream retains `person_id`, `domain`, `concept_id`, `value_as_number`, `value_as_concept_id`, and `unit_concept_id`. It is **not** one row per patient, one row per day, or a padded neural-network tensor. Consumers sort by patient age and choose an availability boundary for each prediction landmark. The SMASH-ES model groups same-day facts into day sets in its data loader; that grouping is downstream of this export. Source-level timing within a day, assessment phase, and source-column provenance are absent, so inclusion of all events on a landmark day is an exploratory end-of-day assumption requiring leakage review. Events after a landmark must never enter that landmark's input.

## Study landmarks and outcome labels

`build_rolling_landmarks.py` creates endpoint-specific rows in `landmarks.csv` and `landmark_horizon_labels.csv`. The baseline index date is the ETL ledger's age/date anchor. A training patient may also receive annual anniversary landmarks up to `--max-training-years` (default five), only while still at risk. A `-TEST` patient receives the fixed baseline landmark only. Each row has remaining time to the dated endpoint or censor date and an event indicator; a separate 1-, 2-, or 5-year label is positive for an observed event within that horizon, negative when known event-free through the horizon, and blank when censored before the horizon. Undated positives, unascertained endpoints, cohort-status conflicts, prevalent/same-day outcomes, and inadequate follow-up are excluded according to the code's checks and reported in `landmark_audit.json`. `sample_weight` is inverse to the number of eligible landmarks for that patient/endpoint. An endpoint-specific `landmark_id` must not be collapsed with another endpoint's row.

The prediction boundary is a **consumer decision**: historically, events strictly before the landmark date were used; the exploratory end-of-baseline-day policy includes dated events on that day as well. This changes input features, not the ETL endpoint ledger or the database. It does not automatically include a CMR or other test performed days after the anchor. A subsequent clinical prediction could use a later landmark, but it needs its own outcome horizon and availability audit.

## Sparse tabular view

`python -m smash_hcm_databank_client.legacy.main tabular --config config.yaml` calls `export_omop_tabular.py` using `age_omop_events.csv` and, by default, `landmarks.csv`. The output is **long/sparse**: one row per selected patient, landmark, domain, and concept **when at least one qualifying event exists**. It is not one wide row per patient. Config filters can select sites, splits, endpoint-specific landmarks, OMOP domains, concept IDs, cohort IDs, and a lookback period. `input_sources` requires a provenance-enriched stream and fails on the current export. With `tabular.landmarks: false`, the exporter instead uses one generic age anchor per selected patient, without endpoint labeling.

For each `(patient, landmark, domain, concept)` group, the exporter computes:

| Field | Meaning |
| --- | --- |
| `event_count` | Number of qualifying events in the lookback window. |
| `latest_event_age_years` | Largest event age in that group. |
| `years_since_latest` | Landmark age minus latest event age. |
| `latest_numeric_mean` | Mean numeric value among events at the latest event age, if present and units do not conflict. |
| `window_numeric_mean` | Mean of **all** numeric values in the window, if present and units do not conflict. |
| `latest_value_as_concept_id` | Categorical value ID when the latest-age events agree on one nonzero value. |
| `unit_concept_id`, `unit_conflict` | The single nonzero unit ID if one exists; conflict flag when multiple nonzero IDs occur. Blank unit is **not** proof of a known clinical unit. |

The CLI default is strict `event_age < landmark_age` (with a small floating-point tolerance). Direct CLI use of `--include-landmark-day` applies an inclusive age boundary for a same-day sensitivity export. **`main.py tabular` currently does not forward that flag from YAML**, so the default YAML workflow remains strict. If comparing with models that include landmark-day records, generate a matching sparse view explicitly and audit date/age rounding and source availability. The current export has no source name or concept name columns; resolve IDs against the restored `vocabulary.concept` or an up-to-date lookup for display, while retaining the IDs as stable keys.

The numeric summaries are provisional. In the 25 September cardiac export, 33 measurement events across two patients carry `value_as_number` in the `208100`–`208199` range; they produce implausible window means when mixed with ordinary measurements. Review their ETL mapping before using value aggregates as predictors. A blank numeric field can mean that no numeric value was present or that unit conflict suppressed the mean; inspect `unit_conflict` and source events rather than imputing a clinical zero.

## Relationship to model inputs

The current CoxPH, XGBoost AFT, and DeepSurv scripts in `digitaltwin_moe` **do not read the sparse tabular file**. They join `landmarks.csv` to `patient_manifest.csv` and summarize `omop_events.csv` into age, sex, years since anchor, and per-domain all-prior count, two-year count, and recency (18 candidates, with zero-variance columns removed on the Florence development fold). Consequently, those baselines do not use individual concept IDs or measurement values. SMASH-ES uses the event stream's concept/value/unit/age fields through its own snapshot data loader. A concept-value baseline requires a separate, explicit wide feature policy and a source/unit QC pass.

To make a dense clinical table later, pivot a prespecified concept list to one row per **patient, endpoint, and prediction landmark**, with named columns such as `measurement__<concept_id>__latest_value`, `__count`, `__recency`, and missingness flags. Retain a companion dictionary with concept name, source, aggregation, unit, lookback, and availability rule. Define the feature list and preprocessing from training data only, and retain labels in a separate table until the supervised join. Unrestricted pivoting of every concept creates unstable, high-dimensional features and makes leakage harder to audit.

## Reproducibility checks

Record the dump identifier/hash, export SQL hash, ETL endpoint definition version, cohort split, landmark policy, lookback, concept filters, and model input boundary. Inspect `extract_audit.json` and `landmark_audit.json`, verify that every model input event is available at its landmark, and keep all patient-level exports outside Git. A successful schema export does not validate endpoint definitions or clinical measurement units.
