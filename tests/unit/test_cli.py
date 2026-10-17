import pytest

from behave_hive import cli


def test_version_prints_name_and_version(capsys):
    assert cli.main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == "behave-hive 0.1.0"


def test_split_argv_at_the_first_double_dash():
    assert cli.split_argv(["run", "-x", "--", "-t", "@a", "--", "b"]) == (["run", "-x"], ["-t", "@a", "--", "b"])
    assert cli.split_argv(["run"]) == (["run"], [])


def make_features(tmp_path, csv=True):
    root = tmp_path / "features"
    (root / "steps").mkdir(parents=True)
    ref = "read('v.csv')" if csv else "x"
    (root / "a.feature").write_text(
        f"Feature: F\n  Scenario Outline: S\n    Given x\n    Examples:\n      | {ref} |\n"
    )
    (root / "v.csv").write_text("v\n1\n")
    return root


def test_expand_writes_the_expanded_tree(tmp_path, capsys):
    src = make_features(tmp_path)
    dst = tmp_path / "out"
    assert cli.main(["expand", str(src), str(dst)]) == 0
    assert "| v |\n      | 1 |" in (dst / "a.feature").read_text()
    assert (dst / "v.csv").is_symlink()


def test_expand_reexpansion_removes_stale_feature(tmp_path):
    src = make_features(tmp_path)
    dst = tmp_path / "out"
    assert cli.main(["expand", str(src), str(dst)]) == 0
    (dst / "gone.feature").write_text("Feature: stale\n")
    assert cli.main(["expand", str(src), str(dst)]) == 0
    assert not (dst / "gone.feature").exists()


