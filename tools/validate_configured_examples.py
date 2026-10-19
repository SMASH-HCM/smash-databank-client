"""Generate protected RC4 examples in the standard layout; no source writes."""
import argparse
import csv
from datetime import date
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from omop_exporter import __version__
from omop_exporter.availability import held_reason
from omop_exporter.database import OmopDatabase, quote, sha256
from omop_exporter.datasets import export_dataset
from omop_exporter.features import resolve_variables
from omop_exporter.output import write_json
from omop_exporter.reports import write_data_report


def read_rows(path):
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def main(db_path, data_dir):
    root = Path(data_dir).expanduser().resolve()
    if root.exists():
        raise FileExistsError("Choose a new protected DATA_DIR; existing examples are never replaced")
    before = sha256(db_path)
    examples, blocked = [], []
    root.mkdir(parents=True)
    with OmopDatabase(db_path) as database:
        cohorts = ["Rennes Training", "Rennes Test", "Tampere Training", "Tampere Pilot"]
        examples.extend(export_dataset(database, root, cohorts, "core")["cohorts"])
        examples.extend(export_dataset(database, root, cohorts, "core", "events")["cohorts"])
        for cohort in ("FLORENCE Training", "FLORENCE Pilot"):
            try:
                export_dataset(database, root, [cohort], "core")
                raise AssertionError("Expected incomplete RC4 FLORENCE anchors to block export")
            except ValueError as exc:
                if "baseline" not in str(exc):
                    raise
                blocked.append({"cohort": cohort, "reason": str(exc)})
        examples.extend(export_dataset(database, root / "examples/minimal-measurements", ["Rennes Test"], "minimal-measurements")["cohorts"])
        examples.extend(export_dataset(database, root / "examples/consolidated-core", ["Tampere Training"], "core-consolidated")["cohorts"])
        examples.extend(export_dataset(database, root / "examples/history-365d", ["Tampere Training"], "core-measurements",
                                       tabular_mode="latest-history", lookback_days=365,
                                       history_features=["previous-value", "previous-age-days", "count", "mean"])["cohorts"])
        examples.extend(export_dataset(database, root / "examples/baseline-events", ["Rennes Test"], "core", "events",
                                       time_scope="baseline", event_lookback_days=365,
                                       domains=["measurement", "observation"], include_metadata=True)["cohorts"])
        for kind in ("inventory", "cohorts", "endpoints", "overlap", "distributions", "features", "patients"):
            report = write_data_report(database, kind, root)
            if kind == "patients":
                patient_facts = {key: report[key] for key in ("patient_count", "file_catalogue", "unlinked_file_catalogue_rows")}
                assert len(report["patients"]) == database.count("person")
                assert {row["person_id"] for row in report["patients"]} == set(database.person_sites())
                assert all(row["training_index_count"] is None for row in report["patients"])
        anchors = {pid: date.fromisoformat(day) for pid, day in database.connection.execute("SELECT person_id,baseline_date FROM " + quote(database.table("smash_endpoint_censor"))) if day}
        names = database.concept_names()
        for example in examples:
            directory, csv_path = Path(example["directory"]), Path(example["data_file"])
            manifest = json.loads((directory / "dataset_manifest.json").read_text())
            rows = read_rows(csv_path)
            assert len(rows) == example["rows"]
            members = {pid for pid, in database.connection.execute("SELECT DISTINCT subject_id FROM " + quote(database.table("cohort")) + " WHERE cohort_definition_id=?", (manifest["cohort_id"],))}
            assert {int(row["person_id"]) for row in rows}.issubset(members)
            if example["format"] == "tabular":
                assert len(rows) == len(members)
                assert len(rows[0]) == manifest["feature_count"] + 4
                assert list(rows[0]) == manifest["columns"]
                assert all(row["snapshot_date"] == anchors[int(row["person_id"])].isoformat() for row in rows)
                provenance = read_rows(directory / "feature_provenance.csv")
                if manifest["tabular_mode"] == "snapshot":
                    assert all(not row["event_date"] or row["event_date"] == anchors[int(row["landmark_id"].split(":")[0])].isoformat() for row in provenance)
                else:
                    history = read_rows(directory / "history_provenance.csv")
                    for row in history:
                        elapsed = (anchors[int(row["landmark_id"].split(":")[0])] - date.fromisoformat(row["event_date"])).days
                        assert 0 <= elapsed <= manifest["lookback_days"]
                example["feature_columns"] = manifest["feature_count"]
                example["populated_feature_cells"] = sum(value != "" for row in rows for key, value in row.items() if key not in manifest["metadata_columns"])
            elif manifest["time_scope"] == "baseline":
                for row in rows:
                    elapsed = (anchors[int(row["person_id"])] - date.fromisoformat(row["event_date"])).days
                    assert 0 <= elapsed <= 365
                    assert not held_reason(row["fact_table"], int(row["concept_id"]), names.get(int(row["concept_id"]), ""), elapsed == 0, "post-assessment")
            for relative, expected in manifest["output_sha256"].items():
                assert sha256(directory / relative) == expected
            example["acceptance"] = "PASS: source membership/anchors, schema, boundaries and hashes"
    after = sha256(db_path)
    assert before == after
    result = {"version": __version__, "source_sha256": before, "source_unchanged": True,
              "patient_report": patient_facts, "examples": examples, "blocked": blocked}
    write_json(root / "acceptance.json", result)
    lines = ["# Configured RC4 exports — 18 October 2026", "", "Standard DATA_DIR layout generated with omop-exporter " + __version__ + ". Patient-level data: keep in protected storage.", "",
             "Default CORE snapshots: RENNES/train.csv, RENNES/test.csv, TAMPERE/train.csv, TAMPERE/test.csv. Each has 37 features plus four metadata columns. PILOT uses test.csv with original cohort identity retained.", "",
             "Reports: reports/patients.csv (2,984 people), patients.txt, cohorts, endpoints, inventory, overlap, distributions, and complete preset feature lists. JSON/CSV companions remain in reports/<kind>/.", "",
             "Patient training-index counts are unknown: RC4 has no recognised explicit ledger. File counts are logged catalogue records, not physical availability checks. There are 180 unlinked catalogue records.", "",
             "Event streams: event_stream/<cohort>/omop_events.csv are full history and require prediction-time handling. examples/baseline-events/ is the explicit masked 365-day comparison with source/timing metadata.", "",
             "Alternative configurations have separate DATA_DIRs under examples/: minimal-measurements (8 fields), consolidated-core (36 output features from 42 source concepts), history-365d (26 CORE measurements with four explicit derived columns each). Family mapping is a candidate; it does not bypass the same-day availability mask or prove clinical equivalence.", "",
             "FLORENCE Training/Pilot snapshots remain blocked by missing baselines. No people were dropped and no dates inferred. Outcome labels, risk sets and annual prediction indices are not generated. Full details: acceptance.json.", "",
             "Source database SHA-256 before/after: " + before, ""]
    (root / "README.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"examples": len(examples), "blocked": len(blocked), "patients": patient_facts, "source_unchanged": True, "output": str(root)}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--data-dir", required=True, type=Path)
    args = parser.parse_args()
    main(args.db, args.data_dir)
