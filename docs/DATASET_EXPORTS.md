# Dataset exports and reports

Version 0.10 adds the standard DATA_DIR layout, menu configuration, explicit history features, feature families and a patient inventory. Everything is calculated from the local OMOP database. No WP2 report, PostgreSQL connection or fitted preprocessing is required.

## Locations and cohort memberships

Choose the confirmed local directory in Setup, or confirm/change DATA_DIR in the export/report menu. That choice is saved in local application settings, separate from credentials. CLI users can supply `--data-dir` directly.

```text
DATA_DIR/
  FLORENCE/
    train.csv
    test.csv
    train/                     # manifest, frozen variables, provenance and QC
    test/
  RENNES/train.csv
  RENNES/test.csv
  TAMPERE/train.csv
  TAMPERE/test.csv
  event_stream/
    FLORENCE-TRAINING/omop_events.csv
    RENNES-TEST/omop_events.csv
  reports/
    patients.csv
    patients.txt
    patients/report.json
    cohorts.csv
    cohorts.txt
    overlap/core.csv
    overlap/two_site.csv
    features.csv
    features/report.json
```

The group directory comes from the cohort name without its split suffix. TRAINING/TRAIN writes `train.csv`; TEST/PILOT writes `test.csv`; EVALUATION/EVAL writes `evaluation.csv`; ALL/ALL PATIENTS writes `all.csv`. Other named cohorts use their own group directory and `data.csv`. Source SHaRe labels are displayed as FLORENCE. Events retain the whole displayed cohort name in the directory.

PILOT and TEST are naming distinctions; original IDs and memberships remain in the manifest. The exporter does not create a random split or combine cohort populations. If two selected definitions would map to the same output path, it stops rather than merging them. Select separate DATA_DIRs for those definitions or alternative feature/configuration runs. Existing datasets and reports are never silently overwritten. Cohorts in one menu batch share the same frozen feature schema; generate held-out data with the training `variable_set.json` when running separate commands.

`--out` remains an explicit low-level bundle destination for scripts: it writes `data.csv` or `omop_events.csv` inside a new directory. `--out` and `--data-dir` are mutually exclusive. The menu uses the standard DATA_DIR layout.

See [INDEXING_AND_LANDMARKS.md](INDEXING_AND_LANDMARKS.md) for the difference between the fixed baseline, an input history window, an outcome horizon and repeated training landmarks.

## Tabular configuration

The default is one patient, one baseline day, one selected source feature per column. Four metadata fields precede the features: `person_id`, `site`, `cohort`, `snapshot_date`. There are no history-derived columns, averages, implicit carry-forward, scaling or imputation. Baseline ages, source units and provenance live in companion files. Conflicting same-day values remain missing; identical repeats collapse without averaging.

Select one or more existing cohorts, choose variables, choose Tabular, then choose:

| Setting | Behaviour |
|---|---|
| Exact baseline day (default) | Only eligible facts on that calendar date; standard feature columns |
| Latest history | Explicit positive lookback, e.g. 365 days; latest eligible value on/before baseline |
| Availability policy | Post-assessment/pre-intervention, or strict-before as an explicit history control |
| Optional history columns | Previous value, previous age in days, latest age in days, count, mean, min, max |

History columns require `--tabular-mode latest-history --lookback-days N` and explicit `--history-features` names. No derived history feature is enabled by default. A lookback of N includes the Nth day before baseline through the allowed baseline boundary. Strict-before excludes day zero.

- `previous-value`: value on the preceding distinct eligible observation date before the latest selected date. It is not a duplicate row from the same day and is not necessarily yesterday. A conflicting preceding date stays missing rather than falling back further.
- `previous-age-days`, `last-age-days`: elapsed days from that observation date to baseline; these are recency measures, not patient age.
- `count`: number of QC-valid distinct observed dates in the configured window. Identical same-day repeats count once. A window without evidence stays missing, not a proven zero event count.
- `mean`, `min`, `max`: explicit numeric summaries over QC-valid daily values in that window. Conflicting daily values are excluded; category concept IDs and incompatible/unknown units are not averaged. The original source feature remains the latest value, not a mean.

Each extra adds one column per selected source feature. For example, 26 measurements with `previous-value` and `previous-age-days` yields 78 feature columns plus four metadata fields. Families and derived history columns currently require separate exports. `feature_definitions.json`, `variable_set.json` and `dataset_manifest.json` freeze the settings and source mapping; `feature_provenance.csv` retains values' dates and QC information.

