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
| `src/behave_hive/` | The package. One module per concern: `expand`, `roots`, `config`, `discovery`, `batching`, `selection`, `status`, `worker`, `lock`, `runner`, `merge`, `summary`, `html_report`, `cli`, `formatters/`. |
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

## Conventions

- **Language:** everything versioned is in English: code, identifiers, comments, docstrings, test names, CLI and error messages, HTML report, docs, example data, commit messages and PR descriptions. Non-English test data goes under `tests/fixtures/i18n/` or is written with `\u` escapes.
- **Python:** 3.11+, type hints, `pathlib`. No `print` outside `cli.py`, `summary.py` and `runner.py` (progress output).
- **Errors:** user-facing errors are raised as `HiveError` or a subclass (`errors.py`), never as a raw traceback.
- **Running behave in tests:** always in a subprocess (`project.run("behave", ...)` from the `make_project` fixture), never in-process, because behave keeps global state.
- **Dependencies:** none beyond those declared in `pyproject.toml`. `allure-behave` stays pinned to `2.16.2`, because `formatters/allure.py` relies on its internal API.
- **Commits:** [Conventional Commits](https://www.conventionalcommits.org/), English, imperative mood, for example `feat: add CSV examples scanner` or `fix(merge): keep background before its scenario`.

## Not versioned

`openspec/`, `.claude/` and `CLAUDE.md` hold the maintainers' local planning and agent tooling, and are git-ignored. Do not add them to the repository.
