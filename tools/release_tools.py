"""Pure helpers for immutable CI candidates and verified release assets."""
import hashlib
from pathlib import Path
import re


def candidate_identity(base, run_number, commit):
    if not re.fullmatch(r"\d+\.\d+\.\d+", base) or not re.fullmatch(r"[1-9]\d*", str(run_number)) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Candidate needs a stable base version, positive run number and full commit SHA")
    return base + "rc" + str(run_number), "v" + base + "-rc." + str(run_number) + "." + commit[:7]


def set_candidate_version(root, version):
    if not re.fullmatch(r"\d+\.\d+\.\d+rc[1-9]\d*", version):
        raise ValueError("Invalid PEP 440 release-candidate version")
    root = Path(root)
    for relative, field in (("pyproject.toml", "version"), ("omop_exporter/__init__.py", "__version__")):
        path = root / relative
        source = path.read_text(encoding="utf-8")
        match = re.search(r'^' + field + r' = "([^"]+)"$', source, re.M)
        if not match or match.group(1) != version.split("rc")[0]:
            raise ValueError("Candidate base differs from the source version")
    # Validate both files before modifying either.
    for relative, field in (("pyproject.toml", "version"), ("omop_exporter/__init__.py", "__version__")):
        path = root / relative
        path.write_text(re.sub(r'^' + field + r' = "[^"]+"$', field + ' = "' + version + '"', path.read_text(encoding="utf-8"), count=1, flags=re.M), encoding="utf-8")


def verified_assets(root):
    root = Path(root).resolve()
    assets = sorted(root.iterdir())
    payloads = [path for path in assets if not path.name.endswith(".sha256")]
    if len([p for p in payloads if p.suffix == ".zip"]) != 4 or len([p for p in payloads if p.suffix == ".whl"]) != 1 or len([p for p in payloads if p.name.endswith(".tar.gz")]) != 1:
        raise ValueError("Expected four platform ZIPs, one wheel and one source archive")
    expected_names = {p.name for p in payloads} | {p.name + ".sha256" for p in payloads}
    if {p.name for p in assets} != expected_names:
        raise ValueError("Unexpected or missing release assets/checksums")
    for path in assets:
        if not path.is_file() or path.is_symlink() or path.resolve().parent != root:
            raise ValueError("Release assets must be regular files inside the artifact directory")
    for path in payloads:
        text = path.with_name(path.name + ".sha256").read_text().strip()
        digest, separator, name = text.partition("  ")
        if not separator or name != path.name or not re.fullmatch(r"[0-9a-f]{64}", digest) or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("Asset checksum mismatch: " + path.name)
    return assets
