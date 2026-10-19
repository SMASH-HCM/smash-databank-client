"""Acceptance for the portable app against the protected RC4 examples."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import zipfile


def main(repo, root, db):
    from smash_hcm_databank_client import __version__
    folder = repo / ("dist/binary/smash-hcm-databank-client-" + __version__ + "-windows-amd64")
    exe = folder / "smash-hcm-databank-client.exe"
    archive = Path(str(folder) + ".zip")
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == archive.with_suffix(".zip.sha256").read_text().split()[0]
    with zipfile.ZipFile(archive) as bundle:
        prefix = folder.name + "/"
        for line in bundle.read(prefix + "SHA256SUMS.txt").decode().splitlines():
            checksum, name = line.split("  ", 1)
            assert hashlib.sha256(bundle.read(prefix + name)).hexdigest() == checksum
        assert not any(Path(name).name == ".env" or Path(name).suffix in (".db", ".npz", ".nii", ".dcm") for name in bundle.namelist())
        assert prefix + "docs/DATASET_EXPORTS.md" in bundle.namelist()
    session = root / "binary-acceptance"
    session.mkdir()
    env = dict(os.environ, NO_COLOR="1")
    for name in ("PYTHONPATH", "OMOP_EXPORTER_DB", "NEXTCLOUD_URL", "NEXTCLOUD_USERNAME", "NEXTCLOUD_PASSWORD"):
        env.pop(name, None)
    def run(args, input=None):
        result = subprocess.run([str(exe)] + args, cwd=session, env=env, input=input, capture_output=True, text=True, timeout=180)
        assert result.returncode == 0, result.stderr
        return result.stdout
    assert run(["--version"]).strip() == "0.10.0"
    common = ["export", "--db", str(db)]
    run(common + ["--format", "tabular", "--cohort", "Rennes Test", "--vars", "core", "--data-dir", str(session / "snapshot")])
    assert (session / "snapshot/RENNES/test.csv").read_bytes() == (root / "RENNES/test.csv").read_bytes()
    run(common + ["--format", "tabular", "--cohort", "Tampere Training", "--vars", "core-measurements", "--tabular-mode", "latest-history", "--lookback-days", "365", "--history-features", "previous-value", "previous-age-days", "count", "mean", "--data-dir", str(session / "history")])
    assert (session / "history/TAMPERE/train.csv").read_bytes() == (root / "examples/history-365d/TAMPERE/train.csv").read_bytes()
    run(common + ["--format", "tabular", "--cohort", "Tampere Training", "--vars", "core-consolidated", "--data-dir", str(session / "family")])
    assert (session / "family/TAMPERE/train.csv").read_bytes() == (root / "examples/consolidated-core/TAMPERE/train.csv").read_bytes()
    run(common + ["--format", "events", "--cohort", "Rennes Test", "--vars", "core", "--event-scope", "baseline", "--event-lookback-days", "365", "--domains", "measurement", "observation", "--include-event-metadata", "--data-dir", str(session / "events")])
    assert (session / "events/event_stream/RENNES-TEST/omop_events.csv").read_bytes() == (root / "examples/baseline-events/event_stream/RENNES-TEST/omop_events.csv").read_bytes()
    run(["report", "patients", "--db", str(db), "--data-dir", str(session / "patients")])
    assert (session / "patients/reports/patients.csv").read_bytes() == (root / "reports/patients.csv").read_bytes()
    menu_root = session / "menu-data"
    supplied = "\n".join(["3", "1", "5", "8", "1", "1", str(menu_root), "y", "6", ""])
    menu = run(["menu", "--state-dir", str(session / "state"), "--env-file", str(session / "absent.env"), "--db", str(db), "--plain"], supplied)
    assert "Export complete: 40 rows" in menu
    assert (menu_root / "RENNES/test.csv").read_bytes() == (root / "examples/minimal-measurements/RENNES/test.csv").read_bytes()
    saved = json.loads((session / "state/state.json").read_text())
    assert Path(saved["download_root"]) == menu_root
    result = {"version": "0.10.0", "mode": "onedir", "archive_hashes_and_private_file_exclusion": "PASS",
              "snapshot": "matches audited API output", "explicit_history": "matches audited API output", "family": "matches audited API output",
              "baseline_events_with_metadata": "matches audited API output", "patient_report": "matches audited API output",
              "plain_menu_configured_export_and_saved_DATA_DIR": "PASS"}
    (session / "acceptance.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    application = root / "application"
    application.mkdir()
    for source in (archive, archive.with_suffix(".zip.sha256")):
        shutil.copy2(source, application / source.name)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--db", required=True, type=Path)
    args = parser.parse_args()
    main(Path(__file__).resolve().parents[1], args.data_dir, args.db)
