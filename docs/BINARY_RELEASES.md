# Portable application releases

The collaborator application can be distributed with Python, SQLite/HTTPS support, the arrow-key menu, native credential-vault support and YAML configuration included. Users extract a release ZIP and run `omop-exporter.exe` on Windows; no Python installation, source checkout or pip commands are required. The OMOP database and imaging/ECG assets are separate downloads. Credentials and local state are never release inputs.

## Run a Windows release

1. Extract the entire ZIP into a writable, protected folder. Keep the executable and its `_internal` folder together.
2. Run `omop-exporter.exe` and choose **1. Setup**. You can also use `.\omop-exporter.exe setup` in a terminal to open login setup directly.
3. Configure your login. Automatic access checking then offers **Check for data updates?**; Yes refreshes the manifest and offers selected updates. Connection/manifest actions remain available separately for diagnosis. Request access from the main menu if needed.
4. Choose **2. Download**, then a database, published CSV dataset, cohort ZIPs or specific files/folders. For cohort ZIPs, tick cohorts first, then data types, and review the file list. The manifest browser supports individual/multiple files, direct folder contents and recursive subfolders.
5. Confirm the download folder (default `~/SMASH-HCM`) and confirm the transfer. Use **4. Validate** on later visits to find deleted or modified files. Use **3. Local OMOP** for local reports, saved variable sets and cohort exports. The remaining main choices are **5. Data Access Request** and **6. Exit**. Plain and arrow menus use the same hierarchy.

Current Python and portable installations keep new profiles under `~/.smash/omop-exporter/`. Existing source checkouts with `.smash/state.json` and working-directory `.env` remain compatible. Native vault storage is recommended; explicit plaintext profile storage is optional. Data uses the separately confirmed folder. Override old locations using `menu --state-dir ... --env-file ...`. New bundles contain no developer credentials or configured data paths. See [MENU.md](MENU.md).

Arrow keys and Enter navigate grouped submenus. Enabled actions are colored and disabled choices are grey with an explanation. The numbered menu remains available with `--plain`, for example `.\omop-exporter.exe menu --plain`. Noninteractive streams use plain output automatically. Data Access Request opens only the fixed public form; it does not submit a request.

## Build locally

Build on the target operating system and CPU architecture, in a local environment:

```powershell
python -m venv .venv-build
.\.venv-build\Scripts\python.exe -m pip install -e ".[binary,dev]"
.\.venv-build\Scripts\python.exe -m pytest tests -m "not integration"
.\.venv-build\Scripts\python.exe tools\build_binary.py --out dist\binary
```

The builder uses an explicit public-file allowlist, packages application dependencies and creates a version/platform ZIP, an archive checksum, file checksums, build information and third-party dependency license notices. It refuses an existing release destination. Build in a clean environment for repeatable dependency selection; `build-info.json` records the Python/PyInstaller/platform versions, while third-party notices record library versions. Dependencies are bounded rather than locked, so a later build is not guaranteed byte-identical.

The builder now exclusively uses PyInstaller's folder bundle (`--onedir`): startup is faster and it avoids unpacking the runtime for each launch. The ZIP remains one download and includes Python and the necessary libraries. Keep the executable and `_internal` directory together. The `--onefile` option has been removed. The optional historical PostgreSQL adapter is excluded.

## Defender detection of the historical 0.5.0 one-file build

On 16 October 2026, local Defender records confirmed successful quarantine of the 0.5.0 one-file executable under both `Trojan:Win32/Bearfoos.B!ml` and `Behavior:Win32/DefenseEvasion.A!ml`. The latter records execution. Both threat records were inactive when inspected. This confirms remediation, not that the executable was safe or that no other compromise occurred. Do not distribute that build while its detection is unresolved.

PyInstaller's maintainers document false-positive reports, including possible similarity between one-file executables. This is a possible explanation here, not an independently confirmed false positive. Folder packaging can reduce the triggering behaviour but cannot guarantee antivirus acceptance. See [PyInstaller's maintainer discussion](https://github.com/orgs/pyinstaller/discussions/5877) and [bundle behaviour](https://pyinstaller.org/en/stable/operating-mode.html).

Keep Defender enabled and leave flagged files quarantined; do not add broad exclusions or restore the old executable merely to run it. Review source/build inputs and dependency provenance, scan the replacement folder, then test it only if protection permits. Record the scanner version, signatures, time and findings. A clean scan and matching SHA-256 identify a point-in-time result and an artifact respectively; neither proves absence of malware.

For suspected false positives, the developer can submit the affected public application binary and detection name to [Microsoft Security Intelligence](https://www.microsoft.com/en-us/wdsi/filesubmission) for analysis. This uploads the file to Microsoft; never upload credentials, databases or clinical assets. No submission has been made automatically. Signing official releases establishes publisher identity but does not override malware detections; trusted signing and a clean, reproducible release pipeline remain release work.

Build Windows on Windows, Linux on Linux and macOS on macOS. Native vault availability on Linux still depends on the user's desktop secret service. A Windows build is not proof of Linux/macOS compatibility. These are unsigned portable builds; signing/notarization and a public release publication step remain separate release work. Do not ship a local build as an audited/signed official release.

## Automated artifacts and acceptance

The canonical repository is [SMASH-HCM/smash-hcm-databank-client](https://github.com/SMASH-HCM/smash-hcm-databank-client). **Main release candidate** automatically runs the contract matrix and native Windows/Linux/Apple Silicon/Intel Mac builds on each main push, then publishes a uniquely versioned prerelease with all verified artifacts. It does not replace latest stable. **Portable application** remains manually dispatchable and reusable for builds without publication. **Prepare draft release** handles reviewed stable-version tags and stops at a draft. [Release policy](GITHUB_RELEASE.md). No data or credentials are CI inputs; only actually passing platform jobs establish native acceptance.

Before distributing: run executable help/version, menu navigation, a synthetic database export, native backend detection without storing secrets, and the authorized Nextcloud README test using the executable. Compare published archive checksums. The library tests remain relevant but do not replace frozen-executable tests.

Historical 0.3 acceptance on 15 October 2026 passed both Windows AMD64 modes: runtime/library/native-backend detection, plain menu, synthetic validation and a two-person core baseline export. The folder executable also downloaded the 586-byte Nextcloud README over verified HTTPS. The 0.4 guided-workflow source suite passes 158 tests, including three-cohort selection, CSV filters, download-folder confirmation, missing/changed files, real Questionary checkbox navigation and native Windows console detection. Current executable acceptance is recorded in [TESTING.md](TESTING.md). No credentials or database are release inputs. Local ZIPs are under `dist/binary/`; local results do not establish acceptance on another machine or operating system.

## Terminal UI choice

| Library | Suitable use | Fit here |
| --- | --- | --- |
| Questionary | Arrow-key prompts, disabled choices, checkboxes and nested menus | Implemented: compact, works with existing commands |
| Textual | Full-screen terminal apps, trees, tables, panels and richer layouts | Strong option if the client grows into a dashboard; needs a separate screen/worker design |
| Rich | Styled text, tables and progress displays | Useful presentation layer; selection/navigation needs another library |

References: [Questionary prompts](https://questionary.readthedocs.io/en/stable/pages/types.html), [Questionary styling](https://questionary.readthedocs.io/en/stable/pages/advanced.html), [Textual Tree](https://textual.textualize.io/widgets/tree/), [Rich](https://rich.readthedocs.io/en/stable/introduction.html), [PyInstaller bundle modes](https://pyinstaller.org/en/stable/operating-mode.html) and [platform-specific builds](https://pyinstaller.org/en/stable/usage.html).
