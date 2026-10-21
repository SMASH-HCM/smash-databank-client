"""Download and byte-validation CLI; OMOP analysis lives in digitaltwin_moe."""
import argparse
import json
from pathlib import Path
import os
import sys
from . import __version__
from .nextcloud import NextcloudClient, NextcloudConfig
from .workspace import Workspace, default_env_file, default_state_dir
from .menu import run_menu
from .output import bundle, write_json
from .progress import DownloadProgress
from .database_artifacts import validate_dump


def main(argv=None):
    parser = argparse.ArgumentParser(prog="smash-hcm-databank-client", description="Download and verify published SMASH-HCM datasets, reports, curated data and PostgreSQL dumps.", epilog="OMOP analysis and dataset publication: digitaltwin_moe, python -m smash_omop --help")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--plain", action="store_true", help="Use numbered menus")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("doctor", help="Show runtime/menu/vault availability without reading secrets")
    for name in ("setup", "menu"):
        interactive = commands.add_parser(name, help="Login setup and download menu")
        interactive.add_argument("--state-dir", type=Path, default=default_state_dir())
        interactive.add_argument("--env-file", type=Path)
        interactive.add_argument("--db", type=Path, help="Select a local PostgreSQL dump for integrity validation")
        interactive.add_argument("--plain", action="store_true", default=argparse.SUPPRESS)
    validate = commands.add_parser("validate", help="Verify PostgreSQL dump bytes; no table queries or restoration")
    validate.add_argument("--db", type=Path, help="Local PostgreSQL dump; otherwise SMASH_DATABANK_DB")
    validate.add_argument("--sha256", help="Trusted expected SHA-256")
    validate.add_argument("--out", type=Path, help="New directory for validation.json")
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
            for name in ("questionary",):
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
                cloud_config = NextcloudConfig.from_env(args.env_file or default_env_file(args.state_dir), args.remote_root)
                if args.remote_root is None and not cloud_config.remote_root:
                    from dataclasses import replace
                    from .settings import SMASH_REMOTE_ROOT
                    cloud_config = replace(cloud_config, remote_root=SMASH_REMOTE_ROOT)
                client = NextcloudClient(cloud_config)
            if args.cloud_action == "check":
                result = client.check()
            elif args.cloud_action == "list":
                result = {"entries": client.list(args.path)}
            else:
                with DownloadProgress(args.path) as progress:
                    result = client.download(args.path, args.out, args.sha256, args.max_bytes, progress=progress)
            print(json.dumps(result, indent=2, allow_nan=False))
            return 0
        path = args.db or os.environ.get("SMASH_DATABANK_DB") or os.environ.get("OMOP_EXPORTER_DB")
        if not path:
            raise ValueError("Specify --db or SMASH_DATABANK_DB")
        result = validate_dump(path, args.sha256)
        if args.out:
            with bundle(args.out) as stage:
                write_json(stage / "validation.json", result)
        print(json.dumps(result, indent=2, allow_nan=False))
        return 2 if result["status"] == "FAIL" else 0
    except (OSError, ValueError, KeyError) as exc:
        from .console import write_message
        write_message("Error: " + str(exc), level="failure", stream=sys.stderr)
        return 2
