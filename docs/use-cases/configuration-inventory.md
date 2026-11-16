# Configuration Inventory: Use Case and Test Cases

## Use case

An engineer analyzes a repository that includes a readable `.env.example` file. They need to know which configuration values must be supplied to run or deploy the project, without CodeAtlas exposing the assigned values that may contain credentials or connection strings.

CodeAtlas records the assignment names and their source file in the generated knowledge base and report. It records no assigned value, and it does not inspect configuration files excluded by the repository walker (including gitignored files).

## Acceptance criteria

1. A readable `.env` or `.env.*` file is considered only when the priority plan identifies it as a configuration file.
2. `KEY=value` and `export KEY=value` assignments produce a `ConfigurationItem` containing `key`, `source_file`, and an unknown `required` state.
3. The generated Markdown report and persisted knowledge section contain configuration names only, never assignment values.
4. Duplicate names in the same source file appear once.
5. A file excluded by the repository walker is not read for configuration discovery.

## Automated test cases

| ID | Scenario | Expected result |
|---|---|---|
| CI-01 | Analyze a repo containing `.env.example` with a normal assignment. | The assignment name and source file appear in `ProjectKnowledge.configuration`. |
| CI-02 | Analyze an `.env.example` containing an `export` assignment. | The assignment name is collected. |
| CI-03 | Use values resembling a token and database URL. | Neither value is present in the Markdown report or SQLite configuration payload. |
| CI-04 | Persist and reload the analysis. | The `configuration` knowledge section contains only the expected serialized item fields. |
| CI-05 | Analyze a gitignored/excluded `.env` file. | The walker excludes it and configuration discovery does not read it. |

CI-01 through CI-04 are implemented by `test_environment_configuration_keys_are_reported_without_values` in `tests/unit/test_m6_orchestrator.py`. CI-05 is covered by the repository-walker exclusion contract and should remain a targeted test if configuration-file exclusion behavior changes.
