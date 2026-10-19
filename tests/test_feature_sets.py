import csv
import importlib.metadata
import json
from pathlib import Path
import sqlite3

import pytest

from smash_hcm_databank_client.database import OmopDatabase
from smash_hcm_databank_client.datasets import export_dataset
from smash_hcm_databank_client.features import (PRESETS, PRESET_ALIASES, ESC_RISK_VARIABLES,
                                    freeze_selection, load_variable_set, resolve_variables, save_variable_set)
from smash_hcm_databank_client.tabular import export_wide


def test_old_names_resolve_identically_to_friendly_names(database):
    for old, new in PRESET_ALIASES.items():
        if old == "ecg-derived":  # This minimal fixture has no ECG-labelled concept.
            for name in (old, new):
                with pytest.raises(ValueError, match="empty"):
                    resolve_variables(database, name)
            continue
        assert resolve_variables(database, old) == resolve_variables(database, new)
        assert freeze_selection(database, old) == freeze_selection(database, new)
    assert not set(PRESETS) & set(PRESET_ALIASES)


def test_esc_exports_age_and_source_concepts_without_score_or_inferred_negatives(omop_path, tmp_path):
    with sqlite3.connect(omop_path) as connection:
        connection.executescript("""
          INSERT INTO measurement VALUES (100,1,4353969,'2021-01-01',20,NULL,8582);
          INSERT INTO condition_occurrence VALUES (100,1,135360,'2021-01-01');
        """)
    with OmopDatabase(omop_path) as db:
        export_dataset(db, tmp_path / "out", [1, 3], "esc-risk")
        saved = load_variable_set(tmp_path / "out/FLORENCE/train/variable_set.json")
        assert set(saved["keys"]) == set(ESC_RISK_VARIABLES)
        assert saved["anchor_features"] == ["baseline_age_years"]
        export_wide(db, tmp_path / "reuse", 1, saved)
    with (tmp_path / "out/FLORENCE/train.csv").open() as file:
        row = next(csv.DictReader(file))
    assert len(row) == 12  # Four metadata + seven source concepts + baseline age.
    assert row["baseline_age_years"] == "50.0" and row["measurement__4353969"] == "20.0"
    assert row["condition_occurrence__135360"] == ""  # Conservative same-day role mask.
    assert row["condition_occurrence__40480274"] == ""  # No evidence is not a negative.
    assert "measurement__2000001100" not in row  # Previously calculated risk is not an input.
    assert (tmp_path / "reuse/data.csv").read_bytes() == (tmp_path / "out/FLORENCE/train.csv").read_bytes()
    definitions = json.loads((tmp_path / "reuse/feature_definitions.json").read_text())
    assert definitions["anchor_features"] == ["baseline_age_years"]


def test_custom_documented_variable_file_exports_portably(database, tmp_path):
    path = Path(__file__).resolve().parents[1] / "examples/clinical_variables.json"
    selected = load_variable_set(path)
    export_wide(database, tmp_path / "out", 1, selected)
    with (tmp_path / "out/data.csv").open() as file:
        row = next(csv.DictReader(file))
    assert len(row) == 10 and row["baseline_age_years"] == "50.0"
    assert all(row[f"measurement__{cid}"] == "" for _, cid in selected["keys"])


def test_unknown_derived_features_rejected(database, tmp_path):
    with pytest.raises(ValueError, match="Unsupported anchor features"):
        save_variable_set(tmp_path / "bad.json", database, {"keys": [("measurement", 10)], "anchor_features": ["risk_score"]})


def test_public_distribution_has_one_client_command():
    distribution = importlib.metadata.distribution("smash-hcm-databank-client")
    assert [e.name for e in distribution.entry_points if e.group == "console_scripts"] == ["smash-hcm-databank-client"]
