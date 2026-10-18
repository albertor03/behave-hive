# Contributing

See [AGENTS.md](AGENTS.md) for the layout, the TDD workflow and the conventions.
Install the development tools with `pip install -e ".[dev,allure,playwright]"`. Work test-first
on a feature branch from `develop`; keep versioned content in English.

```bash
ruff check src tests
pylint src
pytest -m "not e2e and not packaging" --cov --cov-report=term-missing --cov-report=json
pip-audit --local --skip-editable
```

Ruff checks lint, security rules and McCabe complexity (maximum 10; there are no
exceptions). Pylint rejects duplicated blocks of six matching lines in source;
`pylint tests` is informational. Tools are declared in the `dev` extra.

Coverage requires **100% statements and 100% branches** across the entire
`src/behave_hive` library, including future modules and worker/CLI subprocesses.
Scripts, tests, examples and dependencies are outside this gate. Do not narrow
the source list or add exclusions to hide untested library code. `.artifacts/coverage.json`
reports statement counts (`covered_lines`/`num_statements`, `missing_lines`) and
branch counts (`covered_branches`/`num_branches`, `missing_branches`) separately:
both missing counts must be exactly zero. The terminal's combined percentage is
not the branch percentage; rounded percentages alone are not proof of completion.
CI also rejects excluded library lines and prints both exact counter sets.

## CI jobs and artifacts

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
Cucumber JSON and Allure results by test name; `coverage` contains `.artifacts/.coverage`,
`coverage.xml`, `coverage.txt` and `coverage.json` with missing statement/branch
locations. Both artifacts are retained for seven days, including on
failure. To preserve example reports locally, set
`BEHAVE_HIVE_E2E_KEEP=/absolute/path/to/evidence` before running e2e tests.
Artifacts retain report contents, including inputs, tracebacks and screenshots.

## Security

CodeQL scans Python on pushes, pull requests and Mondays at 03:17 UTC. Its job
waits for processing and rejects open high/critical-severity findings on the
scanned ref. Dependency review rejects high-severity vulnerable dependencies and
licenses outside the configured allow-list on pull requests. CodeQL and dependency
review are enabled for public repositories; private repositories skip these jobs
until the appropriate GitHub security plan is configured.

Dependabot proposes grouped weekly updates for pip and GitHub Actions against
`develop`. It only proposes patch updates to `allure-behave`, whose internal API
is used by the formatter. Updates go through the regular pull request checks.
