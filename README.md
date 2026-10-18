# behave-hive

A layer on top of [behave](https://github.com/behave/behave) 1.3.x that adds:

- **Examples from CSV:** a Karate-style cell, `| read('data/users.csv') |`, under `Examples:`.
- **Sequential or parallel runs:** chosen in `behave.ini` or on the command line.
- **Consolidated reports:** Allure results, standard Cucumber JSON and a self-contained HTML report.

Your steps, your `environment.py` and the way you write features stay the same. A `.feature` without CSV cells runs exactly as it does with behave.

See [Project status and pending work](STATUS.md) for the verified local snapshot,
story progress, integration state and remaining reviews/publication steps.

## Installation

The current `0.1.0` checkout is not published yet. Install it from source with
`pip install -e ".[allure,playwright]"` (or `.[dev,allure,playwright]` for development).
The package-index commands below apply after publication.

```bash
pip install behave-hive                 # or: uv pip install behave-hive
pip install "behave-hive[allure]"       # adds allure-behave 2.16.2 for the Allure format
pip install "behave-hive[playwright]"   # only needed to run the example
```

Requires Python 3.11 or newer. macOS and Linux are supported; Windows is not supported.

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
| `--results-dir DIR` | Where JSON, Allure results and logs go; HTML uses `report_path`. |
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
report_name = My QA project
report_path = reports/report.html
```

| Key | Default | Notes |
|---|---|---|
| `parallel` | `false` | `true/false`, `yes/no`, `on/off`, `1/0`. Sequential mode ignores `workers`, `scheme` and `chunk`. |
| `workers` | number of CPUs | At least 1. |
| `scheme` | `scenario` | `scenario` or `feature`. |
| `chunk` | `0` | At least 0. |
| `results_dir` | `reports` | |
| `report_name` | project name | HTML title and heading only; blank also uses the fallback. |
| `report_path` | `<project-root>/report.html` | Full HTML filename; relative to the project root, or absolute. Parents are created. |
| `formats` | `cucumber, html` | Comma or space separated; TOML arrays work too. |
| `work_dir` | `.behave-hive` | Each run uses its own subdirectory. |
| `behave_args` | empty | Shell-style string (`--tags="@a and not @b" -D env=qa`) or a TOML array. `%` is literal. |
| `paths` | `features` | What to run when no path is given. |

Precedence, lowest to highest: default, file, command line. Arguments after `--` are appended after `behave_args`. An unknown key is an error. behave's own settings (`default_tags`, `tags`, `lang`, ...) keep their meaning; `--tags` on the command line overrides `default_tags`, as in behave.

The project root is the selected configuration file's directory, or the working
directory when no configuration section is selected. An omitted/blank HTML name
uses `[project].name` from that root's `pyproject.toml`, then the folder name.
HTML is now written at the project root by default. Set
`report_path = reports/report.html` to retain the earlier destination.
These settings do not change the generated Allure report's name.

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

JSON, Allure and logs are written to `results_dir` (default `reports/`). The HTML
file uses `report_path` independently (default `<project-root>/report.html`):

| Path | Format |
|---|---|
| `cucumber.json` | Standard Cucumber JSON, scenarios in line order, each preceded by its background. |
| `allure-results/` | One Allure result per scenario that behave selected, including scenarios inside a `Rule`. Open it with the Allure CLI: `npx allure@3 generate reports/allure-results`. |
| `report_path` | Self-contained HTML with inline filters, no external requests, light and dark mode; project name in title and heading. |
| `logs/batch-<n>.log` | Output of each behave process. |

At the start of a run behave-hive deletes only what it manages (`cucumber.json`, `report.html`, `allure-results/`, `logs/`, `tmp/`); anything else in `results_dir` is kept. A second run on the same `results_dir` exits with code 2.

Scenario and feature ids are stable: they do not depend on `workers`, `chunk` or input order. Hook failures and failed `context.add_cleanup` functions count as `failed` (`broken` in Allure). A `pending` step counts as `pending`, except inside a `@wip` scenario.

The HTML carries a default-deny Content-Security-Policy with the hash of its exact
inline script, inline styles and `data:` images. Error-message path rewriting is
described under [Limitations](#limitations). Allure screenshot attachments and
`environment.properties` are planned diagnostics work, not currently delivered.

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
- **CSV access is not sandboxed:** a feature may reference any CSV readable by the
  current user, including paths with `..`; its rows can appear in reports.
- **Retained run configuration:** `--keep-tmp` preserves private plans and
  locations, including `-D key=value` arguments. These files are owner-only
  (`0600`, inside a `0700` temporary directory); remove retained runs when no
  longer needed. The results lock is also owner-only.
- **Report privacy:** behave-hive rewrites expanded roots, the working directory
  and the home prefix in error messages to original relative paths or `~`.
  The directly used Cucumber formatter (`behave -f`) has no run path map and
  does not perform this rewriting. Screenshots and attached data are not scrubbed
  and may contain sensitive application data; scenario inputs can also appear.
- **Expansion race window:** destination checks are repeated before deletion
  and marker creation. This narrows, but does not eliminate, filesystem races.

## Contributing

Install the development tools with `pip install -e ".[dev,allure]"`. Work test-first
on a feature branch from `develop`; keep versioned content in English.

```bash
ruff check src tests
pylint src
pytest -m "not e2e and not packaging" --cov --cov-report=term-missing --cov-report=json:coverage.json
pip-audit --local --skip-editable
```

Ruff checks lint, security rules and McCabe complexity (maximum 10). Temporary
module-level C901 exceptions in `pyproject.toml` remain until HU-10 removes the
complexity debt; the historical baseline had four findings. Pylint rejects duplicated blocks of six matching lines in
source; `pylint tests` is informational. Tools are declared in the `dev` extra.

Coverage requires **100% statements and 100% branches** across the entire
`src/behave_hive` library, including future modules and worker/CLI subprocesses.
Scripts, tests, examples and dependencies are outside this gate. Do not narrow
the source list or add exclusions to hide untested library code. `coverage.json`
reports statement counts (`covered_lines`/`num_statements`, `missing_lines`) and
branch counts (`covered_branches`/`num_branches`, `missing_branches`) separately:
both missing counts must be exactly zero. The terminal's combined percentage is
not the branch percentage; rounded percentages alone are not proof of completion.
CI also rejects excluded library lines and prints both exact counter sets.

### CI jobs and artifacts

The CI workflow runs on pushes and pull requests to `main` and `develop`:

| Job | Purpose |
| --- | --- |
| `unit` | Linux and macOS, Python 3.11, 3.12, 3.13 and 3.14 |
| `e2e` | Chromium example and HTML report interactions |
| `packaging` | Build and install the wheel with pip and uv |
| `quality` | Ruff, pylint duplicate-code, pip-audit |
| `coverage` | Unit suite: exactly 100% library statements and branches, including subprocesses |
| `actionlint` | Validate all workflow files and expressions |

Runs have timeouts and superseded CI runs are cancelled. Action references use
release commit SHAs; pip and Playwright downloads are cached. On a failed run,
open the run's **Artifacts** section: `e2e-reports` contains the example's HTML,
Cucumber JSON and Allure results by test name; `coverage` contains `.coverage`,
`coverage.xml`, `coverage.txt` and `coverage.json` with missing statement/branch
locations. Both artifacts are retained for seven days, including on
failure. To preserve example reports locally, set
`BEHAVE_HIVE_E2E_KEEP=/absolute/path/to/evidence` before running e2e tests.
Artifacts retain report contents, including inputs, tracebacks and screenshots.

### Security

CodeQL scans Python on pushes, pull requests and Mondays at 03:17 UTC. Its job
waits for processing and rejects open high/critical-severity findings on the
scanned ref. Dependency review rejects high-severity vulnerable dependencies and
licenses outside the configured allow-list on pull requests. CodeQL and dependency
review are enabled for public repositories; private repositories skip these jobs
until the appropriate GitHub security plan is configured.

Dependabot proposes grouped weekly updates for pip and GitHub Actions against
`develop`. It only proposes patch updates to `allure-behave`, whose internal API
is used by the formatter. Updates go through the regular pull request checks.

## Releasing

Publishing goes directly to **PyPI** through Trusted Publishing. A published
version and its filenames cannot be replaced, even after deletion.

### One-time setup (requires maintainer approval)

After creating the public repository and observing the first green CI run, review
the exact commands and JSON in [apply_settings.sh](.github/scripts/apply_settings.sh).
With explicit maintainer approval, run `bash .github/scripts/apply_settings.sh`.
It requires all eight `unit (OS, Python)` matrix checks and `e2e`, `packaging`,
`quality`, `coverage`, `actionlint` on both `main` and `develop`, requires up-to-date
pull requests (zero approving code reviews for a solo maintainer), enforces these
rules for administrators and disallows force pushes and deletion.

The same script creates environment `pypi` with reviewer `albertor03`, manual
approval without administrator bypass, and deployment policy `v*` of type `tag`.
Self-review is permitted so the solo maintainer can approve their own release.
Review existing environment policies before reapplying; the script is intended
for initial setup and does not remove existing policies.

The maintainer must also register a pending trusted publisher in the PyPI web UI:

| Field | Value |
| --- | --- |
| PyPI project | `behave-hive` |
| GitHub owner | `albertor03` |
| Repository | `behave-hive` |
| Workflow filename | `release.yml` |
| Environment | `pypi` |

No PyPI API token or password is stored. Inspect settings after applying them:

```bash
gh api repos/albertor03/behave-hive/branches/main/protection
gh api repos/albertor03/behave-hive/branches/develop/protection
gh api repos/albertor03/behave-hive/environments/pypi
gh api repos/albertor03/behave-hive/environments/pypi/deployment-branch-policies
```

### Prepare and rehearse

1. Bump `project.version` in `pyproject.toml` on `develop` (and version assertions
   in the tests), and add `## [X.Y.Z] - YYYY-MM-DD` with notes to `CHANGELOG.md`.
2. Merge `develop` into `main` through a passing pull request.
3. Create the matching tag `vX.Y.Z` on that commit; accepted prereleases are
   `vX.Y.ZaN`, `vX.Y.ZbN` and `vX.Y.ZrcN`, matching the project version exactly.
4. With maintainer approval, push the tag and watch the Release workflow.
   Verification checks the tag format/version, its checked-out commit's
   reachability from `origin/main`, and a real date on the changelog section.
5. For the **first release**, leave the `pypi` deployment unapproved, cancel that
   initial run, and start the manual rehearsal below. The single release
   concurrency group must be free before the rehearsal can start.

In Actions, choose **Release -> Run workflow**, select the existing release **tag**
(not a branch), and keep `dry_run` checked. Equivalently:

```bash
gh workflow run release.yml --ref vX.Y.Z -f dry_run=true
gh run list --workflow release.yml
gh run view RUN_ID
```

The dry run verifies, builds the wheel and sdist once, checks metadata with
`twine check`, installs the wheel in clean environments with pip and uv, and
compares `behave-hive --version` to the tag. Download artifact `dist` to inspect
the exact files; `publish` and `github-release` must be skipped.

After a successful rehearsal, rerun the cancelled initial run (or manually run
the same tag with `dry_run=false`), watch all checks pass, and explicitly approve
the `pypi` deployment. The publish job alone gets OIDC permission. Only after
publication does GitHub Release receive write permission and attach the same
wheel/sdist and the version's changelog notes. Release runs never auto-cancel.

### Recovery

If verification, build or installation fails, nothing is published. Correct the
problem through `develop` and `main` and rehearse again. If publishing fails,
first inspect PyPI to determine whether any file was accepted. If **nothing** was
published, correct the configuration and rerun the failed job; a tag may only be
replaced with explicit maintainer approval before any files are published. If
any file was accepted, never try to replace that version: complete the release
record for those exact artifacts or prepare a new version. If only GitHub
Release failed, rerun that job with the original artifacts rather than rebuilding
or republishing. Do not use `skip-existing` to conceal a partial publication.

## License

MIT, see [LICENSE](LICENSE).
