# behave-hive

A layer on top of [behave](https://github.com/behave/behave) 1.3.x that adds:

- **Examples from CSV:** a Karate-style cell, `| read('data/users.csv') |`, under `Examples:`.
- **Sequential or parallel runs:** chosen in `behave.ini` or on the command line.
- **Consolidated reports:** Allure results, standard Cucumber JSON and a self-contained HTML report.

Your steps, your `environment.py` and the way you write features stay the same. A `.feature` without CSV cells runs exactly as it does with behave.

## Installation

```bash
pip install behave-hive                 # or: uv pip install behave-hive
pip install "behave-hive[allure]"       # adds allure-behave 2.16.2 for the Allure format
pip install "behave-hive[playwright]"   # only needed to run the example
```

Requires Python 3.11 or newer. macOS and Linux are supported; Windows is not tested.

## Examples from CSV

```gherkin
Feature: Login

  Scenario Outline: Login as <user>
    Given I open the login page
    When I sign in with user "<user>" and password "<password>"
    Then I see the message "<message>"

    Examples: valid credentials
      | read('data/login.csv') |
```

`data/login.csv`:

```csv
user,password,message
admin,1234,Welcome
admin,wrong,Invalid credentials
```

A table is read from CSV when its first row has **one cell** that is `read('path.csv')`, `read("path.csv")` or a bare path ending in `.csv`. Any other table is a regular, hand-written one. Both kinds can live in the same outline, each under its own `Examples:`, and each keeps its own tags:

```gherkin
    @smoke
    Examples: from a file
      | read('data/login.csv') |

    Examples: written by hand
      | user  | password | message             |
      | guest | guest    | Invalid credentials |
```

The CSV path is relative to the directory of the `.feature` file (subdirectories and `..` are fine). The `Examples:` keyword follows the language of the feature (`# language:` directive or `lang` in `[behave]`).

### CSV contract

- UTF-8, with or without a BOM. The first row is the header; its names are the `<placeholders>`.
- Physically empty lines are ignored. Empty cells are kept.
- Spaces around a cell are lost, as in any Gherkin table. A `|` inside a cell is written as `\|` for you, and the step receives it intact.
- Rejected, with exit code 2 and a message naming the `.feature`, the line, the CSV and the CSV row: no data rows, empty or duplicated headers (after stripping spaces), rows whose width differs from the header, cells with a line break, a missing file and invalid UTF-8.
- Text inside `"""` or `'''` docstrings is never interpreted as `Examples:`.

### What behave-hive writes

When a CSV table is present, the whole features root is copied to a working directory: `.feature` files are written expanded and every other file is a symlink to the original. `uri`s in the reports are the original ones; the HTML report shows `path.csv:row` next to each scenario. To see the result:

```bash
behave-hive expand features /tmp/expanded
```

`expand` refuses, without deleting anything, a destination that is the source or one of its ancestors, a symlink, or a non-empty directory not created by a previous expansion.

## Running

```bash
behave-hive run                         # uses [behave_hive] from behave.ini
behave-hive run --parallel -w 4         # 4 processes
behave-hive run --no-parallel           # one process per features root
behave-hive run features/login.feature   # a directory or a single .feature file
behave-hive run -- --tags=@smoke -D env=qa   # everything after -- goes to behave
```

Every path belongs to a **features root**: the closest directory, walking up, that contains `steps/`. Inputs with the same root share one expansion, and a scenario reachable through two inputs runs once.

| Option | Meaning |
|---|---|
| `--parallel` / `--no-parallel` | Override `parallel`. |
| `-w`, `--workers N` | Number of processes. |
| `--scheme scenario\|feature` | Distribute scenarios (and outline rows) or whole features. |
| `--chunk N` | Units per process; `0` splits the units of a root evenly among the workers. |
| `--results-dir DIR` | Where reports go. |
| `--formats LIST` | Any of `allure`, `cucumber`, `html`. |
| `--config FILE` | Read `[behave_hive]` from this file only. |
| `--keep-tmp` | Keep `results_dir/tmp/` (partial results, locations files). |

Exit codes: `0` all good, `1` a `failed`, `undefined` or `pending` scenario or a batch error, `2` usage, configuration or CSV error, `130` interrupted with Ctrl+C. When nothing matches, `No scenarios found` is printed and the exit code is 0.

## Configuration

Put a `[behave_hive]` section next to `[behave]` in `behave.ini`, `.behaverc`, `setup.cfg` or `tox.ini`, or a `[tool.behave_hive]` table in `pyproject.toml`. Files are looked up in the working directory in that order and the first one with the section wins. behave ignores the section.

```ini
[behave]
default_tags = not @expected_fail

[behave_hive]
parallel = true
workers = 3
scheme = scenario
formats = allure, cucumber, html
```

| Key | Default | Notes |
|---|---|---|
| `parallel` | `false` | `true/false`, `yes/no`, `on/off`, `1/0`. Sequential mode ignores `workers`, `scheme` and `chunk`. |
| `workers` | number of CPUs | At least 1. |
| `scheme` | `scenario` | `scenario` or `feature`. |
| `chunk` | `0` | At least 0. |
| `results_dir` | `reports` | |
| `formats` | `cucumber, html` | Comma or space separated; TOML arrays work too. |
| `work_dir` | `.behave-hive` | Each run uses its own subdirectory. |
| `behave_args` | empty | Shell-style string (`--tags="@a and not @b" -D env=qa`) or a TOML array. `%` is literal. |
| `paths` | `features` | What to run when no path is given. |

Precedence, lowest to highest: default, file, command line. Arguments after `--` are appended after `behave_args`. An unknown key is an error. behave's own settings (`default_tags`, `tags`, `lang`, ...) keep their meaning; `--tags` on the command line overrides `default_tags`, as in behave.

### Arguments behave-hive controls

These are rejected, in `behave_args` and after `--`, with exit code 2:

- positional arguments and `@file`s (paths go before `--`);
- `-f/--format`, `-o/--outfile`, `-r/--runner`, `--junit`, `--junit-directory`;
- `-d/--dry-run`, `--stop`, `-i/--include`, `-e/--exclude`, `-n/--name`, `-w/--wip`.

The same applies to the *effective* behave configuration: `stop`, `dry_run`, `steps_catalog`, `junit`, `wip`, name filters, `include`/`exclude`, `stage` and a custom runner in `[behave]` are rejected, and so are `--version`, `--tags-help`, `--lang-list` and `--lang-help`. `format` and `outfiles` from `[behave]` are ignored.

### Worker identification

Each behave process receives `BEHAVE_HIVE_WORKER` (the slot, `1..workers`; always `1` in sequential mode) and `BEHAVE_HIVE_BATCH` (the 1-based batch index). Two active processes never share a slot, so they can pick ports, users or databases:

```python
import os
port = 9000 + int(os.environ.get("BEHAVE_HIVE_WORKER", "1"))
```

### `@setup` and `@teardown`

behave runs scenarios tagged `@setup` or `@teardown` even when they are not selected. With `parallel = true` and `scheme = scenario`, a feature containing them is rejected; use `scheme = feature` or sequential mode.

## Reports

Everything is written to `results_dir` (default `reports/`):

| Path | Format |
|---|---|
| `cucumber.json` | Standard Cucumber JSON, scenarios in line order, each preceded by its background. |
| `allure-results/` | One Allure result per scenario that behave selected, including scenarios inside a `Rule`. Open it with the Allure CLI: `npx allure@3 generate reports/allure-results`. |
| `report.html` | Self-contained page: no JavaScript, no external requests, light and dark mode. |
| `logs/batch-<n>.log` | Output of each behave process. |

At the start of a run behave-hive deletes only what it manages (`cucumber.json`, `report.html`, `allure-results/`, `logs/`, `tmp/`); anything else in `results_dir` is kept. A second run on the same `results_dir` exits with code 2.

Scenario and feature ids are stable: they do not depend on `workers`, `chunk` or input order. Hook failures and failed `context.add_cleanup` functions count as `failed` (`broken` in Allure). A `pending` step counts as `pending`, except inside a `@wip` scenario.

`CucumberJSONFormatter` also works without behave-hive:

```bash
behave features -f behave_hive.formatters.cucumber:CucumberJSONFormatter -o out.json
```

## Example

`example/` is a Playwright login test with CSV data, one hand-written table and a table that fails on purpose (`@expected_fail`, excluded by `default_tags`; a failed step attaches a screenshot).

```bash
pip install -e ".[dev,allure,playwright]"
python -m playwright install chromium
cd example
behave-hive run                         # parallel, as configured in behave.ini
behave-hive run --no-parallel
behave-hive run -- --tags=@expected_fail
```

## Benchmark

Informational. `example/` with a 12-row CSV plus the hand-written row (13 scenarios, each about 0.3 s), median of 3 runs, wall-clock seconds, macOS, Python 3.14, Chromium headless:

| Mode | Time |
|---|---|
| `behave-hive run --no-parallel` | 4.7 s |
| `behave-hive run --parallel -w 4` | 4.0 s |

The time goes into starting Python, behave and Chromium once per process and into the steps themselves, not into behave-hive. With scenarios this short parallelism barely pays off; it matters for suites where the steps dominate.

## Limitations

- **Lines in expanded features:** rows generated from a CSV, and everything after them in the file, report the lines of the expanded file. The `uri` is the original one and the HTML shows `csv:row`; files without CSV keep their lines.
- **`Path(__file__)` in steps:** steps run through symlinks in the expanded tree. Use `Path(__file__).resolve()` to reach files next to the original step.
- **Unbalanced batches:** units are split into consecutive chunks. Use `chunk = 1` for dynamic balancing, at the cost of one process per unit.
- **`allure-behave` is pinned to 2.16.2**, because the Allure formatter relies on its internals.
- **POSIX only:** the runner uses symlinks and process groups; Windows is not supported.
- **Not supported:** `--stop`, `--dry-run`, `--include`, `--exclude`, `--name`, `--wip`, retries, and data sources other than CSV.

## Contributing

Install the development tools with `pip install -e ".[dev,allure]"`. Work test-first
on a feature branch from `develop`; keep versioned content in English.

```bash
ruff check src tests
pylint src
pytest -m "not e2e and not packaging" --cov --cov-report=term-missing
pip-audit --local --skip-editable
```

Ruff checks lint, security rules and McCabe complexity (maximum 10). The four
baseline complexity findings are temporarily excluded in `pyproject.toml` until
the planned refactor. Pylint rejects duplicated blocks of six matching lines in
source; `pylint tests` is informational. Coverage includes subprocesses and
branches and must reach 90%. Tools are declared in the `dev` extra.

### CI jobs and artifacts

The CI workflow runs on pushes and pull requests to `main` and `develop`:

| Job | Purpose |
| --- | --- |
| `unit` | Linux and macOS, Python 3.11, 3.12, 3.13 and 3.14 |
| `e2e` | Chromium example and HTML report interactions |
| `packaging` | Build and install the wheel with pip and uv |
| `quality` | Ruff, pylint duplicate-code, pip-audit |
| `coverage` | Unit suite with subprocess branch coverage >= 90% |
| `actionlint` | Validate all workflow files and expressions |

Runs have timeouts and superseded CI runs are cancelled. Action references use
release commit SHAs; pip and Playwright downloads are cached. On a failed run,
open the run's **Artifacts** section: `e2e-reports` contains the example's HTML,
Cucumber JSON and Allure results by test name; `coverage` contains `.coverage`,
`coverage.xml` and `coverage.txt`. Both are retained for seven days, including on
failure. To preserve example reports locally, set
`BEHAVE_HIVE_E2E_KEEP=/absolute/path/to/evidence` before running e2e tests.
Artifacts retain report contents, including inputs, tracebacks and screenshots.

## License

MIT, see [LICENSE](LICENSE).
