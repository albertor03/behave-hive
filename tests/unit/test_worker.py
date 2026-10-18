import json

import pytest

OUTLINE = """\
Feature: F
  Scenario Outline: O
    Given value "<v>"

    Examples:
      | v   |
      | ok  |
      | ok  |
      | bad |
      | ok  |
"""


@pytest.fixture
def project(make_project):
    project = make_project()
    project.write("features/a.feature", OUTLINE)
    return project


def write_plan(project, locations, behave_args=(), allure_dir=None, environment=None):
    locations_file = project.root / "tmp" / "batch-1.locations"
    locations_file.parent.mkdir(exist_ok=True)
    locations_file.write_text("\n".join(locations) + "\n", encoding="utf-8")
    plan = project.root / "tmp" / "batch-1.plan.json"
    plan.write_text(
        json.dumps(
            {
                "locations_file": str(locations_file),
                "behave_args": list(behave_args),
                "cucumber_out": str(project.root / "tmp" / "batch-1.json"),
                "allure_dir": str(allure_dir) if allure_dir else None,
                **({"environment": environment} if environment else {}),
            }
        ),
        encoding="utf-8",
    )
    return plan


def run_worker(project, plan):
    return project.run("behave_hive.worker", "--plan", str(plan))


def result_scenarios(project):
    data = json.loads((project.root / "tmp" / "batch-1.json").read_text(encoding="utf-8"))
    return [e for f in data for e in f["elements"] if e["type"] == "scenario"]


def feature_path(project):
    return str((project.features / "a.feature").resolve())


def test_runs_only_the_locations_of_the_file(project):
    f = feature_path(project)
    result = run_worker(project, write_plan(project, [f"{f}:7", f"{f}:10"]))
    assert result.returncode == 0, result.stdout + result.stderr
    assert [s["line"] for s in result_scenarios(project)] == [7, 10]


def test_a_failing_row_gives_exit_code_1_and_still_writes_the_json(project):
    f = feature_path(project)
    result = run_worker(project, write_plan(project, [f"{f}:9"]))
    assert result.returncode == 1
    (scenario,) = result_scenarios(project)
    assert scenario["x-behave-hive"]["status"] == "failed"


def test_whole_file_location_runs_every_row(project):
    result = run_worker(project, write_plan(project, [feature_path(project)]))
    assert result.returncode == 1
    assert len(result_scenarios(project)) == 4


def test_user_formatters_and_outfiles_from_behave_ini_are_ignored(project):
    project.write("behave.ini", "[behave]\nformat = pretty\noutfiles = pretty.txt\n")
    f = feature_path(project)
    result = run_worker(project, write_plan(project, [f"{f}:7"]))
    assert result.returncode == 0, result.stdout + result.stderr
    assert not (project.root / "pretty.txt").exists()
    assert len(result_scenarios(project)) == 1


def test_nonexistent_formatter_in_behave_ini_does_not_break_the_worker(project):
    project.write("behave.ini", "[behave]\nformat = nonexistent_formatter\n")
    f = feature_path(project)
    result = run_worker(project, write_plan(project, [f"{f}:7"]))
    assert result.returncode == 0, result.stdout + result.stderr


def test_behave_args_are_applied(project):
    project.write(
        "features/b.feature",
        'Feature: B\n  @smoke\n  Scenario: tagged\n    Given value "ok"\n  Scenario: untagged\n    Given value "ok"\n',
    )
    b = str((project.features / "b.feature").resolve())
    result = run_worker(project, write_plan(project, [b], ["--tags=@smoke"]))
    assert result.returncode == 0, result.stdout + result.stderr
    assert [s["name"] for s in result_scenarios(project)] == ["tagged"]


def test_allure_results_go_to_the_allure_dir(project):
    pytest.importorskip("allure_behave")
    f = feature_path(project)
    allure_dir = project.root / "tmp" / "allure-batch-1"
    result = run_worker(project, write_plan(project, [f"{f}:7", f"{f}:8"], allure_dir=allure_dir))
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(list(allure_dir.glob("*-result.json"))) == 2


def test_no_allure_files_without_an_allure_dir(project):
    f = feature_path(project)
    run_worker(project, write_plan(project, [f"{f}:7"]))
    assert not list(project.root.rglob("*-result.json"))


def test_progress_goes_to_stdout(project):
    f = feature_path(project)
    result = run_worker(project, write_plan(project, [f"{f}:7"]))
    assert "Given value" in result.stdout


def test_skipped_scenarios_are_still_reported(project):
    project.write("features/environment.py", 'def before_scenario(context, scenario):\n    scenario.skip("by hook")\n')
    f = feature_path(project)
    result = run_worker(project, write_plan(project, [f"{f}:7"], ["--no-skipped"]))
    assert result.returncode == 0, result.stdout + result.stderr
    assert result_scenarios(project)[0]["x-behave-hive"]["status"] == "skipped"


@pytest.mark.parametrize("error_class", ["ConfigError", "TagExpressionError"])
def test_configuration_error_exits_1_without_results_or_traceback(project, error_class):
    plan = write_plan(project, [feature_path(project)])
    project.write(
        "worker_error.py",
        f'''
        import sys
        from behave.exception import {error_class}
        from behave_hive import worker

        def invalid_config(args):
            raise {error_class}("invalid worker configuration")

        worker.build_behave_config = invalid_config
        sys.exit(worker.main(["--plan", sys.argv[1]]))
        ''',
    )
    result = project.run("worker_error", str(plan))
    assert result.returncode == 1
    assert f"{error_class}: invalid worker configuration" in result.stderr
    assert "Traceback" not in result.stderr
    assert not (project.root / "tmp/batch-1.json").exists()


def test_importing_worker_does_not_start_a_run_or_parse_arguments(project):
    project.write("import_worker.py", "import behave_hive.worker\n")
    before = set(project.root.iterdir())
    result = project.run("import_worker")
    assert result.returncode == 0, result.stderr
    assert result.stdout == result.stderr == ""
    assert set(project.root.iterdir()) == before


def test_environment_properties_are_written_next_to_the_allure_results(project):
    f = project.root / "features" / "a.feature"
    allure_dir = project.root / "tmp" / "allure-batch-1"
    environment = {"mode": "parallel", "workers": "3", "python": "3.14.0"}
    run_worker(project, write_plan(project, [f"{f}:7"], allure_dir=allure_dir, environment=environment))
    lines = (allure_dir / "environment.properties").read_text(encoding="utf-8").splitlines()
    assert lines == ["mode=parallel", "workers=3", "python=3.14.0"]


def test_no_environment_properties_without_environment_data(project):
    f = project.root / "features" / "a.feature"
    allure_dir = project.root / "tmp" / "allure-batch-1"
    run_worker(project, write_plan(project, [f"{f}:7"], allure_dir=allure_dir))
    assert not (allure_dir / "environment.properties").exists()
