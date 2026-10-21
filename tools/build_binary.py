"""Build a portable application and a checksummed release ZIP on the target OS."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def build(output):
    source = (ROOT / "src/smash_hcm_databank_client/__init__.py").read_text(encoding="utf-8")
    version = re.search(r'__version__ = "(\d+\.\d+\.\d+(?:rc[1-9]\d*)?)"', source).group(1)
    output = Path(output).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    platform_name = {"Darwin": "macos"}.get(platform.system(), platform.system().lower())
    name = "smash-hcm-databank-client-" + version + "-" + platform_name + "-" + platform.machine().lower()
    release = output / name
    archive = output / (name + ".zip")
    if release.exists() or archive.exists():
        raise ValueError("Release destination already exists; select a new --out directory")
    work = ROOT / "build" / ("binary-" + uuid.uuid4().hex)
    work.mkdir(parents=True)
    env = dict(os.environ, PYINSTALLER_CONFIG_DIR=str(ROOT / "build/pyinstaller-cache"))
    command = [sys.executable, "-m", "PyInstaller", "--console", "--noupx", "--name", "smash-hcm-databank-client",
               "--onedir", "--distpath", str(work / "dist"), "--workpath", str(work / "work"),
               "--specpath", str(work), "--paths", str(ROOT / "src"), "--hidden-import", "keyring",
               "--collect-data", "smash_hcm_databank_client", "--exclude-module", "psycopg", "--exclude-module", "pandas", "--exclude-module", "sqlite3", "--exclude-module", "_sqlite3",
               "--exclude-module", "numpy", "--exclude-module", "tkinter", str(ROOT / "tools/binary_entry.py")]
    subprocess.run(command, cwd=ROOT, env=env, check=True)
    executable = "smash-hcm-databank-client.exe" if sys.platform == "win32" else "smash-hcm-databank-client"
    shutil.copytree(work / "dist/smash-hcm-databank-client", release)
    # Explicit public allowlist: never collect the checkout, .env or local state.
    for filename in ("README.md", "manifest.example.json"):
        shutil.copy2(ROOT / filename, release / filename)
    dump_guide = release / "docs/POSTGRES_DUMPS.md"
    dump_guide.parent.mkdir(exist_ok=True)
    shutil.copy2(ROOT / "docs/POSTGRES_DUMPS.md", dump_guide)
    for filename in ("README.md", "MENU.md", "NEXTCLOUD.md", "BINARY_RELEASES.md", "UPDATES.md", "SETUP.md", "GITHUB_RELEASE.md", "TESTING.md", "ARCHITECTURE.md", "RELEASE_0.13.0.md"):
        destination = release / "docs" / filename
        destination.parent.mkdir(exist_ok=True)
        shutil.copy2(ROOT / "docs" / filename, destination)
    notices = []
    distributions = sorted(importlib.metadata.distributions(), key=lambda item: item.metadata.get("Name", "").lower())
    # License texts for dependencies actually present in the frozen app, not dev tools.
    included = {"pyinstaller", "questionary", "prompt-toolkit", "pygments", "wcwidth", "keyring", "pywin32-ctypes", "platformdirs", "importlib-metadata", "zipp", "more-itertools", "jaraco.classes", "jaraco.context", "jaraco.functools", "backports.tarfile", "jeepney", "secretstorage", "cryptography", "cffi", "pycparser"}
    for distribution in distributions:
        package = distribution.metadata.get("Name", "")
        if package.lower().replace("_", "-") not in included:
            continue
        notices.append(package + " " + distribution.version + "\n" + (distribution.metadata.get("License-Expression") or distribution.metadata.get("License") or "See license files") + "\n")
        for item in distribution.files or ():
            if ".dist-info" in str(item) and any(token in item.name.lower() for token in ("license", "copying", "notice")):
                path = distribution.locate_file(item)
                if path.is_file():
                    notices.append(str(item) + "\n" + path.read_text(encoding="utf-8", errors="replace") + "\n")
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.is_file():
        notices.append("Python runtime license\n" + python_license.read_text(encoding="utf-8", errors="replace"))
    (release / "THIRD_PARTY_NOTICES.txt").write_text("\n".join(notices), encoding="utf-8")
    details = {"version": version, "source_commit": os.environ.get("GITHUB_SHA"), "platform": platform.system(), "architecture": platform.machine(), "python": platform.python_version(),
               "pyinstaller": importlib.metadata.version("pyinstaller"), "mode": "onedir",
               "built_at_utc": datetime.now(timezone.utc).isoformat(), "includes": ["Python runtime", "HTTPS client", "Questionary", "keyring native backend"],
               "excludes": ["credentials", "databases", "downloads", "local state", "PostgreSQL adapter", "SQLite analysis", "model training"]}
    (release / "build-info.json").write_text(json.dumps(details, indent=2) + "\n", encoding="utf-8")
    files = sorted(path for path in release.rglob("*") if path.is_file())
    for path in files:
        relative = path.relative_to(release)
        if any(part in (".env", ".smash", "downloads", ".local-reports") for part in relative.parts) or path.suffix.lower() in (".db", ".sqlite", ".npz", ".nii", ".dcm"):
            raise ValueError("Unexpected private/data file in release")
    (release / "SHA256SUMS.txt").write_text("".join(hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.relative_to(release).as_posix() + "\n" for path in files), encoding="utf-8")
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(release.rglob("*")):
            if path.is_file():
                bundle.write(path, path.relative_to(output))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix(".zip.sha256").write_text(digest + "  " + archive.name + "\n", encoding="utf-8")
    print("Portable release:", archive)
    print("SHA-256:", digest)
    return release / executable


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(ROOT / "dist/binary"))
    args = parser.parse_args()
    build(args.out)