These are common longitudinal feature-engineering strategies: OHDSI supports explicit index-relative covariate windows, and scikit-learn demonstrates lagged values and rolling summaries. They are optional modelling choices, not automatically better features. Recording intensity can itself encode site/care patterns; a configured window does not prove observation coverage. References: [OHDSI temporal covariates](https://ohdsi.github.io/FeatureExtraction/reference/createCohortBasedTemporalCovariateSettings.html), [scikit-learn lagged-feature example](https://scikit-learn.org/stable/auto_examples/applications/plot_time_series_lagged_features.html).

Annual/multiple prediction indices, endpoint-specific risk sets, outcome labels, slopes and automatic imputation are not generated by these options. Moving the prediction date requires its own reviewed eligibility/outcome policy. Keep all indices of a patient in the predefined patient split. Fit encoders, imputers and scalers using training data only: [scikit-learn leakage guidance](https://scikit-learn.org/stable/common_pitfalls.html).

## Available feature sets

Counts below describe the 18 October SQLite RC4 snapshot, not a fixed count promised across releases or evidence about a replacement file. Friendly names below are canonical; old preset identifiers remain CLI aliases.

| Preset | RC4 source variables | Meaning |
|---|---:|---|
| `shared-clinical` | 37 | Exact table/concept presence across all three sites |
| `shared-extended` | 69 | CORE plus 32 exclusive two-site variables |
| `two-site-only` | 32 | Exclusive two-site variables only |
| `shared-measurements` | 26 | Measurement-domain subset of CORE |
| `starter-measurements` | 8 | Fixed small measurement starter list, preserving missing columns |
| `all-measurements` | 105 | All observed measurement-domain concepts |
| `ecg-measurements` | 3 | ECG-labelled measurements matched by name; narrow and not waveform processing |
| `diagnoses` | 60 | All observed condition concepts |
| `all-clinical` | 250 | All observed clinical table/concept pairs, excluding management concepts |
| `shared-grouped` | 42 inputs → 36 output features | CORE with the MR grade family replacing its separate CORE grade indicators |

The eight starter measurements are height (607590), weight (4099154), BMI (4245997), systolic BP (4152194), diastolic BP (4154790), LVEF (4108582), interventricular septal thickness (3021917), and LVOT maximum systolic gradient (3026578). This is a transparent convenience list, not a validated HCM score or a claim that every source measure has equivalent acquisition context.

The menu can also search the complete variable catalogue by name, concept ID or domain, multi-select variables, name/save a set, and load it later. `report features` produces the complete source concept lists for the presets; `report overlap` gives CORE and exclusive two-site lists with site coverage. Exported frozen lists retain table and concept IDs. Reuse the training list for test data, rather than discovering a new list or a new column order at test time.

## ESC Risk-SCD clinical inputs

`--vars esc-risk` selects seven fixed source concepts plus `baseline_age_years` from the anchor ledger. The output has **8 feature columns + 4 metadata columns** when no history extras are requested. Missing concepts retain blank columns. It does not calculate an ESC score or export the previously calculated score/recommendation as an input.

| Required clinical input | Export source | Review needed |
|---|---|---|
| Age at assessment | `baseline_age_years` from `smash_endpoint_censor` | Recorded baseline age, not age at diagnosis |
| Maximum LV wall thickness | `measurement__4353969` | Segmental-thickness concept includes mixed contexts; confirm maximum and appropriate modality |
| Left atrial diameter | `measurement__3023614` | Confirm antero-posterior diameter, timing and mm units |
| Maximum rest/Valsalva LVOT gradient | `measurement__3026578` and `measurement__2000001122` | Resting and provoked retained separately; no automatic max, unit conversion or assumption that provocation is Valsalva |
| Family history of SCD | `observation__46270007` | Confirm relatives/age/HCM criteria and coded yes/no definitions |
| NSVT | `condition_occurrence__40480274` | Confirm qualifying rhythm/duration and prior-to-index ascertainment |
| Unexplained syncope | `condition_occurrence__135360` | Generic syncope does not establish unexplained syncope |

The seven clinical inputs follow the [ESC HCM Risk-SCD variable definitions](https://www.escardio.org/static-file/Escardio/Guidelines/publications/HCMESC%20HCM-Web%20addenda.pdf). These OMOP pairs are **candidate mappings for input review**, not a validated equivalence catalogue. Review source definitions, timing and units before score calculation. The strict same-day role mask may withhold NSVT/syncope conditions. No record does not establish a negative history. Do not override missingness or use future follow-up to complete baseline inputs. For event exports the same set selects raw source events only; anchor age is not fabricated as a clinical event.

Fixed source sets and the optional age field survive saving/loading and train/test schema freezing. See the [custom-variable tutorial](TABULAR_TUTORIAL.md) for the JSON contract.

## Category-family consolidation

Exact concept overlap can underestimate shared clinical variables. “Mild”, “moderate” and “severe” may be different concepts in one underlying variable, and a site without severe cases need not lack the variable. Do not identify such families by name similarity alone or treat absent categories as confirmed negatives.

The initial, explicit MR family maps:

| Concept ID | Category |
|---:|---|
| 2000001130 | trace |
| 2000001131 | trace-mild |
| 3654726 | mild |
| 2000001132 | mild-moderate |
| 3654727 | moderate |
| 2000001133 | moderate-severe |
| 3654728 | severe |

The opt-in `shared-grouped` preset emits one `mitral_regurgitation_grade` categorical column instead of the separate MR category source columns. It includes all seven source category concepts even if some occur in fewer than three sites. It selects a uniquely recorded grade on the latest eligible date; conflicting grades remain unknown. It does not collapse trace/intermediate grades, assume absence means no regurgitation, or assign an arbitrary numeric severity score. Unspecified MR (443962) is not assigned a severity. Saved sets carry the versioned family definition.

This is an initial candidate family mapping, not a completed clinical-equivalence catalogue. The conservative same-day condition-role mask still applies, so consolidation alone does not make held baseline-day conditions available. Further families require explicit source-reviewed mappings. Event exports select the family's raw concepts and retain individual events; they do not turn event rows into consolidated snapshot columns. One-hot encoding can be performed downstream with a fixed category schema fitted/declared from training data.

## Event stream configuration

Select cohorts, variables and Event stream in the menu, then configure:

- Full history (default), or Baseline prediction scope.
- Domains: condition, measurement, observation, procedure, drug, device.
- Optional inclusive calendar start/end dates.
- For baseline scope: optional positive lookback and availability policy.
- Optional metadata: source value, fact ID/table, site, days before baseline and approximate event age from the baseline age.

The standard event fields remain `person_id, domain, concept_id, event_date, value_as_number, value_as_concept_id, unit_concept_id`. Stable ordering is by patient, date, domain, concept and fact ID. No resampling, aggregation or artificial prediction indices are introduced. Full history can contain future information relative to a baseline and is not automatically prediction-ready. Baseline scope requires complete valid cohort anchors, removes events after baseline and applies the configured treatment/administrative/outcome mask. Calendar filtering alone does not supply that protection. Manifests record excluded-event reason counts and all settings.

## Baseline caveats

The prediction point is after diagnostic assessment and before new therapeutic decisions. Eligible baseline-day measurements can be used; same-day new treatment initiation/changes and therapeutic decisions must be excluded. Earlier established treatment/history is available only through explicitly configured history. Diagnostic procedures are not blanket-excluded. Retrospective outcome, follow-up and administrative facts are held by the availability policy.

RC4 lacks a complete intraday/source-role ledger. The current mask is conservative; it may withhold legitimate clinical history that cannot yet be classified safely. It is not a guarantee of complete leakage prevention for every source-specific fact. Outcome labels and endpoint-specific risk-set construction remain separate. See [BASELINE_AVAILABILITY.md](BASELINE_AVAILABILITY.md).

RC4 has 151 missing FLORENCE baseline date/age pairs, including 124 Training and 21 Pilot members. Those full tabular/baseline-event requests remain blocked. No dates are inferred and no patients are silently dropped. Full-history events and descriptive reports remain available. All Rennes measurements are dated on baseline day, so strict-before examples exclude them. Generic numeric unit handling still holds unitless numeric NYHA classes pending reviewed ordinal handling.

## Patient summary

`report patients` writes one row per person to `DATA_DIR/reports/patients.csv`, plus a text summary and JSON companion. It contains:

- Person ID, site and recorded cohort memberships.
- Observation start/end dates and approximate ages where derivable; number of recorded observation periods. Bounds span the periods and do not imply uninterrupted coverage.
- Distinct visit count when a visit table exists.
- Logged ECG/Echo/MRI/other file counts from the preferred linked asset catalogue; these count catalogue records, not verified downloads or unique studies. The catalogue may mix raw and processed representations. Unknown catalogue availability stays blank. Unlinked assets are reported separately in report metadata.
- Baseline date/age, anchor-ledger row count and valid baseline-index count.
- Training-index count when a recognised explicit ledger is present; otherwise blank with an explanation, not zero or an inferred annual count.
- Censor and last-contact dates/ages when recorded.
- Per-endpoint status, event date/age, prevalence-at-baseline, quality flags and ledger row counts. Unknown/not-ascertained status is preserved, never converted to a negative outcome.

RC4 has no recognised training-index ledger. It has 180 associated-file records without person linkage. The patient report records these limitations. Per-patient reports are sensitive data: the menu displays only counts/summary information and saves the rows to the protected DATA_DIR.

## CLI examples

```powershell
smash-hcm-databank-client export --db OMOP.db --format tabular --cohort "Rennes Training" --vars shared-clinical --data-dir ./analysis
smash-hcm-databank-client export --db OMOP.db --format tabular --cohort "Rennes Test" --variables-file ./analysis/RENNES/train/variable_set.json --data-dir ./analysis
smash-hcm-databank-client export --db OMOP.db --format tabular --cohort "Rennes Training" --vars shared-measurements --tabular-mode latest-history --lookback-days 365 --history-features previous-value previous-age-days mean --data-dir ./analysis/history-example
smash-hcm-databank-client export --db OMOP.db --format tabular --cohort "Tampere Training" --vars shared-grouped --data-dir ./analysis/consolidated-example
smash-hcm-databank-client export --db OMOP.db --format events --cohort "Rennes Test" --vars shared-clinical --event-scope baseline --event-lookback-days 365 --domains measurement observation --include-event-metadata --data-dir ./analysis
smash-hcm-databank-client report patients --db OMOP.db --data-dir ./analysis
smash-hcm-databank-client report features --db OMOP.db --data-dir ./analysis
```
