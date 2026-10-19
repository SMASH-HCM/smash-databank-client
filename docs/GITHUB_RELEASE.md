# Preparing a GitHub release

The canonical repository is **[SMASH-HCM/smash-hcm-databank-client](https://github.com/SMASH-HCM/smash-hcm-databank-client)**, with default branch `main`. Display name: **SMASH-HCM Databank Client**. The package and public command are `smash-hcm-databank-client`; the analysis implementation stays in `smash_hcm_databank_client`, with `python -m smash_hcm_databank_client` as the public module entry point. Existing local checkout folders can retain their old name.

Workflows use `github.repository` rather than hard-coded repository URLs. The client covers downloads, reports and cohort exports; its distribution, portable executable and repository use the same name.

## Automatic release candidate on every main push

**Main release candidate** runs on each push to `main`. It first runs the reusable contract/package test matrix, then native Windows, Linux, Apple Silicon and Intel Mac builds and executable checks. The Python wheel/source package is built and smoke-tested too. Only after all tests/builds and all six artifact checksums pass does it publish a GitHub prerelease. It never marks that candidate as latest stable.

For base version `0.12.0`, run 42 and source commit `abcdef0…`, the GitHub tag is `v0.12.0-rc.42.abcdef0` and the installed package reports `0.12.0rc42`. Version patching happens only in the CI checkout. The generated tag targets the exact source commit, which is also recorded in build metadata. Each main push has a new candidate identity; published candidates are preserved on reruns. Incomplete drafts from the same run/commit can resume their upload. Failed checks do not produce a published candidate.

Pull requests/other branches run checks without publishing. Every main push requests all native jobs, including two Mac runners; organisation runner availability/billing policies apply. No clinical data or Nextcloud passwords are CI inputs. Only publication jobs have `contents: write`; tests/builds are read-only.

Main retains a stable base version in `pyproject.toml` and `src/smash_hcm_databank_client/__init__.py`. After publishing stable `0.12.0`, bump main to the next intended base, e.g. `0.13.0`, so subsequent candidates sort after that release's candidates. Never force-move a published tag or overwrite published candidate assets. [GitHub prerelease/latest options](https://cli.github.com/manual/gh_release_create).

## What users should download

| User | Asset |
|---|---|
| Windows x64, no Python | `smash-hcm-databank-client-<version>-windows-amd64.zip` |
| Mac Apple Silicon, no Python | `smash-hcm-databank-client-<version>-macos-arm64.zip` |
| Mac Intel, no Python | `smash-hcm-databank-client-<version>-macos-x86_64.zip` |
| Linux x64, no Python | `smash-hcm-databank-client-<version>-linux-x86_64.zip` |
| Any supported OS with Python | `smash_hcm_databank_client-<version>-py3-none-any.whl` |
| Developers/reproducible source build | `smash_hcm_databank_client-<version>.tar.gz` |

The Python wheel installs the library and CLI without cloning the full repository. UI and vault extras are installed into the user's virtual environment. Platform ZIPs include the Python runtime, UI and vault dependencies. All ZIPs use folder mode; extract the whole ZIP and keep the executable with `_internal`. macOS builds are unsigned/not notarized, and must pass the native workflow before being described as tested. A Windows build does not verify Mac support.

The workflow tests/builds native Windows, Linux, Apple Silicon Mac and Intel Mac runners. It cannot build a Mac executable locally on Windows: [PyInstaller platform behaviour](https://www.pyinstaller.org/en/stable/operating-mode.html). Current runner labels come from [GitHub's runner reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners). Hosted-runner availability/billing depends on the repository's GitHub plan.

## Reviewed stable release: guided route

1. For a clone still using an old remote URL, set the canonical remote:

   ```powershell
   git remote set-url origin git@github.com:SMASH-HCM/smash-hcm-databank-client.git
   ```

   Check `git remote -v` afterwards.

2. Review `git status` and commit the intended public code, tests, examples, documentation and workflows. Building locally does not commit files. Keep real `.env`, application state, databases, exports and downloads out of the commit. The builders use public-file allowlists; review the Git index separately.

3. For version **0.12.0**, check `pyproject.toml` and `src/smash_hcm_databank_client/__init__.py` both declare it. Push the reviewed commit to main and review **Actions → Main release candidate**, including its nested contract/build jobs.

4. Create an annotated tag at the reviewed commit and push it:

   ```powershell
   git tag -a v0.12.0 -m "SMASH-HCM Databank client 0.12.0"
   git push origin v0.12.0
   ```

   Do not retarget an already published release tag. Fixes should get a new version/tag.

5. On GitHub, open **Actions → Prepare draft release → Run workflow**. Enter `v0.12.0`. The workflow requires an existing tag matching the package version, runs synthetic tests on each native platform, builds/smoke-tests the binaries and Python package, verifies asset checksums, then creates a **draft prerelease**. It stops if that release already exists; it does not overwrite it or publish automatically. No Nextcloud credentials or clinical files are CI inputs.

6. Open the draft under **Releases**. Review the release notes, platform job results and attached assets. Test a downloaded ZIP/wheel on the intended operating systems, check its `.sha256`, and confirm the examples describe current limitations. For a first client release, keeping it marked prerelease is reasonable. Click **Publish release** when satisfied.

The workflow's release job needs `contents: write` permission for its `GITHUB_TOKEN`; other jobs are read-only. An organisation policy may require allowing that workflow permission. Native builds only become available after the workflow is committed, pushed and successfully run. Signing/notarization can be added later; this workflow does not claim to perform them.

Official instructions: [GitHub release management](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository), [GitHub CLI create/draft/tag options](https://cli.github.com/manual/gh_release_create).

## Manual draft from local Windows/Python artifacts

This is useful for reviewing the first release before all native platforms pass. Only attach assets actually tested; do not label a Windows ZIP as a Mac build.

```powershell
gh auth login
gh release create v0.12.0 --repo SMASH-HCM/smash-hcm-databank-client --verify-tag --draft --prerelease --title "SMASH-HCM Databank Client 0.12.0" --notes-file docs/releases/v0.12.0.md dist/binary/smash-hcm-databank-client-0.12.0-windows-amd64.zip dist/binary/smash-hcm-databank-client-0.12.0-windows-amd64.zip.sha256 dist/smash_hcm_databank_client-0.12.0-py3-none-any.whl
```

Run this only after pushing the reviewed stable version tag. This manual workflow stops at a reviewable draft; automatic main candidates publish themselves only after checks pass. Add native assets only after their builds pass.

## Installing the Python release

Mac/Linux, from the folder containing the downloaded wheel:

```sh
python3 -m venv ~/.venvs/smash-databank
~/.venvs/smash-databank/bin/python -m pip install './smash_hcm_databank_client-0.12.0-py3-none-any.whl[ui,secure]'
~/.venvs/smash-databank/bin/python -m smash_hcm_databank_client setup
```

Windows PowerShell:

```powershell
python -m venv .venv-smash
.\.venv-smash\Scripts\python.exe -m pip install ".\smash_hcm_databank_client-0.12.0-py3-none-any.whl[ui,secure]"
.\.venv-smash\Scripts\python.exe -m smash_hcm_databank_client setup
```

On later launches use `python -m smash_hcm_databank_client` from that environment, or its installed `smash-hcm-databank-client` command. No OMOP database is needed to set up/login/download. Python dependencies are installed locally; the optional PostgreSQL adapter is not required. Terminal-only users can omit UI/vault extras and use `--plain` with session or explicitly configured `.env` credentials.
