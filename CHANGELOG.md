# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] - 2026-10-18

### Added

- **JSON Examples:** a single `| data/users.json |` or `| read('data/users.json') |` cell under `Examples:` is replaced by the objects of the file (an array of objects with the same keys; strings, numbers, booleans and `null`). JSON, CSV and hand-written tables can live in the same outline; every JSON error names the feature, the line, the file and the object; the HTML report shows `path.json:N` for each scenario. The start-of-run summary adds `from JSON` when a suite uses JSON tables.

- **Windows support:** the run lock uses `msvcrt` on Windows, each batch runs in its own process group and Ctrl+C ends its whole process tree, and report paths are scrubbed in their Windows spelling. CI runs the unit, end-to-end and packaging suites on Windows, and the release test-installs the wheel there.

### Changed

- **Breaking:** CSV and JSON tables are expanded in memory when behave parses each `.feature`. The working copy of the features root and its symlinks are gone, behave runs the original files, and `work_dir` is accepted but ignored. `behave-hive expand` writes only the expanded `.feature` files.
- The coverage gate is measured on the Linux and Windows runs combined.
- Errors raised for data files are `ExamplesDataError` (`CsvExamplesError` remains as an alias), and the internal `x-behave-hive` source uses `data_path` and `data_row` instead of `csv_path` and `csv_row`.

## [0.1.1] - 2026-10-18

### Fixed

- The README uses absolute URLs for its images and links, so the PyPI project page shows the screenshots and the links work. A unit test rejects relative targets.

## [0.1.0] - 2026-10-18

First release.

### Added

- **CSV Examples:** a single `| read('data/users.csv') |` or `| data/users.csv |` cell under `Examples:` is replaced by the rows of the CSV. CSV and hand-written tables can live in the same outline; docstrings are never interpreted; every CSV error names the feature, the line, the file and the row. `behave-hive expand SOURCE DEST` writes the expanded tree.
- **Configuration:** the `[behave_hive]` section of `behave.ini`, `.behaverc`, `setup.cfg`, `tox.ini` or `[tool.behave_hive]` in `pyproject.toml`, with `parallel`, `workers`, `scheme`, `chunk`, `results_dir`, `formats`, `work_dir`, `behave_args` and `paths`; command line overrides; validation of reserved behave arguments and of the effective behave configuration.
- **Parallel runner:** `behave-hive run` runs the suite sequentially or in parallel, per scenario or per feature, in batches of consecutive units with a slot per process (`BEHAVE_HIVE_WORKER`, `BEHAVE_HIVE_BATCH`), a lock on `results_dir`, Ctrl+C handling and exit codes `0`, `1`, `2` and `130`.
- **Reports:** consolidated Cucumber JSON with stable ids and tags with their source line, Allure results with one result per selected scenario, and a self-contained HTML report that shows the CSV source of each row. `CucumberJSONFormatter` and `AllureFormatter` are also usable directly with `behave -f`.
- **Packaging:** installable with `pip` and `uv`, with `allure` and `playwright` extras.
- **Example:** a Playwright login project with CSV data, run sequentially and in parallel by the end-to-end tests.
- **HTML report:** the page shows failed scenarios first and open, with an error headline and a copy button; the run context with wall time, scenario time and speedup; the worker and batch of each scenario; Scenario Outline groups; and filters (search, status, tag) kept in the URL fragment. `report_name` and `report_path` choose the title and the file; by default it is `report.html` in the project root.
- **Allure:** `context.attach` data becomes an attachment of the step that made it, and `environment.properties` lists versions, mode, workers and scheme.
- **Quality gates:** ruff (lint, security rules and complexity of at most 10), duplicate-code detection, exact 100% statement and branch coverage of the library including subprocesses, and a dependency audit.
- **Delivery:** CI on Linux and macOS with Python 3.11 to 3.14, CodeQL, dependency review, Dependabot and a release workflow that publishes to PyPI with Trusted Publishing.

### Security

- Reports rewrite the run directory, the working directory and the home directory in error messages and Allure status details to original relative paths or `~`.
- The HTML report carries a default-deny Content-Security-Policy with the hash of its inline script.
- Run configuration files are private (owner-only), the results lock does not follow symlinks and generated HTML is replaced atomically; only a file that behave-hive marked as its own HTML is deleted at the start of a run.
- Known limitations are documented in the README.
