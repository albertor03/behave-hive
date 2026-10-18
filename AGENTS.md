# AGENTS.md

Guidelines for anyone, human or AI agent, working on **behave-hive**. Read this first; the
[README](README.md) is the user's view and [CONTRIBUTING.md](CONTRIBUTING.md) has the CI details.

## What this project is

behave-hive is a layer on top of [behave](https://github.com/behave/behave) 1.3.x that adds:

- **Examples from CSV:** a single cell with the path, `| data/users.csv |` (the default form), or `| read('data/users.csv') |`, under `Examples:`. CSV and hand-written (inline) tables can coexist.
- **Sequential or parallel runs:** configured in the `[behave_hive]` section of `behave.ini`, or with `--parallel/--no-parallel`.
- **Consolidated reports:** Allure results, standard Cucumber JSON and a self-contained HTML report.

## How a run flows

`cli` → `config` → `roots` (group inputs by features root) → `expand` (write the CSV tables into a
working copy of the root) → `discovery` (units: scenarios or features) → `batching` →
`runner.prepare_jobs` (a private plan per batch) → `execution` (one `worker` process per batch,
each running behave with the Cucumber and Allure formatters) → `merge` (original paths, stable
ids) → `summary` and `html_report`. Sequential mode is the same pipeline with one worker.

## Repository layout

| Path | Contents |
|---|---|
| `src/behave_hive/cli.py`, `config.py` | Command line and `[behave_hive]` settings; precedence default < file < command line. |
| `expand.py`, `roots.py` | CSV `Examples:` scanner and the expanded copy of a features root; `PathMap` between expanded and original paths. |
| `discovery.py`, `batching.py`, `selection.py`, `status.py` | Which scenarios run, how they split into batches, which ones behave selected, status mapping. |
| `runner.py`, `execution.py`, `worker.py`, `lock.py` | Plans, cleanup and the `run` orchestration; process pool and interruption; the per-batch behave process; the `results_dir` lock. |
| `merge.py`, `privacy.py`, `summary.py`, `html_report.py`, `templates/report.html` | Merge of partial results, path scrubbing, totals and the HTML page (one inline script, no external resources). |
| `formatters/` | `cucumber.py` and `allure.py` (on top of allure-behave 2.16.2 internals). |
| `tests/unit/` | Fast tests, no browser. |
| `tests/e2e/` | Runs `example/` and rendered reports with Playwright (`e2e` marker). |
| `tests/packaging/` | Builds and installs the wheel with pip and uv (`packaging` marker). |
| `tests/fixtures/i18n/` | The only place where non-English Gherkin test data may live. |
| `tests/schemas/` | Cucumber JSON schema used to validate reports. |
| `example/` | Runnable project with one example per capability; see `example/README.md`. |
| `docs/RELEASING.md` | The maintainer's release checklist. |
| `docs/screenshots.py`, `docs/images/` | Script and output of the README screenshots; see "Screenshots". |

## Development workflow: strict TDD

1. Write the test.
2. Run it and watch it fail for the right reason: `.venv/bin/pytest -x <file>::<test>`.
3. Write the minimal implementation.
4. Watch it pass, then run the whole unit suite.
5. Refactor without breaking anything.

Branches: `main` and `develop`; one `feature/*` (or `fix/*`, `docs/*`, `chore/*`) branch per story from
`develop`, merged into `develop` with `--no-ff`; `develop` reaches `main` only by release. Never commit
directly to either.

## Commands

| Purpose | Command |
|---|---|
| Set up | `python3 -m venv .venv && .venv/bin/pip install -e ".[dev,allure,playwright]" && .venv/bin/python -m playwright install chromium` |
| Unit tests | `.venv/bin/pytest -m "not e2e and not packaging"` |
| E2E tests | `.venv/bin/pytest -m e2e` |
| Packaging tests | `.venv/bin/pytest -m packaging` (requires `uv`) |
| Lint, complexity and security | `.venv/bin/ruff check src tests` |
| Source duplication (six matching lines) | `.venv/bin/pylint src` |
| Exact 100% library statements and branches, including subprocesses | `.venv/bin/pytest -m "not e2e and not packaging" --cov --cov-report=term-missing --cov-report=json` |
| Dependency audit | `.venv/bin/pip-audit --local --skip-editable` |

Coverage data and reports (`.coverage`, `coverage.json`, `coverage.xml`, `htmlcov/`) are written to `.artifacts/`, which is git-ignored, so the project root stays clean. Put any other scratch output of local tools there too.

## Definition of done

A change is done when all of these hold, and you report the real output, not a summary:

- the new behavior has a test that failed first;
- unit, e2e and packaging tests pass;
- `ruff check src tests` is clean (complexity at most 10, no exceptions) and `pylint src` is 10/10;
- `.artifacts/coverage.json` shows `missing_lines` and `missing_branches` both zero and no excluded lines. Report statement and branch counts separately; the combined percentage is not branch coverage. Every module of `src/behave_hive` stays in the denominator; never add `omit` or exclusion patterns to reach the gate;
- `pip-audit` reports no vulnerabilities;
- README, CHANGELOG and `example/` are updated when behavior a user can see changes.

## Conventions

- **Language:** everything versioned is in English: code, identifiers, comments, docstrings, test names, CLI and error messages, HTML report, docs, example data, commit messages and PR descriptions. Non-English test data goes under `tests/fixtures/i18n/` or is written with `\u` escapes.
- **Python:** 3.11+, type hints, `pathlib`. No `print` outside `cli.py`, `summary.py` and `runner.py` (progress output).
- **Errors:** user-facing errors are raised as `HiveError` or a subclass (`errors.py`), never as a raw traceback.
- **Running behave in tests:** always in a subprocess (`project.run("behave", ...)` from the `make_project` fixture), never in-process, because behave keeps global state.
- **Dependencies:** none beyond those declared in `pyproject.toml`. Quality tools (ruff, pylint, pytest-cov, coverage and pip-audit) belong in the `dev` extra. `allure-behave` stays pinned to `2.16.2`, because `formatters/allure.py` relies on its internal API.
- **Commits:** [Conventional Commits](https://www.conventionalcommits.org/), English, imperative mood, for example `feat: add CSV examples scanner` or `fix(merge): keep background before its scenario`.
- **README links:** the README is also the PyPI project page, where relative links and images break. Use absolute URLs (`https://raw.githubusercontent.com/albertor03/behave-hive/main/...` for images, `https://github.com/albertor03/behave-hive/blob/main/...` for files); a unit test enforces it. A published version's page cannot be fixed, only the next release.
- **Examples:** a new capability gets an example under `example/features/` and a row in `example/README.md`; update the scenario count in `tests/e2e/test_example.py`.
- **New modules** go in `src/behave_hive/` with one concern each and their own unit tests; they count toward the 100% gate from the first commit.

## Screenshots

`python docs/screenshots.py` runs `example/` for real and rewrites the PNGs in `docs/images/` (it needs the dev setup with Chromium). Use it sparingly:

- **Run it only when** the HTML report's look changes (`templates/report.html`, CSS, a section added, removed or renamed), when the data in `example/` changes what the images show, or right before a release if the README pictures are visibly stale.
- **Do not run it** for code-only changes, in CI or in tests, or just to refresh. Every run changes the pixels (timestamps, durations), so a changed file is not evidence of a visual change.
- **After running,** open each image: no local paths, no personal data, each under 250 KB (the script fails above that). Commit only the images whose content really changed, in the same commit as the visual change; restore the rest with `git checkout docs/images/<name>.png`.
- **A new picture** needs a new block in the script and a reference in the README; keep the script short and simple.

## Things that bite

- Steps run through symlinks in the expanded tree: resolve `Path(__file__)` before looking for files next to a step.
- Reports must not leak the run directory or the user's home: route error text through `privacy.scrub`.
- `context.attach` reaches Allure only because `AllureFormatter` defines `embedding`; keep that when touching the formatter.
- The HTML page has a hash-based Content-Security-Policy: change the inline script freely (the hash is computed at render time) but do not add external resources or inline event handlers.
- The runner creates plans and locks as owner-only files; keep that when adding run files.
- Never run destructive commands on a user's `results_dir`: cleanup removes only what behave-hive manages.

## Actions that need the maintainer's approval

Commits and merges when not asked for, pushes, creating the remote repository, repository settings,
tags, PyPI configuration and publication. CI and release details are in [CONTRIBUTING.md](CONTRIBUTING.md)
and [docs/RELEASING.md](docs/RELEASING.md).

## Not versioned

These paths are the maintainers' local working files. They are listed in `.gitignore` and must never reach the repository:

| Path | What it is |
|---|---|
| `openspec/` | Local OpenSpec planning: proposals, specs, designs, task lists and verification notes of each change. |
| `.claude/` | Claude Code settings, agents and skills for this project. |
| `CLAUDE.md` | Local instructions for Claude Code; it imports this file. |
| `STATUS.md` | Local progress notes and backlog. |

Rules for everyone, humans and agents:

- Never force-add them (`git add -f`) and never remove them from `.gitignore`; check `git status` before every commit.
- Do not link to them, quote them or rely on them from versioned files (README, CHANGELOG, docs, code comments, commit messages): a reader of the repository cannot see them.
- Do not copy their content into versioned files. If a decision recorded there matters to users or contributors, write it in the README, `CONTRIBUTING.md` or `docs/` instead.
- If a path appears as tracked by git, stop and tell the maintainer before doing anything else.
