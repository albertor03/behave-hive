# behave-hive example

A runnable behave project: Playwright drives a local login page (`app/login.html`) and the
scenarios read their data from CSV files. Each feature shows one capability of behave-hive.

## Run it

```bash
uv venv && uv pip install "behave-hive[allure,playwright]"
uv run python -m playwright install chromium
uv run behave-hive run                       # settings from behave.ini
```

Reports are written to `reports/`: `report.html`, `cucumber.json`, `allure-results/` and `logs/`.
The expected result is 24 scenarios, all passed (the failing table is excluded by `default_tags`).

## What each example shows

The commands assume the environment is active; otherwise prefix them with `uv run`.

| File | Shows | Try |
|---|---|---|
| `features/login.feature` | CSV table (plain path `data/login.csv`), a hand-written table, and a table that fails on purpose (`@expected_fail`). | `behave-hive run -- --tags=@expected_fail` fails and attaches a screenshot. |
| `features/csv/forms.feature` | The plain path (the default form), `read('...')` with single and double quotes, and a data file shared through `..`. | `behave-hive run features/csv/forms.feature` |
| `features/csv/mixed_and_tagged.feature` | CSV (plain path and `read()`) and hand-written tables in one outline, each `Examples:` with its own tag. | `behave-hive run -- --tags=@smoke` (or `@regression`) |
| `features/csv/special_characters.feature` | A pipe, a comma in quotes and a percent sign inside CSV cells reach the step intact. | `behave-hive run features/csv/special_characters.feature` |
| `features/structure/background_and_rule.feature` | `Background` and `Rule` with CSV `Examples:`. | `behave-hive run features/structure` |
| `features/structure/step_data.feature` | Step data tables and docstrings; text inside a docstring is never read as `Examples:`. | `behave-hive run features/structure/step_data.feature` |
| `features/environment.py` | A browser per scenario and a screenshot attached to every failed step (it appears in the HTML report and in Allure). | |

## Configuration examples

| File | Use |
|---|---|
| `behave.ini` | Parallel, 3 workers, scheme `scenario`, all three formats; the HTML goes to `reports/report.html`. |
| `configs/sequential.ini` | One process: `behave-hive run --config configs/sequential.ini`. |
| `configs/feature_scheme.ini` | Parallel with whole features per worker, as needed for `@setup`/`@teardown`. |
| `configs/pyproject.toml` | The same settings as a `[tool.behave_hive]` table, plus a custom `report_name`. |

## Inspect what behave-hive does

```bash
behave-hive expand features /tmp/expanded    # the features with every CSV table written out
```

From a checkout of this repository you can use the local code instead: `uv pip install -e "..[allure,playwright]"`.

See the [main README](../README.md) for the CSV contract, the options and the report details.
