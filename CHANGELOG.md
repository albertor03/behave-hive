# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

These changes are implemented locally; review/integration and remote release
verification are tracked in [STATUS.md](STATUS.md). No version is published yet.

### Added

- HTML-only `report_name` and `report_path` settings, project-name fallback,
  escaped title/heading and atomic writes to nested or absolute output paths.
- Declared development quality tools, regression tests for the gates and
  machine-readable coverage evidence including worker/CLI subprocesses.
- Hardened CI, security scanning/update workflows and a tested release pipeline
  with Trusted Publishing configuration and an approval-gated setup script.
  Remote execution, settings application and publication remain pending.

### Changed

- **Breaking:** the default HTML destination is now `<project-root>/report.html`.
  Set `report_path = reports/report.html` to preserve the earlier location.
  JSON, Allure results and logs continue to use `results_dir`.
- Library coverage now requires exactly 100% statements and branches, with zero
  missing counters, all library modules included and JSON retained by CI.
- Removed a redundant CLI dispatch fallback after proving the parser accepts
  only the required `run` and `expand` commands.

### Security

- Rewrite expanded, working-directory and home prefixes in merged diagnostics
  and Allure status details, including steps and hook containers.
- Add a default-deny HTML CSP with the exact inline script's SHA-256 hash.
- Check process liveness before interruption signals under the process lock.
- Revalidate expansion destinations before deletion and marker creation.
- Create private run configuration files exclusively with owner-only permissions
  and restrict new/existing lock files. Full-tree security/code reviews remain
  pending; accepted limitations are documented in the README.

## [0.1.0] - Unreleased

### Added

- **CSV Examples:** a single `| read('data/users.csv') |` or `| data/users.csv |` cell under `Examples:` is replaced by the rows of the CSV. CSV and hand-written tables can live in the same outline; docstrings are never interpreted; every CSV error names the feature, the line, the file and the row. `behave-hive expand SOURCE DEST` writes the expanded tree.
- **Configuration:** the `[behave_hive]` section of `behave.ini`, `.behaverc`, `setup.cfg`, `tox.ini` or `[tool.behave_hive]` in `pyproject.toml`, with `parallel`, `workers`, `scheme`, `chunk`, `results_dir`, `formats`, `work_dir`, `behave_args` and `paths`; command line overrides; validation of reserved behave arguments and of the effective behave configuration.
- **Parallel runner:** `behave-hive run` runs the suite sequentially or in parallel, per scenario or per feature, in batches of consecutive units with a slot per process (`BEHAVE_HIVE_WORKER`, `BEHAVE_HIVE_BATCH`), a lock on `results_dir`, Ctrl+C handling and exit codes `0`, `1`, `2` and `130`.
- **Reports:** consolidated Cucumber JSON with stable ids and tags with their source line, Allure results with one result per selected scenario, and a self-contained HTML report that shows the CSV source of each row. `CucumberJSONFormatter` and `AllureFormatter` are also usable directly with `behave -f`.
- **Packaging:** installable with `pip` and `uv`, with `allure` and `playwright` extras.
- **Example:** a Playwright login project with CSV data, run sequentially and in parallel by the end-to-end tests.
