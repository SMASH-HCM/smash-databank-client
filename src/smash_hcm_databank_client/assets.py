"""Local asset integrity primitives; format/clinical acceptance remains separate."""
from pathlib import Path, PurePosixPath, PureWindowsPath

from .integrity import sha256


def resolve_asset(root, relative_path):
    root = Path(root).expanduser().resolve(strict=True)
    clean = str(relative_path).replace("\\", "/")
    path = PurePosixPath(clean)
    if not clean.strip() or path.is_absolute() or PureWindowsPath(clean).drive or ".." in path.parts or ":" in clean:
        raise ValueError("Asset path must be relative and contained in the asset root")
    resolved = (root / Path(clean)).resolve(strict=True)
    if resolved == root or root not in resolved.parents or not resolved.is_file():
        raise ValueError("Asset must be a regular file contained in the asset root")
    return resolved


def validate_asset(root, record):
    path = resolve_asset(root, record["relative_path"])
    with path.open("rb") as handle:
        handle.read(1)
    if "size_bytes" in record and path.stat().st_size != int(record["size_bytes"]):
        raise ValueError("Asset size mismatch")
    expected = record.get("sha256")
    if expected and sha256(path) != expected.lower():
        raise ValueError("Asset checksum mismatch")
    return {"asset_id": record.get("asset_id"), "status": "PASS", "checksum_verified": bool(expected)}
