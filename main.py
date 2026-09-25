"""Small, reproducible OMOP export runner. Patient-level output stays local."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parent
COPY_RE = re.compile(r"COPY\s*\((.*?)\)\s*TO\s*'/out/([^']+)'\s*WITH\s*\(FORMAT CSV, HEADER TRUE\);", re.I | re.S)


def read_config(path):
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("Configuration must be a mapping")
    return config


def connection_args(config):
    db = config["database"]
    args = {key: db[key] for key in ("host", "port", "dbname", "user") if key in db}
    args["password"] = os.environ.get(db.get("password_env", "PGPASSWORD"))
    return args


def run_python(script, *arguments):
    subprocess.run([sys.executable, str(ROOT / script), *map(str, arguments)], check=True)


def restore(config):
    """Restore into an EXISTING EMPTY database via a temporary PostgreSQL client."""
    import psycopg

    dump = Path(config["dump"]).expanduser().resolve(strict=True)
    db = config["database"]
    if not os.environ.get(db.get("password_env", "PGPASSWORD")):
        raise ValueError("Set the database password environment variable before restore")
    with psycopg.connect(**connection_args(config)) as con:
        with con.cursor() as cur:
            cur.execute("SELECT count(*) FROM pg_tables WHERE schemaname NOT IN ('pg_catalog', 'information_schema')")
            if cur.fetchone()[0]:
                raise ValueError("Restore target is not empty; use a newly created database")
    command = ["docker", "run", "--rm", "--mount",
               f"type=bind,source={dump.parent},target=/dump,readonly", "-e", "PGPASSWORD",
               "postgres:14", "pg_restore", "--exit-on-error", "--no-owner", "--no-privileges",
               "-h", db.get("docker_host", "host.docker.internal"), "-p", str(db.get("port", 5432)),
               "-U", db["user"], "-d", db["dbname"], f"/dump/{dump.name}"]
    environment = {**os.environ, "PGPASSWORD": os.environ[db.get("password_env", "PGPASSWORD")]}
    subprocess.run(command, env=environment, check=True)


def export(config):
    import psycopg

    output = Path(config["output_dir"]).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    statements = COPY_RE.findall((ROOT / "export_smash_omop.sql").read_text(encoding="utf-8"))
    if len(statements) != 7:
        raise ValueError("Expected seven versioned COPY statements in export_smash_omop.sql")
    with psycopg.connect(**connection_args(config)) as con:
        with con.cursor() as cur:
            for query, filename in statements:
                destination = output / filename
                if destination.parent != output:
                    raise ValueError("Unsafe output filename")
                with destination.open("wb") as handle, cur.copy(f"COPY ({query}) TO STDOUT WITH (FORMAT CSV, HEADER TRUE)") as copy:
                    for data in copy:
                        handle.write(data)
                print(destination)
    dump = Path(config["dump"]).expanduser()
    metadata = {"dump": str(dump), "dump_sha256": None, "export_sql_sha256":
                hashlib.sha256((ROOT / "export_smash_omop.sql").read_bytes()).hexdigest()}
    if dump.is_file() and config.get("hash_dump", False):
        digest = hashlib.sha256()
        with dump.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        metadata["dump_sha256"] = digest.hexdigest()
    (output / "export_manifest.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")


def prepare(config):
    output = Path(config["output_dir"]).expanduser().resolve()
    if (output / "smash_endpoint_censor.csv").is_file() and (output / "smash_endpoint_event.csv").is_file():
        run_python("build_etl_release_data.py", "--export-dir", output)
    else:
        raw = config["sidecars"]
        run_python("build_smash_experiment_data.py", "--export-dir", output,
                   "--florence-dir", raw["florence_clinical"], "--rennes-csv", raw["rennes_clinical"],
                   "--rennes-endpoints-csv", raw["rennes_endpoints"])
    run_python("build_rolling_landmarks.py", "--data-dir", output)


def tabular(config):
    output = Path(config["output_dir"]).expanduser().resolve()
    options = config.get("tabular", {})
    args = ["--data-dir", output, "--output", output / options.get("filename", "omop_tabular.csv")]
    if options.get("landmarks", True):
        args += ["--landmarks-csv", output / "landmarks.csv"]
    for singular, plural in (("site", "sites"), ("split", "splits"), ("endpoint", "endpoints"),
                             ("domain", "domains"),
                             ("concept-id", "concept_ids"), ("cohort-id", "cohort_ids"),
                             ("input-source", "input_sources")):
        for value in options.get(plural, []):
            args += [f"--{singular}", value]
    if options.get("lookback_years"):
        args += ["--lookback-years", options["lookback_years"]]
    run_python("export_omop_tabular.py", *args)


def assets(config):
    asset = config["assets"]
    output = Path(config["output_dir"]).expanduser().resolve()
    args = ["--patient-manifest", output / "patient_manifest.csv", "--image-occurrences",
            asset["image_occurrences"], "--data-root", asset["data_root"],
            "--output", output / "asset_requests.csv"]
    if asset.get("extra_assets"):
        args += ["--extra-assets", asset["extra_assets"]]
    run_python("build_asset_request_manifest.py", *args)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("restore", "export", "prepare", "tabular", "assets", "all"))
    parser.add_argument("--config", type=Path, default=ROOT / "config.example.yaml")
    args = parser.parse_args()
    config = read_config(args.config)
    if args.command == "restore":
        restore(config)
    elif args.command == "all":
        export(config)
        prepare(config)
        tabular(config)
        if config.get("assets", {}).get("image_occurrences"):
            assets(config)
    else:
        globals()[args.command](config)


if __name__ == "__main__":
    main()
