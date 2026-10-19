# SMASH-HCM Databank Client documentation

Canonical repository: [SMASH-HCM/smash-hcm-databank-client](https://github.com/SMASH-HCM/smash-hcm-databank-client). The distribution and public command are `smash-hcm-databank-client`; local OMOP analysis remains part of this application. Current guides are listed below; dated audits retain their historical scope.

| Task | Guide |
|---|---|
| Install Python/client dependencies | [SETUP.md](SETUP.md) |
| Use the menu | [MENU.md](MENU.md) |
| Login and Nextcloud manifest | [NEXTCLOUD.md](NEXTCLOUD.md) |
| Startup/data updates and retained versions | [UPDATES.md](UPDATES.md) |
| Patient reports, variables, histories, events | [LOCAL_OMOP.md](LOCAL_OMOP.md), [DATASET_EXPORTS.md](DATASET_EXPORTS.md) |
| Train/test examples and custom clinical variables | [TABULAR_TUTORIAL.md](TABULAR_TUTORIAL.md) |
| Link cohort ECG files with tabular outputs | [MULTIMODAL_TUTORIAL.md](MULTIMODAL_TUTORIAL.md) |
| Understand cohort baselines, indices and repeated landmarks | [INDEXING_AND_LANDMARKS.md](INDEXING_AND_LANDMARKS.md) |
| Prediction-time rules and limitations | [BASELINE_AVAILABILITY.md](BASELINE_AVAILABILITY.md) |
| Required SQLite tables/metadata | [DATABASE_CONTRACT.md](DATABASE_CONTRACT.md) |
| Portable platform bundles | [BINARY_RELEASES.md](BINARY_RELEASES.md) |
| Automatic main candidates and reviewed stable releases | [GITHUB_RELEASE.md](GITHUB_RELEASE.md) |
| Test history and external limitations | [TESTING.md](TESTING.md) |
| Historical PostgreSQL scripts | [LEGACY_POSTGRES_WORKFLOW.md](LEGACY_POSTGRES_WORKFLOW.md), [EXPORT_METHODOLOGY.md](EXPORT_METHODOLOGY.md) |

The initial [status review](STATUS_AND_IMPLEMENTATION_PLAN.md), [18 October RC4 validation](RC4_VALIDATION_2026-10-18.md), [database-agent feedback](RC4_DATABASE_AGENT_FEEDBACK_2026-10-18.md), and [19 October format notice](RC4_FORMAT_CHANGE_2026-10-19.md) are dated evidence, not guarantees about a subsequently replaced database or server. Actual patient-level records remain outside Git.
