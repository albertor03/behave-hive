import json
import platform
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

from behave_hive import cli


def test_version_prints_name_and_version(capsys):
    assert cli.main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == "behave-hive 0.1.0"


def test_split_argv_at_the_first_double_dash():
    assert cli.split_argv(["run", "-x", "--", "-t", "@a", "--", "b"]) == (["run", "-x"], ["-t", "@a", "--", "b"])
    assert cli.split_argv(["run"]) == (["run"], [])


@pytest.mark.parametrize("argv", [[], ["unknown"]])
def test_required_subcommand_rejects_missing_or_unknown_input(argv, capsys):
    assert cli.main(argv) == 2
    assert "usage: behave-hive" in capsys.readouterr().err


@pytest.mark.parametrize("argv, command", [(["run"], "run"), (["expand", "features", "out"], "expand")])
def test_parser_accepts_the_two_supported_subcommands(argv, command):
    assert cli.build_parser().parse_args(argv).command == command


def test_keyboard_interrupt_during_configuration_returns_130_without_traceback(monkeypatch, capsys):
    def interrupted(*args):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "load_config", interrupted)
    assert cli.main(["run"]) == 130
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


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

CSV_FEATURE = """\
Feature: Login
  Scenario Outline: Value
    Given value "<v>"

    Examples:
      | read('data/values.csv') |
"""


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


def test_examples_summary_lists_a_shared_csv_once_for_two_tables(project):
    csv_project(project, rows=("ok",))
    project.write("features/second.feature", CSV_FEATURE.replace("Feature: Login", "Feature: Second"))
    result = hive(project, "run")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Examples: 0 inline, 2 from CSV" in result.stdout
    assert result.stdout.count("  - features/data/values.csv") == 1
    assert "2 scenarios (2 passed)" in result.stdout


@pytest.mark.parametrize("error_class", ["ConfigError", "TagExpressionError"])
def test_behave_configuration_errors_are_user_facing_exit_2(project, error_class):
    csv_project(project, rows=("ok",))
    project.write(
        "runner_error.py",
        f'''
        import sys
        from behave.exception import {error_class}
        from behave_hive import runner
        from behave_hive.cli import main

        def invalid_config(args):
            raise {error_class}("invalid behave configuration")

        runner.build_behave_config = invalid_config
        sys.exit(main(["run"]))
        ''',
    )
    result = project.run("runner_error")
    assert result.returncode == 2
    assert f"{error_class}: invalid behave configuration" in result.stderr
    assert "Traceback" not in result.stderr
    assert not (project.root / "reports/logs").exists()


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
    html = (project.root / "report.html").read_text()
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
        'from behave import given\n\ndef boom():\n    raise RuntimeError("x")\n\n'
        '@given("a failing cleanup")\ndef step(context):\n    context.add_cleanup(boom)\n',
    )
    project.write("features/a.feature", "Feature: F\n  Scenario: S\n    Given a failing cleanup\n")
    result = hive(project, "run")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "error" not in result.stdout.lower().replace("0 errors", "")


def test_exit_code_pending_step_in_a_wip_scenario_is_0(project):
    project.write(
        "features/steps/pending_steps.py",
        'from behave import given\nfrom behave.exception import StepNotImplementedError\n\n'
        '@given("a pending step")\ndef step(context):\n    raise StepNotImplementedError("todo")\n',
    )
    project.write("features/a.feature", "Feature: F\n  @wip\n  Scenario: S\n    Given a pending step\n")
    result = hive(project, "run")
    assert result.returncode == 0, result.stdout + result.stderr


