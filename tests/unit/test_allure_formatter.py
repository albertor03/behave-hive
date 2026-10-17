import importlib
import json
import sys

import pytest

from behave_hive.errors import HiveError

FORMATTER = "behave_hive.formatters.allure:AllureFormatter"

OUTLINE = """\
Feature: F
  Scenario Outline: O
    Given value "<v>"

    Examples:
      | v  |
      | ok |
      | ok |
      | ok |
      | ok |
"""


@pytest.fixture
def project(make_project):
    return make_project()


def run_allure(project, *args, target="features"):
    result = project.run("behave", target, "-f", FORMATTER, "-o", "allure", *args)
    assert result.returncode in (0, 1), result.stdout + result.stderr
    out = project.root / "allure"
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(out.glob("*-result.json"))]


def test_one_result_per_selected_scenario_with_two_locations(project):
    project.write("features/a.feature", OUTLINE)
    results = run_allure(project, target="features/a.feature:7")
    assert len(results) == 1
    results = project.run("behave", "features/a.feature:7", "features/a.feature:9", "-f", FORMATTER, "-o", "allure2")
    assert len(list((project.root / "allure2").glob("*-result.json"))) == 2


def test_all_rows_of_an_outline_each_get_a_result(project):
    project.write("features/a.feature", OUTLINE)
    assert len(run_allure(project)) == 4


def test_scenario_inside_a_rule_has_a_result(project):
    project.write(
        "features/a.feature",
        'Feature: F\n  Rule: R\n    Scenario: in rule\n      Given value "ok"\n',
    )
    (result,) = run_allure(project)
    assert result["status"] == "passed"
    assert "in rule" in result["name"]


def test_results_contain_only_their_own_steps_and_background_steps(project):
    project.write(
        "features/a.feature",
        """\
        Feature: F
          Background:
            Given value "ok"

          Scenario: one
            Given value "ok"
            And value "ok"

          Scenario: two
            Given value "ok"
        """,
    )
    results = {r["name"]: r for r in run_allure(project)}
    assert len(results["one"]["steps"]) == 3
    assert len(results["two"]["steps"]) == 2


def test_error_in_after_scenario_makes_a_passed_scenario_broken(project):
    project.write(
        "features/environment.py",
        'def after_scenario(context, scenario):\n    raise RuntimeError("after boom")\n',
    )
    project.write("features/a.feature", 'Feature: F\n  Scenario: s\n    Given value "ok"\n')
    (result,) = run_allure(project)
    assert result["status"] == "broken"
    assert result["statusDetails"]["message"]


def test_failed_context_cleanup_with_passing_steps_is_broken(project):
    project.write(
        "features/steps/cleanup_steps.py",
        """\
        from behave import given


        def boom():
            raise RuntimeError("cleanup boom")


        @given("a failing cleanup")
        def step_cleanup(context):
            context.add_cleanup(boom)
        """,
    )
    project.write("features/a.feature", "Feature: F\n  Scenario: s\n    Given a failing cleanup\n")
    (result,) = run_allure(project)
    assert result["status"] == "broken"


def test_real_skip_is_reported_as_skipped_even_with_no_skipped(project):
    project.write("features/environment.py", 'def before_scenario(context, scenario):\n    scenario.skip("by hook")\n')
    project.write("features/a.feature", 'Feature: F\n  @skip\n  Scenario: s\n    Given value "ok"\n')
    (result,) = run_allure(project, "--no-skipped")
    assert result["status"] == "skipped"


def test_failed_scenario_keeps_the_status_allure_behave_assigns(project):
    project.write("features/a.feature", 'Feature: F\n  Scenario: s\n    Given value "bad"\n')
    (result,) = run_allure(project)
    assert result["status"] == "failed"


def test_unselected_scenarios_have_no_result(project):
    project.write(
        "features/a.feature",
        'Feature: F\n  @smoke\n  Scenario: tagged\n    Given value "ok"\n  Scenario: untagged\n    Given value "ok"\n',
    )
    (result,) = run_allure(project, "--tags=@smoke")
    assert result["name"] == "tagged"


def test_without_allure_behave_importing_the_formatter_raises_hive_error(monkeypatch):
    monkeypatch.delitem(sys.modules, "behave_hive.formatters.allure", raising=False)
    monkeypatch.setitem(sys.modules, "allure_behave", None)
    with pytest.raises(HiveError, match=r"behave-hive\[allure\]"):
        importlib.import_module("behave_hive.formatters.allure")


# --- original paths (task 5.11) -----------------------------------------------------

CSV_OUTLINE = """\
Feature: Login
  Scenario Outline: Row
    Given value "<v>"

    Examples:
      | read('data/v.csv') |
"""


def run_worker_with_path_map(project, allure_dir):
    """Expand the tree under .behave-hive, then run a worker on it with the path map."""
    from behave_hive.expand import expand_tree

    expanded = (project.root / ".behave-hive" / "run-1" / "roots" / "0" / "features")
    expand_tree(project.features, expanded, "en")
    expanded = expanded.resolve()
    locations = project.root / "tmp.locations"
    locations.write_text(f"{expanded}/a.feature\n", encoding="utf-8")
    plan = project.root / "tmp.plan.json"
    plan.write_text(
        json.dumps(
            {
                "locations_file": str(locations),
                "behave_args": [],
                "cucumber_out": str(project.root / "tmp.json"),
                "allure_dir": str(allure_dir),
                "path_map": {str(expanded): str(project.features.resolve())},
            }
        ),
        encoding="utf-8",
    )
    result = project.run("behave_hive.worker", "--plan", str(plan))
    assert result.returncode == 0, result.stdout + result.stderr
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(allure_dir.glob("*-result.json"))]


def test_original_paths_title_path_names_the_original_directory(project):
    project.write("features/data/v.csv", "v\nok\nok\n")
    project.write("features/a.feature", CSV_OUTLINE)
    results = run_worker_with_path_map(project, project.root / "allure-out")
    assert len(results) == 2
    for result in results:
        assert result["titlePath"] == ["features", "Login"]
        assert ".behave-hive" not in json.dumps(result["titlePath"])
        assert "run-" not in json.dumps(result["titlePath"])


def test_original_paths_history_id_is_the_same_for_the_original_and_the_expanded_run(project):
    project.write("features/data/v.csv", "v\nok\nok\n")
    project.write("features/a.feature", CSV_OUTLINE)
    expanded = run_worker_with_path_map(project, project.root / "allure-out")
    assert len({r["historyId"] for r in expanded}) == 2
    assert all(r["fullName"].startswith("Login: Row") for r in expanded)


def test_original_paths_without_a_path_map_nothing_changes(project):
    project.write("features/a.feature", 'Feature: F\n  Scenario: S\n    Given value "ok"\n')
    (result,) = run_allure(project)
    assert result["titlePath"][-1] == "F"
