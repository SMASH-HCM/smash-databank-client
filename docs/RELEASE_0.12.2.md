# 0.12.2 — download location and terminal status

- Separate server connectivity and authenticated login indicators in the status panel.
- Use **Download location**, **SMASH-HCM Manifest** (schema and release) and **SMASH-HCM OMOP database** (database version) labels.
- Suggest the OS Downloads folder for new users; respect Windows folder relocation and preserve previously saved custom locations. Startup does not create or persist the unconfirmed default.
- Use one **Yes / No / Change location** download confirmation, with Yes as the default. Apply it to database/CSV/ZIP selections, manifest browsing and tracked-file updates.
- Color terminal failures red, successful outcomes dark green and cancellations orange. Ctrl+C during transfer reports **CANCELLED**. Logs redirected to files and `NO_COLOR` output remain plain.
- Keep the Windows application in folder (`onedir`) form. Extract the whole ZIP and keep `_internal` beside the executable.

The manifest compatibility introduced in 0.12.1 remains: schema `1.0`, legacy `1` representations and compatible newer numeric versions are accepted after structural, path, size and checksum validation. This release changes the client UI; it does not change database contents, export feature definitions or cohort membership.
