# From clinical variables to train.csv and test.csv

The client exports features. A supervised task additionally needs a reviewed target definition, prediction point, horizon and censoring/eligibility policy. Start with [indexing and landmarks](INDEXING_AND_LANDMARKS.md). All paths below are relative examples; keep real data in approved storage outside this checkout.

## 1. Discover cohorts and choose variables

```sh
smash-hcm-databank-client cohorts list --db ./data/OMOP.db
smash-hcm-databank-client report features --db ./data/OMOP.db --data-dir ./analysis/catalogue
```

Use the exact cohort name or ID printed by the first command. The following examples assume `Rennes Training` and `Rennes Test` exist; no alias creates a cohort that is absent from the release. The menu offers a searchable concept catalogue and saves selected lists.

Copy [examples/clinical_variables.json](../examples/clinical_variables.json) to `./my-variables.json`. It selects five clinical measurement concepts plus optional baseline age:

| Concept ID | Measurement |
|---:|---|
| 4152194 | Systolic blood pressure |
| 4154790 | Diastolic blood pressure |
| 4108582 | Left ventricular ejection fraction |
| 3021917 | Interventricular septal thickness |
| 3026578 | LVOT maximum systolic gradient |

```json
{
  "schema_version": 1,
  "name": "My clinical inputs",
  "anchor_features": ["baseline_age_years"],
  "variables": [
    {"table": "measurement", "concept_id": 4152194},
    {"table": "measurement", "concept_id": 4154790},
    {"table": "measurement", "concept_id": 4108582},
    {"table": "measurement", "concept_id": 3021917},
    {"table": "measurement", "concept_id": 3026578}
  ]
}
```

This produces **10 columns**: four metadata fields, five measurements and age. Remove `anchor_features` for nine columns. Age comes from the baseline ledger, not age at diagnosis or an inferred birthday. `concept_name` is optional descriptive text; selection uses the table/concept pair. Requested absent concepts remain blank. Verify units/context against the release and exported dictionary before modelling.

## 2. Export training, then reuse its frozen schema for testing

```sh
smash-hcm-databank-client export --db ./data/OMOP.db --format tabular --cohort "Rennes Training" --variables-file ./my-variables.json --data-dir ./analysis/clinical
smash-hcm-databank-client export --db ./data/OMOP.db --format tabular --cohort "Rennes Test" --variables-file ./analysis/clinical/RENNES/train/variable_set.json --data-dir ./analysis/clinical
```

Inspect `RENNES/train.csv`, `test.csv`, and their `train/`/`test/` companion directories. `variables.csv` explains the source columns/units. `feature_definitions.json` records explicit anchor/family/history features. `dataset_manifest.json` records the source database hash, cohort identity, settings, exclusions and output hashes. `feature_provenance.csv` gives source dates and reasons for missing/withheld cells. Existing outputs are protected from overwrite.

By default each row uses only that patient's eligible **baseline-day** facts. Metadata fields are identifiers, not automatically model predictors. Missing conditions are not confirmed negatives, coded concept IDs are categories rather than continuous measurements, and unknown/conflicting numeric units may withhold values.

## 3. Understand optional additions

| Addition | Precise meaning | Example configuration |
|---|---|---|
| Latest history | Latest eligible observation in an inclusive lookback ending at the same baseline | `--tabular-mode latest-history --lookback-days 730` |
| Previous value | Value on the preceding distinct eligible observation date; not yesterday or a duplicate same-day row | `--history-features previous-value` |
| Previous/latest age in days | Observation recency relative to baseline; **not patient age** | `previous-age-days last-age-days` |
| Count | QC-valid distinct observation dates in the window; no evidence remains missing | `count` |
| Mean/min/max | Numeric summaries over QC-valid dates, preserving unit identity; no category averaging | `mean min max` |
| Log transform | For a reviewed positive-skew feature, apply a declared `log(x)` or `log1p(x)` downstream; domain/zero/negative handling matters | No client flag |
| Log-normal | A distributional assumption about values whose logarithms are normally distributed; not another name for normalization | No client flag |
| Scaling/normalization | E.g. subtract training mean and divide by training standard deviation | Downstream, fitted on training only |
| Imputation/one-hot encoding | Fill missing values or encode categories using an explicitly chosen training schema | Downstream, fitted on training only |

