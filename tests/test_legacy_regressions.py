import csv
import subprocess
import sys


def write_csv(path, fields, rows):
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_legacy_sparse_unknown_unit_regression(tmp_path):
    write_csv(tmp_path / "patient_manifest.csv", ["person_id", "site", "split", "baseline_age_years"],
              [{"person_id": "1", "site": "FLORENCE", "split": "FLORENCE-TRAIN", "baseline_age_years": "50"}])
    fields = ["person_id", "domain", "concept_id", "patient_age_at_event_years", "value_as_number", "value_as_concept_id", "unit_concept_id"]
    rows = [{"person_id": "1", "domain": "measurement", "concept_id": "10", "patient_age_at_event_years": age, "value_as_number": value, "value_as_concept_id": "", "unit_concept_id": unit}
            for age, value, unit in [("49", "10", "8582"), ("49.5", "100", ""), ("50", "999", "8582"), ("50.1", "888", "8582")]]
    write_csv(tmp_path / "age_omop_events.csv", fields, rows)
    out = tmp_path / "sparse.csv"
    subprocess.run([sys.executable, "-m", "export_omop_tabular", "--data-dir", str(tmp_path), "--output", str(out)], check=True, capture_output=True)
    with out.open() as handle:
        result = list(csv.DictReader(handle))[0]
    assert result["event_count"] == "2"
    assert result["unit_conflict"] == "1"
    assert result["window_numeric_mean"] == ""
    assert result["latest_numeric_mean"] == ""


def test_legacy_help_does_not_require_yaml_or_postgres():
    result = subprocess.run([sys.executable, "-m", "main", "--help"], capture_output=True, text=True)
    assert result.returncode == 0


def test_packaged_legacy_sql_has_seven_contracts():
    import main
    assert len(main.COPY_RE.findall(main.SQL_PATH.read_text(encoding="utf-8"))) == 7


def test_annual_training_and_fixed_holdout_landmarks(tmp_path):
    import json
    fields = ["person_id", "site", "split", "index_date", "censor_date", "baseline_age_years"]
    people = [{"person_id": pid, "site": "FLORENCE", "split": split, "index_date": "2020-02-29", "censor_date": "2024-03-01", "baseline_age_years": "50"}
              for pid, split in [("1", "FLORENCE-TRAIN"), ("2", "FLORENCE-TEST")]]
    write_csv(tmp_path / "patient_manifest.csv", fields, people)
    label_fields = ["person_id", "endpoint", "horizon_years", "event_date", "label_reason", "cohort_status_conflict", "prevalent_at_baseline"]
    write_csv(tmp_path / "horizon_labels.csv", label_fields,
              [{"person_id": pid, "endpoint": "overall", "horizon_years": "1", "event_date": "2022-03-01", "label_reason": "observed_event", "cohort_status_conflict": "0", "prevalent_at_baseline": "0"} for pid in ("1", "2")])
    subprocess.run([sys.executable, "-m", "build_rolling_landmarks", "--data-dir", str(tmp_path)], capture_output=True, check=True)
    with (tmp_path / "landmarks.csv").open() as handle:
        rows = list(csv.DictReader(handle))
    train = [row for row in rows if row["person_id"] == "1"]
    test = [row for row in rows if row["person_id"] == "2"]
    assert len(train) == 3 and len(test) == 1
    assert train[1]["landmark_date"] == "2021-02-28"
    assert all(row["landmark_date"] < row["event_date"] for row in rows)
    assert abs(sum(float(row["sample_weight"]) for row in train) - 1) < 1e-7
    assert test[0]["landmark_policy"] == "fixed_baseline"
    assert json.loads((tmp_path / "landmark_audit.json").read_text())["policy"]["max_training_years"] == 5