def test_expand_dangerous_destination_exits_2_without_deleting(tmp_path, monkeypatch, capsys):
    src = make_features(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert cli.main(["expand", "features", "."]) == 2
    assert capsys.readouterr().err.startswith("behave-hive: error: ")
    assert (src / "a.feature").is_file() and (src / "v.csv").is_file()


def test_expand_csv_error_exits_2_with_message_and_no_traceback(tmp_path, capsys):
    src = make_features(tmp_path)
    (src / "v.csv").unlink()
    assert cli.main(["expand", str(src), str(tmp_path / "out")]) == 2
    err = capsys.readouterr().err
    assert err.startswith("behave-hive: error: ")
    assert "v.csv" in err and "Traceback" not in err


# --- 6.7 run --------------------------------------------------------------------

import json
import subprocess
import sys
import time

CSV_FEATURE = """\
Feature: Login
  Scenario Outline: Value
    Given value "<v>"

    Examples:
      | read('data/values.csv') |
"""


@pytest.fixture
def project(make_project):
    return make_project()


def hive(project, *args, timeout=120):
    return project.run("behave_hive.cli", *args, timeout=timeout)


def csv_project(project, rows=("ok",) * 6, feature="features/login.feature", values="data/values.csv"):
    project.write(f"features/{values}", "v\n" + "\n".join(rows) + "\n")
    project.write(feature, CSV_FEATURE.replace("data/values.csv", values))


def test_run_csv_parallel_passes_all_rows(project):
    csv_project(project)
    result = hive(project, "run", "--parallel", "-w", "2")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "6 passed" in result.stdout
    assert "Mode: parallel (2 workers, scheme scenario)" in result.stdout


def test_run_reports_inline_and_csv_example_tables_and_the_csv_files(project):
    csv_project(project)
    project.write(
        "features/inline.feature",
        'Feature: I\n  Scenario Outline: O\n    Given value "<v>"\n    Examples:\n      | v |\n      | ok |\n',
    )
    result = hive(project, "run")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Examples: 1 inline, 1 from CSV" in result.stdout
    assert "features/data/values.csv" in result.stdout
    assert "Mode: sequential" in result.stdout


def test_run_sequential_mode_uses_a_single_batch(project):
    csv_project(project)
    result = hive(project, "run")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "batch 1" in result.stdout and "batch 2" not in result.stdout
    assert [p.name for p in (project.root / "reports" / "logs").glob("*.log")] == ["batch-1.log"]


def test_run_suite_without_csv_runs_original_files_without_an_expanded_tree(project):
    project.write("features/a.feature", 'Feature: F\n  Scenario: S\n    Given value "ok"\n')
    result = hive(project, "run", "--formats", "cucumber", "--keep-tmp")
    assert result.returncode == 0, result.stdout + result.stderr
    assert not (project.root / ".behave-hive" / "roots").exists()
    data = json.loads((project.root / "reports" / "cucumber.json").read_text())
    assert data[0]["uri"] == "features/a.feature"
    assert data[0]["elements"][0]["line"] == 2


def test_run_without_matching_scenarios_prints_a_notice_and_exits_0(project):
    csv_project(project)
    result = hive(project, "run", "--", "--tags=@nonexistent")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "No scenarios found" in result.stdout
    assert not list((project.root / "reports").glob("logs/*"))


def test_run_single_file_uses_the_steps_and_hooks_of_its_root(project):
    project.write("features/auth/login.feature", 'Feature: F\n  Scenario: S\n    Given value "ok"\n')
    project.write("features/environment.py", "def before_all(context):\n    open('hook-ran', 'w').close()\n")
    result = hive(project, "run", "features/auth/login.feature")
    assert result.returncode == 0, result.stdout + result.stderr
    assert (project.root / "hook-ran").exists()


def test_run_overlapping_inputs_run_each_scenario_once(project):
    project.write("features/a.feature", 'Feature: F\n  Scenario: S\n    Given value "ok"\n')
    result = hive(project, "run", "features", "features/a.feature", "--formats", "cucumber")
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads((project.root / "reports" / "cucumber.json").read_text())
    assert len(data[0]["elements"]) == 1


def test_run_two_roots_with_different_steps(project):
    for name in ("a", "b"):
        project.write(
            f"suite_{name}/features/steps/steps.py",
            f'from behave import given\n\n@given("I am in {name}")\ndef step(context):\n    pass\n',
        )
        project.write(f"suite_{name}/features/x.feature", f'Feature: {name}\n  Scenario: S\n    Given I am in {name}\n')
    result = hive(project, "run", "suite_a/features", "suite_b/features")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "2 scenarios (2 passed)" in result.stdout


def test_run_input_without_a_steps_directory_exits_2(project):
    project.write("loose/a.feature", "Feature: F\n")
    result = hive(project, "run", "loose")
    assert result.returncode == 2
    assert "steps" in result.stderr and "loose" in result.stderr


def test_run_missing_input_exits_2(project):
    result = hive(project, "run", "nowhere")
    assert result.returncode == 2
    assert "nowhere" in result.stderr


# --- 6.8 reports ----------------------------------------------------------------


def scenario_ids(project):
    data = json.loads((project.root / "reports" / "cucumber.json").read_text())
    return [e["id"] for f in data for e in f["elements"] if e["type"] == "scenario"]


def test_reports_all_three_formats_from_a_parallel_csv_run(project):
    csv_project(project)
    result = hive(project, "run", "--parallel", "-w", "3", "--formats", "allure,cucumber,html")
    assert result.returncode == 0, result.stdout + result.stderr
    reports = project.root / "reports"
    data = json.loads((reports / "cucumber.json").read_text())
    assert len(data) == 1 and data[0]["uri"] == "features/login.feature"
    assert len([e for e in data[0]["elements"] if e["type"] == "scenario"]) == 6
    assert [e["line"] for e in data[0]["elements"]] == sorted(e["line"] for e in data[0]["elements"])
    assert len(list((reports / "allure-results").glob("*-result.json"))) == 6
    html = (reports / "report.html").read_text()
    assert "features/data/values.csv:2" in html and "6 scenarios (6 passed)" in html
    assert "x-behave-hive" not in (reports / "cucumber.json").read_text()


def test_reports_ids_do_not_depend_on_the_number_of_workers(project):
    csv_project(project)
    assert hive(project, "run", "--parallel", "-w", "3", "--formats", "cucumber").returncode == 0
    three = scenario_ids(project)
    assert hive(project, "run", "--parallel", "-w", "1", "--formats", "cucumber").returncode == 0
    assert scenario_ids(project) == three
    assert len(set(three)) == 6


def test_reports_previous_results_are_replaced_and_other_files_kept(project):
    csv_project(project)
    (project.root / "reports" / "allure-results").mkdir(parents=True)
    (project.root / "reports" / "allure-results" / "old-result.json").write_text("{}")
    (project.root / "reports" / "notes.txt").write_text("keep")
    assert hive(project, "run", "--formats", "allure,cucumber").returncode == 0
    assert not (project.root / "reports" / "allure-results" / "old-result.json").exists()
    assert (project.root / "reports" / "notes.txt").read_text() == "keep"
    assert not (project.root / "reports" / "tmp").exists()


def test_reports_keep_tmp_keeps_the_partials_and_locations(project):
    csv_project(project)
    assert hive(project, "run", "--parallel", "-w", "2", "--keep-tmp").returncode == 0
    tmp = project.root / "reports" / "tmp"
    assert list(tmp.glob("batch-*.json")) and list(tmp.glob("batch-*.locations"))


def test_reports_without_keep_tmp_removes_tmp_and_the_run_directory(project):
    csv_project(project)
    assert hive(project, "run", "--parallel", "-w", "2").returncode == 0
    assert not (project.root / "reports" / "tmp").exists()
    assert not list(project.root.glob(".behave-hive/run-*"))


# --- 6.9 exit codes ---------------------------------------------------------------


def test_exit_code_failing_row_gives_1(project):
    csv_project(project, rows=("ok", "ok", "bad", "ok", "ok", "ok"))
    result = hive(project, "run", "--parallel", "-w", "2")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "5 passed, 1 failed" in result.stdout


def test_exit_code_error_in_before_all_is_a_batch_error_with_its_log(project):
    project.write("features/environment.py", 'def before_all(context):\n    raise RuntimeError("boom")\n')
    project.write("features/a.feature", 'Feature: F\n  Scenario: S\n    Given value "ok"\n')
    result = hive(project, "run")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "batch-1.log" in result.stdout
    assert (project.root / "reports" / "logs" / "batch-1.log").is_file()


def test_exit_code_failed_cleanup_is_1_without_a_batch_error(project):
    project.write(
        "features/steps/cleanup_steps.py",
        'from behave import given\n\ndef boom():\n    raise RuntimeError("x")\n\n@given("a failing cleanup")\ndef step(context):\n    context.add_cleanup(boom)\n',
    )
    project.write("features/a.feature", "Feature: F\n  Scenario: S\n    Given a failing cleanup\n")
    result = hive(project, "run")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "error" not in result.stdout.lower().replace("0 errors", "")


def test_exit_code_pending_step_in_a_wip_scenario_is_0(project):
    project.write(
        "features/steps/pending_steps.py",
        'from behave import given\nfrom behave.exception import StepNotImplementedError\n\n@given("a pending step")\ndef step(context):\n    raise StepNotImplementedError("todo")\n',
    )
    project.write("features/a.feature", "Feature: F\n  @wip\n  Scenario: S\n    Given a pending step\n")
    result = hive(project, "run")
    assert result.returncode == 0, result.stdout + result.stderr


def test_exit_code_pending_step_without_wip_is_1(project):
    project.write(
        "features/steps/pending_steps.py",
        'from behave import given\nfrom behave.exception import StepNotImplementedError\n\n@given("a pending step")\ndef step(context):\n    raise StepNotImplementedError("todo")\n',
    )
    project.write("features/a.feature", "Feature: F\n  Scenario: S\n    Given a pending step\n")
    result = hive(project, "run")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "pending" in result.stdout


def test_exit_code_informational_option_in_passthrough_is_2_without_processes(project):
    csv_project(project)
    result = hive(project, "run", "--", "--version")
    assert result.returncode == 2
    assert not (project.root / "reports" / "logs").exists()


def test_exit_code_nonexistent_user_formatter_in_behave_ini_still_exits_0(project):
    project.write("behave.ini", "[behave]\nformat = nonexistent_formatter\noutfiles = x.txt\n")
    csv_project(project)
    result = hive(project, "run", "--parallel", "-w", "2")
    assert result.returncode == 0, result.stdout + result.stderr
    assert not (project.root / "x.txt").exists()


def test_exit_code_missing_csv_is_2_without_starting_processes(project):
    project.write("features/login.feature", CSV_FEATURE.replace("data/values.csv", "missing.csv"))
    result = hive(project, "run")
    assert result.returncode == 2
    assert "missing.csv" in result.stderr and result.stderr.startswith("behave-hive: error: ")
    assert not (project.root / "reports" / "logs").exists()


def test_exit_code_reserved_argument_is_2(project):
    csv_project(project)
    result = hive(project, "run", "--", "-f", "pretty")
    assert result.returncode == 2
    assert "-f" in result.stderr and "formats" in result.stderr


def test_exit_code_invalid_workers_is_2(project):
    csv_project(project)
    result = hive(project, "run", "-w", "0")
    assert result.returncode == 2
    assert "workers" in result.stderr


# --- 6.11 concurrent runs ---------------------------------------------------------


def test_concurrent_second_run_with_the_same_results_dir_exits_2_and_first_finishes(project):
    project.write("features/a.feature", 'Feature: F\n  Scenario: S\n    Given I wait 3.0 seconds\n')
    first = subprocess.Popen(
        [sys.executable, "-m", "behave_hive.cli", "run"],
        cwd=project.root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        log = project.root / "reports" / "logs" / "batch-1.log"
        deadline = time.monotonic() + 30
        while not log.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        second = hive(project, "run")
        assert second.returncode == 2
        assert "in use" in second.stderr
        output, _ = first.communicate(timeout=60)
        assert first.returncode == 0, output
        assert (project.root / "reports" / "logs" / "batch-1.log").is_file()
    finally:
        if first.poll() is None:
            first.kill()


def test_exit_code_unparsable_feature_is_2_without_a_traceback(project):
    project.write("features/a.feature", "this is not gherkin\n")
    result = hive(project, "run")
    assert result.returncode == 2
    assert result.stderr.startswith("behave-hive: error: ")
    assert "a.feature" in result.stderr and "Traceback" not in result.stderr
