import hashlib
from pathlib import Path

import pytest

from tools.release_tools import candidate_identity, set_candidate_version, verified_assets


def test_candidate_versions_are_unique_and_pep440_compatible():
    from packaging.version import Version
    version, tag = candidate_identity("0.11.0", 42, "a" * 40)
    assert version == "0.11.0rc42" and tag == "v0.11.0-rc.42.aaaaaaa"
    assert Version(version).is_prerelease and Version(version) < Version("0.11.0")
    assert candidate_identity("0.11.0", 43, "b" * 40) != (version, tag)


@pytest.mark.parametrize("base,run,commit", [("../bad", 1, "a" * 40), ("0.11.0", 0, "a" * 40), ("0.11.0", 1, "main")])
def test_bad_candidate_identities_rejected(base, run, commit):
    with pytest.raises(ValueError):
        candidate_identity(base, run, commit)


def test_candidate_version_patches_only_matching_source_versions(tmp_path):
    (tmp_path / "src/smash_hcm_databank_client").mkdir(parents=True)
    project = tmp_path / "pyproject.toml"
    module = tmp_path / "src/smash_hcm_databank_client/__init__.py"
    project.write_text('version = "0.11.0"\n')
    module.write_text('__version__ = "0.10.0"\n')
    with pytest.raises(ValueError):
        set_candidate_version(tmp_path, "0.11.0rc42")
    assert project.read_text() == 'version = "0.11.0"\n'
    module.write_text('__version__ = "0.11.0"\n')
    set_candidate_version(tmp_path, "0.11.0rc42")
    assert '"0.11.0rc42"' in project.read_text() and '"0.11.0rc42"' in module.read_text()


def write_assets(root):
    names = ["windows.zip", "linux.zip", "macos-arm64.zip", "macos-x86_64.zip", "client.whl", "client.tar.gz"]
    for name in names:
        payload = ("synthetic artifact " + name).encode()
        (root / name).write_bytes(payload)
        (root / (name + ".sha256")).write_text(hashlib.sha256(payload).hexdigest() + "  " + name + "\n")


def test_release_requires_all_six_verified_assets(tmp_path):
    write_assets(tmp_path)
    assert len(verified_assets(tmp_path)) == 12
    (tmp_path / "windows.zip").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksum mismatch"):
        verified_assets(tmp_path)


def test_missing_or_injected_release_assets_are_rejected(tmp_path):
    write_assets(tmp_path)
    (tmp_path / ".env").write_text("synthetic forbidden file")
    with pytest.raises(ValueError):
        verified_assets(tmp_path)
    (tmp_path / ".env").unlink()
    (tmp_path / "macos-x86_64.zip.sha256").unlink()
    with pytest.raises(ValueError):
        verified_assets(tmp_path)
