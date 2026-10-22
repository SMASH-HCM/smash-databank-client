"""Guided selection and review of published databank artifacts."""
from pathlib import Path

from .manifest import normalized, select_downloads
from .nextcloud import NextcloudError
from .prompts import ask, choose, choose_many, location_choice, text
from .progress import DownloadProgress
from .listing import size_label, file_labels, table_labels


def folder(workspace, read=input, write=print, plain=False):
    return confirm_location(workspace, read, write, plain, message="Use download location:")


def confirm_location(workspace, read=input, write=print, plain=False, message="Download these files to:", suffix=""):
    path = workspace.suggested_download_root()
    while True:
        answer = location_choice(message + " " + text(path) + suffix, read, write, plain)
        if answer == "no":
            write("Download cancelled; no files were transferred." if message.startswith("Download") else "Download location was not changed.")
            return None
        if answer == "yes":
            return workspace.set_download_root(path)
        selected = ask("Download location", str(path), read, write, plain, path=True).strip().strip('"')
        path = Path(selected).expanduser().resolve()


def tags(entries, key):
    return sorted({normalized(tag).upper() for entry in entries for tag in entry[key]})


def download(workspace, category, read=input, write=print, plain=False):
    manifest = workspace.manifest()
    entries = select_downloads(manifest, category)
    if not entries:
        raise NextcloudError("The manifest has no published files in this category")
    if category == "database":
        labels = file_labels(entries)
        chosen = choose(entries, lambda item: labels[item["path"]], read, write, plain, message="Choose the OMOP database release")
        if chosen is None:
            return []
        entries = [chosen]
    elif category in ("reports", "etl"):
        labels = file_labels(entries)
        entries = choose_many(entries, lambda item: labels[item["path"]], read, write, plain,
                              message="Select cohort summaries / landmark tables" if category == "reports" else "Select SMASH-HCM ETL output")
        if not entries:
            return []
    else:
        variable_group = None
        if category == "curated":
            cohorts = choose_many(tags(entries, "cohorts"), str, read, write, plain, message="Specify cohort(s)")
            if not cohorts:
                return []
            def unavailable(kind):
                missing = [cohort for cohort in cohorts if not any(normalized(cohort) in {normalized(tag) for tag in entry["cohorts"]} and normalized(kind) in {normalized(tag) for tag in entry["modalities"]} for entry in entries)]
                return "Not published for: " + ", ".join(missing) if missing else ""
            data_types = tags(entries, "modalities")
            if not any(not unavailable(kind) for kind in data_types):
                raise NextcloudError("No data type is published for every selected cohort. Choose fewer cohorts or browse specific files/folders.")
            modalities = choose_many(data_types, str, read, write, plain, message="Specify data type(s) (MRI / Echo / ECG)", disabled=unavailable)
            if not modalities:
                return []
            entries = select_downloads(manifest, category, cohorts, modalities=modalities)
            write("Selected data types: " + ", ".join(modalities))
        else:
            groups = tags(entries, "variable_groups")
            if groups:
                options = ["Any published variable set"] + groups
                group = choose(options, str, read, write, plain, message="Choose the published variable set")
                if group is None:
                    return []
                variable_group = None if group == options[0] else group
                entries = select_downloads(manifest, category, variable_group=variable_group)
            cohorts = choose_many(tags(entries, "cohorts"), str, read, write, plain, message="Select one or more cohorts")
            if not cohorts:
                write("No cohorts selected; download cancelled.")
                return []
            entries = select_downloads(manifest, category, cohorts, variable_group=variable_group)
            if any(entry.get("preprocessing") for entry in entries):
                formats = sorted({entry.get("preprocessing", "unspecified") for entry in entries})
                selected_formats = choose_many(formats, str, read, write, plain, message="Select preprocessing format(s)")
                if not selected_formats:
                    return []
                entries = select_downloads(manifest, category, cohorts, variable_group=variable_group, preprocessing=selected_formats)
        write("Selected cohorts: " + ", ".join(cohorts))
    return review_download(workspace, entries, category, read, write, plain)


def review_download(workspace, entries, category="files", read=input, write=print, plain=False):
    manifest = workspace.manifest()
    # Folder selections can overlap; transfer each manifest path only once.
    entries = list({entry["path"]: entry for entry in entries}.values())
    if not entries:
        raise NextcloudError("No manifest files were selected")
    write("Release: " + text(manifest["release"]))
    write("Download review: " + str(len(entries)) + " files | " + size_label(sum(item["size_bytes"] for item in entries)))
    rows = [("File", "Size", "Cohorts", "Representation", "Preprocessing", "Comment")]
    for entry in entries:
        scope = ", ".join(entry["cohorts"]) or "whole release"
        representation = entry.get("representation") or "not specified"
        rows.append((entry["path"], size_label(entry["size_bytes"]), scope, representation,
                     entry.get("preprocessing", "not specified"), entry.get("comment", "")))
    for line in table_labels(rows):
        write(line)
    if any(entry["path"].lower().endswith(".zip") for entry in entries):
        write("Archives are downloaded as published. No patient filtering or automatic extraction is performed.")
    location = confirm_location(workspace, read, write, plain)
    if location is None:
        return []
    results, failed = [], []
    for number, entry in enumerate(entries, 1):
        write(str(number) + "/" + str(len(entries)) + " | Downloading " + text(entry["path"]) + "...")
        try:
            with DownloadProgress(entry["path"], write) as progress:
                result = workspace.download_entry(entry, progress=progress)
        except (OSError, ValueError) as exc:
            failed.append(entry["path"])
            write("FAILED | " + text(entry["path"]) + " | " + text(exc))
            continue
        results.append(result)
        write(result["status"] + " | size and SHA-256 verified | " + text(result["local_path"]))
    write("Finished: " + str(len(results)) + " verified, " + str(len(failed)) + " failed.")
    if failed:
        write("Retry the selection to fetch failed files; verified cached files are reused.")
    return results