def test_exit_code_pending_step_without_wip_is_1(project):
    project.write(
        "features/steps/pending_steps.py",
        'from behave import given\nfrom behave.exception import StepNotImplementedError\n\n'
        '@given("a pending step")\ndef step(context):\n    raise StepNotImplementedError("todo")\n',
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


def allure_results(project):
    paths = sorted((project.root / "reports" / "allure-results").glob("*-result.json"))
    return [json.loads(p.read_text()) for p in paths]


def test_allure_paths_never_mention_the_run_directory(project):
    csv_project(project)
    result = hive(project, "run", "--parallel", "-w", "2", "--formats", "allure")
    assert result.returncode == 0, result.stdout + result.stderr
    results = allure_results(project)
    assert len(results) == 6
    for item in results:
        assert item["titlePath"] == ["features", "Login"], item["titlePath"]


def test_allure_paths_history_ids_do_not_depend_on_the_workers(project):
    csv_project(project)
    assert hive(project, "run", "--parallel", "-w", "3", "--formats", "allure").returncode == 0
    three = sorted(r["historyId"] for r in allure_results(project))
    assert hive(project, "run", "--parallel", "-w", "1", "--formats", "allure").returncode == 0
    assert sorted(r["historyId"] for r in allure_results(project)) == three
    assert len(set(three)) == 6


def test_report_name_and_default_path_use_the_project_folder(project):
    csv_project(project, rows=("ok",))
    result = hive(project, "run")
    assert result.returncode == 0, result.stdout + result.stderr
    page = (project.root / "report.html").read_text()
    assert f"<title>{project.root.name}</title>" in page
    assert not (project.root / "reports/report.html").exists()


@pytest.mark.parametrize("absolute", [False, True])
def test_report_name_and_custom_path_leave_other_formats_in_results_dir(project, absolute):
    csv_project(project, rows=("ok",))
    target = project.root / "evidence/nested/login.html"
    setting = str(target) if absolute else "evidence/nested/login.html"
    project.write("behave.ini", f"[behave_hive]\nreport_name = Portal QA\nreport_path = {setting}\n")
    result = hive(project, "run", "--formats", "allure,cucumber,html")
    assert result.returncode == 0, result.stdout + result.stderr
    page = target.read_text()
    assert "<title>Portal QA</title>" in page and "<h1>Portal QA</h1>" in page
    assert (project.root / "reports/cucumber.json").is_file()
    assert list((project.root / "reports/allure-results").glob("*-result.json"))
    assert not (project.root / "report.html").exists()


def test_report_path_write_error_is_a_user_facing_error(project):
    csv_project(project, rows=("ok",))
    project.write("blocked", "a file, not a directory")
    project.write("behave.ini", "[behave_hive]\nreport_path = blocked/report.html\n")
    result = hive(project, "run")
    assert result.returncode == 2
    assert "cannot write HTML report" in result.stderr and "Traceback" not in result.stderr


def test_privacy_of_failing_csv_row_in_all_report_formats(project):
    csv_project(project, rows=("bad",))
    result = hive(project, "run", "--formats", "allure,cucumber,html")
    assert result.returncode == 1, result.stdout + result.stderr
    reports = [project.root / "reports/cucumber.json", project.root / "report.html"]
    reports += list((project.root / "reports/allure-results").glob("*-result.json"))
    assert len(reports) == 3
    for report in reports:
        text = report.read_text()
        assert ".behave-hive" not in text, report
        assert "run-" not in text, report
        assert str(Path.home()) not in text, report
        assert "features/steps/steps.py" in text


def test_run_without_scenarios_removes_the_previous_report_it_generated(project):
    csv_project(project)
    assert hive(project, "run").returncode == 0
    report = project.root / "report.html"
    assert report.is_file()

    result = hive(project, "run", "--", "--tags=@nonexistent")
    assert result.returncode == 0, result.stdout + result.stderr
    assert not report.exists()


def test_run_keeps_a_report_path_file_that_behave_hive_did_not_generate(project):
    csv_project(project)
    project.write("report.html", "<html>precious</html>")
    result = hive(project, "run", "--", "--tags=@nonexistent")
    assert result.returncode == 0, result.stdout + result.stderr
    assert (project.root / "report.html").read_text() == "<html>precious</html>"


def read_properties(path):
    return dict(line.split("=", 1) for line in path.read_text(encoding="utf-8").splitlines())


def test_allure_environment_lists_versions_mode_workers_and_scheme(project):
    csv_project(project)
    result = hive(project, "run", "--parallel", "-w", "3", "--formats", "allure,cucumber")
    assert result.returncode == 0, result.stdout + result.stderr

    props = read_properties(project.root / "reports" / "allure-results" / "environment.properties")
    assert props["mode"] == "parallel"
    assert props["workers"] == "3"
    assert props["scheme"] == "scenario"
    assert props["behave-hive"] == hive(project, "--version").stdout.split()[1]
    assert props["python"] == platform.python_version()
    assert re.fullmatch(r"\d+\.\d+(\.\d+)?", props["behave"])


def test_allure_environment_in_sequential_mode_has_one_worker(project):
    csv_project(project)
    assert hive(project, "run", "--formats", "allure,cucumber").returncode == 0
    props = read_properties(project.root / "reports" / "allure-results" / "environment.properties")
    assert (props["mode"], props["workers"]) == ("sequential", "1")


def test_html_report_shows_the_run_context(project):
    csv_project(project)
    result = hive(project, "run", "--parallel", "-w", "3", "--formats", "html")
    assert result.returncode == 0, result.stdout + result.stderr

    page = (project.root / "report.html").read_text(encoding="utf-8")
    section = re.search(r'<section class="run">(.*?)</section>', page, re.S).group(1)
    context = dict(re.findall(r"<dt>(.*?)</dt><dd>(.*?)</dd>", section))
    assert context["Mode"] == "parallel, 3 workers, scheme scenario"
    assert context["Command"] == "behave-hive run --parallel -w 3 --formats html"
    assert re.fullmatch(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d", context["Started"])
    assert context["Versions"].endswith(f"Python {platform.python_version()}")
    assert "Speedup" in context


def test_html_report_command_does_not_leak_the_home_directory(project, monkeypatch):
    csv_project(project)
    monkeypatch.setenv("HOME", str(project.root))
    result = hive(project, "run", "--formats", "html", "--results-dir", str(project.root / "out"))
    assert result.returncode == 0, result.stdout + result.stderr

    page = (project.root / "report.html").read_text(encoding="utf-8")
    assert str(project.root) not in page
    assert "--results-dir out" in page
