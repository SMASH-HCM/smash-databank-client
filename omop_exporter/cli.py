"""Installed command-line interface. SQLite core imports only the standard library."""
import argparse
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

from . import __version__
from .database import OmopDatabase
from .exports import export_events, DOMAINS
from .datasets import export_dataset
from .nextcloud import NextcloudClient, NextcloudConfig
from .menu import run_menu
from .tabular import export_wide, HISTORY_FEATURES
from .workspace import Workspace, default_env_file, default_state_dir
from .output import bundle, write_csv, write_json
from .reports import REPORTS, write_report, write_data_report
from .features import PRESETS, load_variable_set
from .progress import DownloadProgress
from .availability import POLICIES
from .validation import validate_database


def database_options(parser):
    parser.add_argument("--db", type=Path, help="Versioned SQLite OMOP database; or set OMOP_EXPORTER_DB")
    parser.add_argument("--config", type=Path, help="JSON configuration (YAML requires the config extra)")


def database_path(args):
    config = {}
    if args.config:
        with args.config.open(encoding="utf-8") as handle:
            if args.config.suffix.lower() in (".yaml", ".yml"):
                try:
                    import yaml
                except ImportError:
                    raise ValueError('YAML requires installation of ".[config]" in your local environment') from None
                config = yaml.safe_load(handle)
            else:
                config = json.load(handle)
        if not isinstance(config, dict):
            raise ValueError("Configuration must be an object")
    path = args.db or os.environ.get("OMOP_EXPORTER_DB") or config.get("db")
    if not path:
        raise ValueError("Specify --db, OMOP_EXPORTER_DB, or db in a config file")
    path = Path(path).expanduser()
    if args.db is None and not os.environ.get("OMOP_EXPORTER_DB") and args.config and not path.is_absolute():
        path = args.config.resolve().parent / path
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Inspect and export a SMASH OMOP SQLite database directly.")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--plain", action="store_true", help="Use numbered text menus instead of arrow-key navigation")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("doctor", help="Show bundled runtime/menu/vault availability without reading login secrets")
    for name in ("setup", "menu"):
        interactive = commands.add_parser(name, help="SMASH login wizard and interactive data menu" if name == "setup" else "Open the SMASH data menu")
        interactive.add_argument("--state-dir", type=Path, default=default_state_dir())
        interactive.add_argument("--env-file", type=Path, help="Override the local login file")
        interactive.add_argument("--db", type=Path, help="Select an already available local database")
        interactive.add_argument("--plain", action="store_true", default=argparse.SUPPRESS, help="Use numbered text menus")
    validate = commands.add_parser("validate", help="Integrity, schema, expected checksum and optional local asset checks")
    database_options(validate)
    validate.add_argument("--sha256", help="Trusted expected database SHA-256")
    validate.add_argument("--require-capability", action="append", default=[], choices=("persons", "concept_names", "cohorts", "cohort_catalog", "baseline_anchors", "endpoint_labels", "asset_catalog", "image_occurrences"))
    validate.add_argument("--asset-root", type=Path, help="Validate all files declared by the embedded smash_asset catalog")
    validate.add_argument("--out", type=Path, help="New directory for validation.json")
    report = commands.add_parser("report", help="Generate aggregate reports from database tables")
    report.add_argument("kind", choices=tuple(REPORTS))
    database_options(report)
    report_destination = report.add_mutually_exclusive_group(required=True)
    report_destination.add_argument("--out", type=Path, help="New explicit report bundle directory")
    report_destination.add_argument("--data-dir", type=Path, help="Standard layout: DATA_DIR/reports/kind.txt and tables")
    cohorts = commands.add_parser("cohorts", help="Discover canonical cohort names/IDs")
    cohorts.add_argument("action", choices=("list",))
    database_options(cohorts)
    export = commands.add_parser("export", help="Export full-history events or a baseline feature-only table")
    database_options(export)
    export.add_argument("--format", choices=("events", "tabular"), default="events")
    selection = export.add_mutually_exclusive_group()
    selection.add_argument("--vars", choices=tuple(PRESETS), help="Freeze an exact-variable group from the supplied database")
    selection.add_argument("--variables-file", type=Path, help="Reuse exact table/concept pairs from saved variable-set JSON")
    export.add_argument("--cohort", help="Canonical database cohort name or ID")
    export.add_argument("--availability-policy", choices=POLICIES, help="Tabular prediction-time mask (default post-assessment); strict-before retains the historical comparison. Not valid for full-history events.")
    export.add_argument("--tabular-mode", choices=("snapshot", "latest-history"), help="Default snapshot: exact baseline day, no carry-forward. History requires explicit configuration.")
    export.add_argument("--lookback-days", type=int, help="Explicit lookback for latest-history only; no snapshot window")
    export.add_argument("--history-features", nargs="+", choices=HISTORY_FEATURES, default=[], help="Explicit extra history columns; requires latest-history and lookback")
    export.add_argument("--event-scope", choices=("full-history", "baseline"), help="Events: full history (default) or prediction-boundary mask")
    export.add_argument("--domains", nargs="+", choices=tuple(DOMAINS.values()), help="Event domains to include")
    export.add_argument("--start-date", help="Events: inclusive calendar start YYYY-MM-DD")
    export.add_argument("--end-date", help="Events: inclusive calendar end YYYY-MM-DD")
    export.add_argument("--event-lookback-days", type=int, help="Events in baseline scope: optional prior window")
    export.add_argument("--event-availability-policy", choices=POLICIES, help="Baseline-scoped event availability mask")
    export.add_argument("--include-event-metadata", action="store_true", help="Include fact/source/site and baseline-relative event timing")
    destination = export.add_mutually_exclusive_group(required=True)
    destination.add_argument("--out", type=Path, help="New explicit bundle directory (data.csv or omop_events.csv)")
    destination.add_argument("--data-dir", type=Path, help="Standard DATA_DIR/cohort/train.csv,test.csv or event_stream/cohort layout")
    cloud = commands.add_parser("nextcloud", help="Read-only Nextcloud access using setup credentials or a local .env")
    cloud_actions = cloud.add_subparsers(dest="cloud_action", required=True)
    for action in ("check", "list", "download"):
        sub = cloud_actions.add_parser(action)
        sub.add_argument("--env-file", type=Path, help="Explicit .env; otherwise prefer a configured setup profile, then .env")
        sub.add_argument("--state-dir", type=Path, default=default_state_dir(), help="Local setup profile directory")
        sub.add_argument("--remote-root", help="Mounted group folder, e.g. databank; overrides NEXTCLOUD_REMOTE_ROOT")
        if action == "list":
            sub.add_argument("--path", default="", help="Folder relative to remote root; non-recursive listing")
        if action == "download":
            sub.add_argument("path", help="One file relative to remote root, e.g. README.md")
            sub.add_argument("--out", type=Path, required=True, help="New directory for the file and a credential-free receipt")
            sub.add_argument("--sha256", help="Optional expected checksum from a trusted manifest")
            sub.add_argument("--max-bytes", type=int, default=16 * 1024 * 1024, help="Safety size limit; default 16 MiB")
    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            import importlib
            from .credentials import native_vault
            from .nextcloud import NextcloudError
            available = {}
            for name in ("questionary", "yaml"):
                try:
                    importlib.import_module(name)
                    available[name] = True
                except ImportError:
                    available[name] = False
            try:
                backend = native_vault()
                vault = type(backend).__module__ + "." + type(backend).__name__
            except NextcloudError:
                vault = "unavailable; session-only and explicit .env storage remain available"
            result = {"version": __version__, "frozen": bool(getattr(sys, "frozen", False)), "python": sys.version.split()[0],
                      "libraries": available, "native_vault": vault}
            print(json.dumps(result, indent=2))
            return 0
        if args.command in (None, "setup", "menu"):
            state_dir = getattr(args, "state_dir", default_state_dir())
            workspace = Workspace(state_dir, getattr(args, "env_file", None) or default_env_file(state_dir), getattr(args, "db", None))
            if getattr(args, "db", None) is not None:
                workspace.register_database(args.db)
            return run_menu(workspace, initial_setup=args.command == "setup", plain=args.plain)
        if args.command == "nextcloud":
            configured = Workspace(args.state_dir, default_env_file(args.state_dir)) if args.env_file is None else None
            if configured is not None and configured.state["profile"].get("credential_storage"):
                from .settings import SMASH_REMOTE_ROOT
                if args.remote_root not in (None, SMASH_REMOTE_ROOT):
                    raise ValueError("The setup profile uses the fixed SMASH databank folder; use an explicit --env-file for another root")
                client = configured.client()
            else:
                client = NextcloudClient(NextcloudConfig.from_env(args.env_file or default_env_file(args.state_dir), args.remote_root))
            if args.cloud_action == "check":
                result = client.check()
            elif args.cloud_action == "list":
                result = {"entries": client.list(args.path)}
            else:
                with DownloadProgress(args.path) as progress:
                    result = client.download(args.path, args.out, args.sha256, args.max_bytes, progress=progress)
            print(json.dumps(result, indent=2, allow_nan=False))
            return 0
        if args.command == "validate" and args.sha256 and not re.fullmatch(r"[0-9a-fA-F]{64}", args.sha256):
            raise ValueError("--sha256 must contain 64 hexadecimal characters")
        with OmopDatabase(database_path(args)) as database:
            if args.command == "validate":
                result = validate_database(database, args.sha256, args.require_capability, args.asset_root)
                if args.out:
                    with bundle(args.out) as stage:
                        write_json(stage / "validation.json", result)
            elif args.command == "cohorts":
                result = {"cohorts": database.cohorts(), "supported": database.capabilities()["cohorts"]}
            elif args.command == "export":
                variables = load_variable_set(args.variables_file) if args.variables_file else args.vars
                if args.format == "events" and (any(value is not None for value in (args.availability_policy, args.tabular_mode, args.lookback_days)) or args.history_features):
                    raise ValueError("Event streams are full history; tabular availability/history options apply only to tabular exports")
                if args.format == "tabular":
                    if any(value is not None for value in (args.event_scope, args.domains, args.start_date, args.end_date, args.event_lookback_days, args.event_availability_policy)) or args.include_event_metadata:
                        raise ValueError("Event configuration options apply only to event exports")
                    if args.cohort is None:
                        raise ValueError("Tabular export needs an explicit --cohort from cohorts list")
                    options = dict(lookback_days=args.lookback_days, availability_policy=args.availability_policy or "post-assessment", tabular_mode=args.tabular_mode or "snapshot", history_features=args.history_features)
                    result = export_dataset(database, args.data_dir, [args.cohort], variables or "core", "tabular", **options) if args.data_dir else export_wide(database, args.out, args.cohort, variables or "core", **options)
                else:
                    if args.event_availability_policy and args.event_scope != "baseline":
                        raise ValueError("An event availability policy requires --event-scope baseline")
                    options = dict(time_scope=args.event_scope or "full-history", domains=args.domains, date_start=args.start_date, date_end=args.end_date,
                                   event_lookback_days=args.event_lookback_days, event_availability_policy=args.event_availability_policy or "post-assessment", include_metadata=args.include_event_metadata)
                    result = export_dataset(database, args.data_dir, [args.cohort], variables or "all", "events", **options) if args.data_dir else export_events(database, args.out, args.cohort, variables, **options)
            else:
                report_data = write_data_report(database, args.kind, args.data_dir) if args.data_dir else write_report(database, args.kind, args.out)
                result = {"report": args.kind, "output": str(args.data_dir / "reports" if args.data_dir else args.out), "patients_by_site": report_data["patients_by_site"]}
                if args.kind == "overlap":
                    result.update({"core_count": report_data["core_count"], "two_site_count": report_data["two_site_count"]})
        print(json.dumps(result, indent=2, allow_nan=False))
        return 2 if result.get("status") == "FAIL" else 0
    except (OSError, ValueError, KeyError, sqlite3.Error) as exc:
        print("Error: " + str(exc), file=sys.stderr)
        return 2
