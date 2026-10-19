import csv
import importlib.metadata
import json
import os
import sqlite3
import subprocess
import sys

import pytest

from omop_exporter.cli import main
from omop_exporter.exports import export_events
from omop_exporter.output import bundle


def test_help_and_installed_metadata_require_no_psycopg():
    result = subprocess.run([sys.executable, "-m", "omop_exporter", "--help"], capture_output=True, text=True)
    assert result.returncode == 0 and "validate" in result.stdout
    code = "import omop_exporter.cli,sys; assert 'psycopg' not in sys.modules; assert 'yaml' not in sys.modules"
    assert subprocess.run([sys.executable, "-c", code], capture_output=True).returncode == 0
    metadata = importlib.metadata.metadata("omop-exporter")
    assert all("extra ==" in requirement for requirement in metadata.get_all("Requires-Dist", []))


def test_report_outputs_are_direct_database_results(omop_path, tmp_path, capsys):
    out = tmp_path / "report"
    assert main(["report", "overlap", "--db", str(omop_path), "--out", str(out)]) == 0
    assert json.loads((out / "report.json").read_text())["core_count"] == 1
    with (out / "two_site.csv").open() as handle:
        assert len(list(csv.DictReader(handle))) == 2
    assert main(["report", "overlap", "--db", str(omop_path), "--out", str(out)]) == 2
    assert "Output already exists" in capsys.readouterr().err


def test_relative_config_and_explicit_database_precedence(omop_path, tmp_path):
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"db": omop_path.name}))
    assert main(["cohorts", "list", "--config", str(config)]) == 0
    config.write_text(json.dumps({"db": "does-not-exist.db"}))
    assert main(["cohorts", "list", "--config", str(config), "--db", str(omop_path)]) == 0


def test_validation_nonzero_exit_for_bad_hash(omop_path, capsys):
    assert main(["validate", "--db", str(omop_path), "--sha256", "0" * 64]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "FAIL"


def test_event_stream_stable_cohort_filtered_and_no_management_facts(database, tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    assert export_events(database, a, "florence_train")["rows"] == 5
    export_events(database, b, "1")
    assert (a / "omop_events.csv").read_bytes() == (b / "omop_events.csv").read_bytes()
    with (a / "omop_events.csv").open() as handle:
        rows = list(csv.DictReader(handle))
    assert {row["person_id"] for row in rows} == {"1"}
    assert not any(row["concept_id"] == "2000011000" for row in rows)
    manifest = json.loads((a / "dataset_manifest.json").read_text())
    assert "Full history" in manifest["time_policy"]
    assert manifest["database_sha256"]


def test_unknown_cohort_creates_no_output(database, tmp_path):
    out = tmp_path / "out"
    with pytest.raises(ValueError):
        export_events(database, out, "imaginary")
    assert not out.exists()


def test_failed_bundle_is_not_published(tmp_path):
    out = tmp_path / "out"
    with pytest.raises(ValueError):
        with bundle(out) as stage:
            (stage / "partial.csv").write_text("partial")
            raise ValueError("fixture failure")
    assert not out.exists()
    assert not list(tmp_path.glob(".omop-exporter-*"))


def test_registry_concepts_excluded_even_with_blank_source(omop_path, tmp_path):
    from omop_exporter.database import OmopDatabase
    with sqlite3.connect(omop_path) as connection:
        connection.execute("UPDATE observation SET observation_source_value=NULL")
    with OmopDatabase(omop_path) as database:
        result = export_events(database, tmp_path / "events", "florence_train")
        assert result["rows"] == 5
