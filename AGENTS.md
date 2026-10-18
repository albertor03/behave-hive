# AGENTS.md

Guidelines for anyone, human or AI agent, working on **behave-hive**.

## What this project is

behave-hive is a layer on top of [behave](https://github.com/behave/behave) 1.3.x that adds:

- **Examples from CSV:** a single cell `| read('data/users.csv') |` or `| data/users.csv |` under `Examples:`. CSV and hand-written (inline) tables can coexist.
- **Sequential or parallel runs:** configured in the `[behave_hive]` section of `behave.ini`, or with `--parallel/--no-parallel`.
- **Consolidated reports:** Allure results, standard Cucumber JSON and a self-contained HTML report.

## Repository layout

| Path | Contents |
|---|---|
| `STATUS.md` | Verified project snapshot, delivery state and pending work; distinguish implementation from integration/publication. |
| `src/behave_hive/` | The package. One module per concern: `expand`, `roots`, `config`, `discovery`, `batching`, `selection`, `status`, `worker`, `lock`, `execution`, `runner`, `merge`, `summary`, `html_report`, `cli`, `formatters/`. |
| `tests/unit/` | Fast tests, no browser. |
| `tests/e2e/` | Runs `example/` with Playwright (`e2e` marker). |
| `tests/packaging/` | Builds and installs the wheel with pip and uv (`packaging` marker). |
| `tests/fixtures/i18n/` | The only place where non-English Gherkin test data may live. |
| `tests/schemas/` | Cucumber JSON schema used to validate reports. |
| `example/` | Playwright login example with CSV data. |

## Development workflow: strict TDD

1. Write the test.
2. Run it and watch it fail for the right reason: `.venv/bin/pytest -x <file>::<test>`.
3. Write the minimal implementation.
4. Watch it pass, then run the whole unit suite.
5. Refactor without breaking anything.

## Commands

| Purpose | Command |
|---|---|
| Set up | `python3 -m venv .venv && .venv/bin/pip install -e ".[dev,allure,playwright]" && .venv/bin/python -m playwright install chromium` |
| Unit tests | `.venv/bin/pytest -m "not e2e and not packaging"` |
| E2E tests | `.venv/bin/pytest -m e2e` |
| Packaging tests | `.venv/bin/pytest -m packaging` (requires `uv`) |
| Lint, complexity and security | `.venv/bin/ruff check src tests` |
| Source duplication (six matching lines) | `.venv/bin/pylint src` |
| Exact 100% library statements and branches, including subprocesses | `.venv/bin/pytest -m "not e2e and not packaging" --cov --cov-report=term-missing --cov-report=json:coverage.json` |
| Dependency audit | `.venv/bin/pip-audit --local --skip-editable` |

## Continuous integration and releases

CI has six jobs: `unit` (Linux/macOS, Python 3.11-3.14), `e2e`, `packaging`,
`quality`, `coverage` and `actionlint`. Every action is pinned to a release commit;
actionlint is a versioned CLI download with a verified checksum. Read the
`e2e-reports` and `coverage` artifacts on a failed run (retained for seven days).
Set `BEHAVE_HIVE_E2E_KEEP` locally to preserve example reports by test name.
The coverage artifact includes `coverage.json`: `missing_lines` and
`missing_branches` must both be zero, with no excluded library lines. Report
covered/total/missing statement and branch counts separately; the combined
percentage is not branch coverage. Keep all of `src/behave_hive`, including new
modules, in the denominator; never add omit/exclusion patterns to reach the gate.
Scripts, tests, examples and dependencies are outside this library-only target.

CodeQL, dependency review and Dependabot provide repository security checks.
Release tags run `verify` -> `build` -> `test-install` (pip/uv) -> `publish` ->
`github-release`. Use the manual dry run before approving a PyPI deployment.
See README "Releasing" for the exact preparation, protection and recovery steps.
Repository settings, pushes and publication require the maintainer's explicit approval.

## Conventions

- **Language:** everything versioned is in English: code, identifiers, comments, docstrings, test names, CLI and error messages, HTML report, docs, example data, commit messages and PR descriptions. Non-English test data goes under `tests/fixtures/i18n/` or is written with `\u` escapes.
- **Python:** 3.11+, type hints, `pathlib`. No `print` outside `cli.py`, `summary.py` and `runner.py` (progress output).
- **Errors:** user-facing errors are raised as `HiveError` or a subclass (`errors.py`), never as a raw traceback.
- **Running behave in tests:** always in a subprocess (`project.run("behave", ...)` from the `make_project` fixture), never in-process, because behave keeps global state.
- **Dependencies:** none beyond those declared in `pyproject.toml`. Quality tools (ruff, pylint, pytest-cov, coverage and pip-audit) belong in the `dev` extra. `allure-behave` stays pinned to `2.16.2`, because `formatters/allure.py` relies on its internal API.
- **Commits:** [Conventional Commits](https://www.conventionalcommits.org/), English, imperative mood, for example `feat: add CSV examples scanner` or `fix(merge): keep background before its scenario`.

## Not versioned

`openspec/`, `.claude/` and `CLAUDE.md` hold the maintainers' local planning and agent tooling, and are git-ignored. Do not add them to the repository.
