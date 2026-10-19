"""Standard DATA_DIR layout, with explicit cohort memberships and no overwrite."""
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

from .exports import export_events
from .features import freeze_selection
from .output import write_json
from .tabular import export_wide


def cohort_paths(database, cohort, fmt):
    cid = database.cohort_id(cohort) if cohort is not None else None
    info = next((r for r in database.cohorts() if r["cohort_id"] == cid), {"name": "ALL-PEOPLE"})
    name = re.sub(r"[^A-Z0-9]+", "-", info["name"].upper()).strip("-")
    if fmt == "events":
        return Path("event_stream") / name, None
    role = re.search(r"-(TRAINING|TRAIN|TEST|PILOT|EVALUATION|EVAL|ALL-PATIENTS|ALL)$", name)
    group = name[:role.start()] if role else name
    split = {"TRAINING": "train", "TRAIN": "train", "PILOT": "test", "TEST": "test", "EVAL": "evaluation", "EVALUATION": "evaluation", "ALL-PATIENTS": "all", "ALL": "all"}.get(role.group(1) if role else "", "data")
    return Path(group) / split, Path(group) / (split + ".csv")


def export_dataset(database, data_dir, cohorts, variables="core", fmt="tabular", **options):
    if fmt not in ("tabular", "events"):
        raise ValueError("Unsupported dataset format")
    cohorts = list(dict.fromkeys(cohorts))
    if not cohorts:
        raise ValueError("Select at least one cohort")
    # Resolve once to freeze the same source-variable schema across all splits.
    selection = freeze_selection(database, variables)
    root = Path(data_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    plans, targets = [], set()
    for cohort in cohorts:
        companion, csv = cohort_paths(database, cohort, fmt)
        for relative in (companion, csv):
            if relative is None:
                continue
            target = root / relative
            if root not in target.resolve().parents or target in targets or target.exists():
                raise FileExistsError("Output already exists or cohort paths collide: " + str(target) + "; choose a new DATA_DIR")
            targets.add(target)
        plans.append((cohort, companion, csv))
    stage = Path(tempfile.mkdtemp(prefix=".omop-datasets-", dir=str(root)))
    published, created_dirs, results = [], [], []
    try:
        for number, (cohort, companion, csv) in enumerate(plans):
            output = stage / str(number)
            result = export_wide(database, output, cohort, selection, **options) if fmt == "tabular" else export_events(database, output, cohort, selection, **options)
            if csv:
                manifest = json.loads((output / "dataset_manifest.json").read_text())
                manifest["data_file"] = "../" + csv.name
                manifest["output_sha256"]["../" + csv.name] = manifest["output_sha256"].pop("data.csv")
                manifest["split_file_policy"] = "Existing cohort membership. Pilot is a held-out test filename; source cohort ID/name retained. No random splitting."
                write_json(output / "dataset_manifest.json", manifest)
            results.append({**result, "cohort": cohort, "directory": str(root / companion), "data_file": str(root / csv) if csv else str(root / companion / "omop_events.csv")})
        for number, (_, companion, csv) in enumerate(plans):
            parent = (root / companion).parent
            if not parent.exists():
                # Parents are known safe layout components, never source paths.
                missing = []
                cursor = parent
                while not cursor.exists():
                    missing.append(cursor)
                    cursor = cursor.parent
                parent.mkdir(parents=True)
                created_dirs.extend(reversed(missing))
            source = stage / str(number)
            if csv:
                # Exclusive create preserves existing datasets even on a race.
                with (root / csv).open("xb") as dest, (source / "data.csv").open("rb") as src:
                    published.append(root / csv)
                    shutil.copyfileobj(src, dest)
                (source / "data.csv").unlink()
            if (root / companion).exists():
                raise FileExistsError("Output appeared during export: " + str(root / companion))
            os.rename(source, root / companion)
            published.append(root / companion)
        return {"format": fmt, "rows": sum(r["rows"] for r in results), "cohorts": results, "data_dir": str(root)}
    except Exception:
        for path in reversed(published):
            if root not in path.resolve().parents:
                raise ValueError("Unsafe dataset rollback path")
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
        for path in reversed(created_dirs):
            if path.exists() and not any(path.iterdir()):
                path.rmdir()
        raise
    finally:
        if stage.exists() and stage.resolve().parent == root and stage.name.startswith(".omop-datasets-"):
            shutil.rmtree(stage)
