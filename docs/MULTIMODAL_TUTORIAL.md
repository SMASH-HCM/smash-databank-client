# Combine processed ECG files with clinical train/test data

This tutorial produces one row per existing clinical patient with paths to eligible ECG NPZ files. It does not decode signals, create labels or train a neural network. MRI/NIfTI and curated Echo data can use the same identity/time/split principles, with their own loaders and quality checks.

## 1. Download matching releases and cohorts

In the client menu, configure/login and retrieve the manifest. Download the SQLite OMOP release and choose **Download → Cohort/modality ZIPs**, e.g. RENNES Training and RENNES Test with ECG. Use the exact cohort names/tags actually published; these example ZIPs are not guaranteed to exist yet. Verify the downloads through **Validate** and note their manifest versions/checksums.

Use **Local OMOP** to export matching tabular cohorts with the same frozen variables. The [tabular tutorial](TABULAR_TUTORIAL.md) produces `./analysis/clinical/RENNES/train.csv` and `test.csv`. Keep clinical and signal releases aligned; a matching filename alone is insufficient evidence of the same person-ID namespace or release.

## 2. Extract verified ZIPs

The example helper is supplied in the source archive/portable release under `examples/`; it needs Python 3.9+ but no extra libraries. This is an optional tutorial script, not automatic menu extraction:

```sh
python examples/prepare_multimodal.py extract ./downloads/rennes-training-ecg.zip --out ./assets/rennes-training
python examples/prepare_multimodal.py extract ./downloads/rennes-test-ecg.zip --out ./assets/rennes-test
```

Substitute your actual receipt paths. The helper refuses existing destinations, escaping/absolute paths, symbolic links and duplicate paths. Its default uncompressed limit is 5 GiB/100,000 entries; review larger published packages before explicitly increasing `--max-bytes`. If extraction fails partway, that directory is incomplete; inspect it and use a new destination. Extraction is not a verification of NPZ contents or waveform quality.

## 3. Obtain an authoritative asset index

You need the release's reviewed person-to-asset mapping. The download manifest describes packages; it is **not necessarily** a per-record patient linkage table. OMOP asset catalogues may provide part of the mapping, but record-level paths, dates and prediction availability must be checked against the extracted package. If the release does not supply these, ask the data curator before proceeding. Do not guess IDs from filenames or manufacture dates.

Adapt the reviewed mapping into this explicit CSV contract, `./reviewed/ecg-index.csv`:

```csv
person_id,relative_path,acquisition_date,available_at_baseline
101,rennes-training/ecg/record-a.npz,2019-12-01,true
103,rennes-test/ecg/record-b.npz,2020-01-01,true
```

Rows/IDs above are fictional. `person_id` must be the exported OMOP ID, `relative_path` is relative to `./assets`, and `acquisition_date` must use the **same time coordinate as OMOP baseline** (including any source date shifting). `available_at_baseline=true` means acquisition/context and processing availability were explicitly reviewed for this prediction task. It must not simply mean the file exists today. Unsupported/unknown availability should be `false` until resolved. Date alone cannot establish intraday ordering or whether a derived signal contains follow-up information.

## 4. Build path-linked train/test tables

```sh
python examples/prepare_multimodal.py link --train ./analysis/clinical/RENNES/train.csv --test ./analysis/clinical/RENNES/test.csv --asset-index ./reviewed/ecg-index.csv --asset-root ./assets --lookback-days 730 --out ./analysis/ecg-clinical
```

The helper checks unique, disjoint patient splits and matching clinical columns; joins by exact OMOP person ID; retains reviewed ECGs on/before each row's baseline and within 730 days; checks paths stay within the asset root and point to existing NPZ files; and refuses duplicate/shared eligible file paths. This window is an example input policy, not a clinical recommendation or an outcome horizon.

Output `train.csv`/`test.csv` retain the clinical columns and add `ecg_count` and `ecg_paths`, a JSON list of relative paths. `linkage_summary.json` records the asset root, window and numbers of patients with ECGs. All matching eligible ECGs are listed; there is no implicit "best recording" choice. Patients without an eligible ECG stay present with `[]`; zero here means **no eligible linked record**, not no ECG in their clinical history. Assets outside the two cohorts are not included. Review modality missingness by split/site before deciding to use a paired-only sample.

## 5. Consume clinical features and waveforms together

A modelling dataset loader can read one patient row, decode `ecg_paths`, and load its linked arrays:

```python
import json
from pathlib import Path
import numpy as np

asset_root = Path("./assets").resolve()
# row is a row from the linked train.csv or test.csv.
for relative_path in json.loads(row["ecg_paths"]):
    path = (asset_root / relative_path).resolve(strict=True)
    if asset_root not in path.parents:
        raise ValueError("Asset outside configured root")
    with np.load(path, allow_pickle=False) as recording:
        print(recording.files)  # Inspect the published NPZ schema first.
        # Select documented arrays, lead order, sample rate and valid-signal mask.
```

NPZ keys/shapes are deliberately not guessed: consult the release's signal dictionary. NumPy documents [NPZ loading and allow_pickle](https://numpy.org/doc/stable/reference/generated/numpy.load.html). Check lead ordering, units, sampling rate, duration, alignment and preprocessing/QC; digitized and native waveforms need not be interchangeable.

A common model has a waveform encoder and a clinical-feature branch; their representations are joined before predicting a reviewed endpoint. Alternatively extract ECG embeddings, aggregate them to one patient/index representation, and join that to tabular features. Train encoders, imputers, scalers and recording-selection rules using training data only. Do not refit them on test patients. Multiple ECGs from one patient must stay in that patient's split and should not give that patient accidental extra weight. Repeated-landmark experiments need a separate eligible asset list per landmark; this helper deliberately accepts only one row per patient.

The client currently supplies download verification and OMOP exports; this helper supplies a checked tutorial join. Automatic raw/processed conversion, clinical linkage review, NPZ schema validation and a multimodal training framework are not implemented in the main app.
