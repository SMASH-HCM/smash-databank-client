"""Browse a virtual directory tree built exclusively from manifest file paths."""
from pathlib import PurePosixPath

from .download_flow import review_download, size_label
from .manifest import validate_manifest
from .nextcloud import NextcloudError, remote_path
from .prompts import choose, choose_many, text


class ManifestTree:
    def __init__(self, manifest):
        self.files = {entry["path"]: entry for entry in validate_manifest(manifest)["files"]}
        self.folders = {""}
        for path in self.files:
            for parent in PurePosixPath(path).parents:
                if str(parent) != ".":
                    self.folders.add(str(parent))
        if set(self.files) & self.folders:
            raise NextcloudError("Manifest uses the same path as both a file and a folder")

    def check_folder(self, folder):
        folder = remote_path(folder)
        if folder not in self.folders:
            raise NextcloudError("Folder is not present in the loaded manifest")
        return folder

    def select_folder(self, folder="", recursive=False):
        folder = self.check_folder(folder)
        prefix = folder + "/" if folder else ""
        return [entry for path, entry in sorted(self.files.items()) if path.startswith(prefix) and (recursive or "/" not in path[len(prefix):])]

    def list_folder(self, folder=""):
        folder = self.check_folder(folder)
        prefix = folder + "/" if folder else ""
        folders = sorted(path for path in self.folders if path != folder and path.startswith(prefix) and "/" not in path[len(prefix):])
        return folders, self.select_folder(folder)


def browse(workspace, read=input, write=print, plain=False):
    tree = ManifestTree(workspace.manifest())
    current = ""
    while True:
        folders, files = tree.list_folder(current)
        subtree = tree.select_folder(current, recursive=True)
        options = []
        if current:
            options.append(("up", "< Parent folder", ""))
        options += [
            ("direct", "Download files in this folder (" + str(len(files)) + ")", "" if files else "No files directly in this folder"),
            ("recursive", "Download this folder and all subfolders (" + str(len(subtree)) + ")", "" if subtree else "Folder has no listed files"),
            ("select", "Select specific files in this folder", "" if files else "No files directly in this folder"),
        ]
        for path in folders:
            descendants = tree.select_folder(path, recursive=True)
            label = "[Folder] " + PurePosixPath(path).name + "/ | " + str(len(descendants)) + " files | " + size_label(sum(entry["size_bytes"] for entry in descendants))
            options.append(("dir:" + path, label, ""))
        options += [("file:" + entry["path"], "[File] " + PurePosixPath(entry["path"]).name + " | " + size_label(entry["size_bytes"]), "") for entry in files]
        selected = choose(options, lambda entry: entry[1], read, write, plain, disabled=lambda entry: entry[2], message="Databank /" + text(current))
        if selected is None:
            return []
        action = selected[0]
        if action == "up":
            parent = str(PurePosixPath(current).parent)
            current = "" if parent == "." else parent
        elif action.startswith("dir:"):
            current = tree.check_folder(action[4:])
        else:
            if action == "direct":
                entries = files
            elif action == "recursive":
                entries = subtree
            elif action == "select":
                entries = choose_many(files, lambda entry: PurePosixPath(entry["path"]).name, read, write, plain, message="Select file(s)")
                if not entries:
                    return []
            else:
                entries = [tree.files[action[5:]]]
            write("Folder selection: /" + text(current))
            write("Only files listed in the loaded manifest will be downloaded; archives remain intact.")
            return review_download(workspace, entries, "files", read, write, plain)
