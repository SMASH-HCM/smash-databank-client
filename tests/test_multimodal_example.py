import csv
import json
import zipfile

import pytest

from examples.prepare_multimodal import extract, link


def write(path, fields, rows):
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(fields)
        writer.writerows(rows)


@pytest.mark.parametrize("name", ["../escape.npz", "/absolute.npz", "C:/drive.npz", "a\\escape.npz", "a/./x.npz"])
def test_tutorial_extract_rejects_unsafe_members(tmp_path, name):
    archive = tmp_path / "input.zip"
    with zipfile.ZipFile(archive, "w") as file:
        member = zipfile.ZipInfo("placeholder")
        member.filename = name  # Preserve malformed separators on Windows too.
        file.writestr(member, b"synthetic")
    with pytest.raises(ValueError):
        extract(archive, tmp_path / "out", 100)
    assert not (tmp_path / "out").exists()


def test_tutorial_extract_size_limit_and_no_overwrite(tmp_path):
    archive = tmp_path / "input.zip"
    with zipfile.ZipFile(archive, "w") as file:
        file.writestr("ecg/record.npz", b"synthetic signal placeholder")
    with pytest.raises(ValueError):
        extract(archive, tmp_path / "out", 1)
    extract(archive, tmp_path / "out", 100)
    assert (tmp_path / "out/ecg/record.npz").is_file()
    with pytest.raises(FileExistsError):
        extract(archive, tmp_path / "out", 100)


def test_tutorial_join_preserves_splits_missing_patients_and_prediction_boundary(tmp_path):
    write(tmp_path / "train.csv", ["person_id", "snapshot_date", "measurement__10"], [[1, "2020-01-01", 10], [2, "2020-01-01", 20]])
    write(tmp_path / "test.csv", ["person_id", "snapshot_date", "measurement__10"], [[3, "2020-01-01", 30]])
    root = tmp_path / "assets"
    root.mkdir()
    for name in ("one.npz", "three.npz"):
        (root / name).write_bytes(b"synthetic placeholder; not loaded as a signal")
    fields = ["person_id", "relative_path", "acquisition_date", "available_at_baseline"]
    write(tmp_path / "index.csv", fields, [[1, "one.npz", "2019-12-01", "true"],
                                          [3, "three.npz", "2020-01-01", "true"],
                                          [2, "future.npz", "2020-01-02", "true"],
                                          [2, "unknown.npz", "2019-12-01", "false"]])
    summary = link(tmp_path / "train.csv", tmp_path / "test.csv", tmp_path / "index.csv", root, tmp_path / "out", 730)
    with (tmp_path / "out/train.csv").open() as file:
        rows = list(csv.DictReader(file))
    assert len(rows) == 2 and json.loads(rows[0]["ecg_paths"]) == ["one.npz"]
    assert rows[1]["ecg_count"] == "0" and summary["splits"]["test"]["patients_with_ecg"] == 1
    write(tmp_path / "test.csv", ["person_id", "snapshot_date", "measurement__10"], [[1, "2020-01-01", 10]])
    with pytest.raises(ValueError, match="disjoint"):
        link(tmp_path / "train.csv", tmp_path / "test.csv", tmp_path / "index.csv", root, tmp_path / "bad", 730)


def test_tutorial_link_rejects_escaping_asset(tmp_path):
    write(tmp_path / "train.csv", ["person_id", "snapshot_date"], [[1, "2020-01-01"]])
    write(tmp_path / "test.csv", ["person_id", "snapshot_date"], [])
    write(tmp_path / "index.csv", ["person_id", "relative_path", "acquisition_date", "available_at_baseline"], [[1, "../outside.npz", "2020-01-01", "true"]])
    (tmp_path / "outside.npz").write_bytes(b"synthetic")
    (tmp_path / "assets").mkdir()
    with pytest.raises(ValueError, match="inside asset_root"):
        link(tmp_path / "train.csv", tmp_path / "test.csv", tmp_path / "index.csv", tmp_path / "assets", tmp_path / "out", 730)