```sh
smash-hcm-databank-client export --db ./data/OMOP.db --format tabular --cohort "Rennes Training" --variables-file ./my-variables.json --tabular-mode latest-history --lookback-days 730 --history-features previous-value previous-age-days count mean min max --data-dir ./analysis/clinical-history
```

The window is **730 days**, not exactly two calendar years and not a two-year outcome horizon. The latest raw feature is retained and optional summaries get separate columns. With five source measurements and six requested extras, there are 35 measurement columns, one baseline-age feature and four metadata fields. No historical summaries are added for the anchor age. To use earlier values while excluding day zero, explicitly add `--availability-policy strict-before`; snapshots cannot use that boundary. Grouped categorical families and history extras require separate exports.

These additions are optional modelling choices, not part of the standard feature-only snapshot. Recording counts/recency can reveal site/care patterns. A window with sparse measurements does not prove continuous observation. Apply the same configuration, frozen variables and units to test exports.

## 4. A simple downstream supervised example

The following is a **separate research script**, not client functionality. It needs pandas and scikit-learn in a modelling environment. It assumes the five-measurement-plus-age exports above and an independently reviewed `labels.csv` with unique `person_id,label` rows and binary labels for **all** exported patients. Unknown/insufficiently followed patients must be handled by the study's eligibility policy before this step; do not fill unknown labels with zero.

```python
from pathlib import Path
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

root = Path("./analysis/clinical/RENNES")
train = pd.read_csv(root / "train.csv", dtype={"person_id": str})
test = pd.read_csv(root / "test.csv", dtype={"person_id": str})
labels = pd.read_csv("./reviewed/labels.csv", dtype={"person_id": str})
assert train.person_id.is_unique and test.person_id.is_unique
assert set(train.person_id).isdisjoint(test.person_id)
assert list(train.columns) == list(test.columns)
assert labels.person_id.is_unique
train = train.merge(labels, on="person_id", how="left", validate="one_to_one")
test = test.merge(labels, on="person_id", how="left", validate="one_to_one")
assert train.label.notna().all() and test.label.notna().all()
assert set(train.label.unique()) == {0, 1}
assert set(test.label.unique()) == {0, 1}  # AUC requires both classes.

# Explicit numeric inputs; never include ID/site/cohort/date or future labels.
features = ["measurement__4152194", "measurement__4154790",
            "measurement__4108582", "measurement__3021917",
            "measurement__3026578", "baseline_age_years"]
X_train = train[features].apply(pd.to_numeric, errors="raise")
X_test = test[features].apply(pd.to_numeric, errors="raise")
model = make_pipeline(
    SimpleImputer(strategy="median", keep_empty_features=True, add_indicator=True),
    StandardScaler(),
    LogisticRegression(max_iter=1000),
)
model.fit(X_train, train.label)
probability = model.predict_proba(X_test)[:, 1]
print("Held-out AUC:", roc_auc_score(test.label, probability))
```

This illustrates consuming the files, not a validated HCM model or a survival analysis. Review empty columns before fitting; an imputer's fallback does not establish clinical normality. Choose transformations/hyperparameters with training-only validation; evaluate the held-out test once. Scikit-learn documents [training-only preprocessing and leakage](https://scikit-learn.org/stable/common_pitfalls.html) and [missing-feature handling](https://scikit-learn.org/stable/modules/generated/sklearn.impute.SimpleImputer.html).

For repeated landmarks, patient IDs are no longer unique input rows: use landmark-specific labels and patient-grouped validation instead. The simple merge above deliberately rejects those data. See [INDEXING_AND_LANDMARKS.md](INDEXING_AND_LANDMARKS.md).
