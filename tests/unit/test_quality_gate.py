"""Exercise real quality tools against deliberate regressions, outside the source tree."""

import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from coverage import CoverageData

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "pyproject.toml"


def test_coverage_configuration_requires_complete_library_without_exemptions():
    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))["tool"]["coverage"]
    assert config["run"]["source"] == ["behave_hive"]
    assert config["run"]["branch"] is True
    assert config["run"]["parallel"] is True
    assert "subprocess" in config["run"]["patch"]
    assert not config["run"].get("omit")
    assert not config["report"].get("omit")
    assert not config["report"].get("exclude_lines")
    assert not config["report"].get("exclude_also")
    assert config["report"]["fail_under"] == 100
    assert config["report"]["precision"] == 2


@pytest.mark.parametrize("gap", ["statement", "branch", "new-module", "complete"])
def test_coverage_gate_rejects_any_missing_statement_or_branch(tmp_path, gap):
    package = tmp_path / "probe"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    code = (
        'def choose(value):\n    result = "no"\n    if value:\n        result = "yes"\n    return result\n'
        + "".join(f"constant_{n} = {n}\n" for n in range(100))
    )
    if gap == "statement":
        code += '\ndef unused():\n    return "never called"\n'
    (package / "exercised.py").write_text(code, encoding="utf-8")
    if gap == "new-module":
        (package / "new_module.py").write_text('value = "not imported"\n', encoding="utf-8")
    launcher = tmp_path / "launch.py"
    launcher.write_text(
        "from probe import exercised\nexercised.choose(True)\n"
        + ("exercised.choose(False)\n" if gap != "branch" else ""), encoding="utf-8",
    )
    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))["tool"]["coverage"]
    # Override only the source in this disposable project; retain every real gate setting.
    config["run"]["source"] = ["probe"]
    rcfile = tmp_path / "pyproject.toml"
    rcfile.write_text("\n".join(
        f"[tool.coverage.{section}]\n" + "\n".join(f"{k} = {json.dumps(v)}" for k, v in settings.items())
        for section, settings in config.items()
    ), encoding="utf-8")
    env = {**os.environ, "COVERAGE_FILE": str(tmp_path / ".coverage")}

    def coverage(*args):
        return subprocess.run(
            [sys.executable, "-m", "coverage", args[0], f"--rcfile={rcfile}", *args[1:]],
            cwd=tmp_path, env=env, capture_output=True, text=True, check=False,
        )

    measured = coverage("run", str(launcher))
    assert measured.returncode == 0, measured.stdout + measured.stderr
    combined = coverage("combine")
    assert combined.returncode == 0, combined.stdout + combined.stderr
    result = coverage("json", "-o", "coverage.json")
    data = json.loads((tmp_path / "coverage.json").read_text(encoding="utf-8"))
    totals = data["totals"]
    assert totals["missing_lines"] == (1 if gap in ("statement", "new-module") else 0)
    assert totals["missing_branches"] == (1 if gap == "branch" else 0)
    if gap == "new-module":
        assert data["files"]["probe/new_module.py"]["executed_lines"] == []
    if gap == "complete":
        assert result.returncode == 0, result.stdout + result.stderr
        assert totals["percent_covered"] == 100
    else:
        # Each incomplete fixture is above 98%: the former 90% gate would wrongly pass.
        assert 98 < totals["percent_covered"] < 100
        assert result.returncode == 2, result.stdout + result.stderr


def test_ruff_rejects_complexity_and_shell_execution(tmp_path):
    module = tmp_path / "regression.py"
    branches = "".join(f"    if value == {n}:\n        return {n}\n" for n in range(10))
    module.write_text(
        "import subprocess\n\ndef complex_function(value):\n" + branches
        + '\ndef risky(command):\n    subprocess.run(command, shell=True)\n', encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--config", str(CONFIG), str(module)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 1
    assert "C901" in result.stdout and "complex_function" in result.stdout
    assert "S602" in result.stdout


def test_duplicate_gate_names_both_modules(tmp_path):
    block = """def duplicated(values):
    result = []
    for value in values:
        normalized = str(value).strip()
        result.append(normalized.lower())
    result.sort()
    return tuple(result)
"""
    modules = [tmp_path / "first.py", tmp_path / "second.py"]
    for module in modules:
        module.write_text(block, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "pylint", "--rcfile", str(CONFIG), *(str(p) for p in modules)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode != 0
    assert "duplicate-code" in result.stdout
    assert "first" in result.stdout and "second" in result.stdout


def test_coverage_measures_worker_subprocess(make_project, tmp_path):
    project = make_project()
    project.write("features/a.feature", 'Feature: F\n  Scenario: S\n    Given value "ok"\n')
    locations = project.write("locations.txt", "features/a.feature\n")
    plan = project.write("plan.json", json.dumps({
        "locations_file": str(locations), "behave_args": [],
        "cucumber_out": str(project.root / "result.json"), "allure_dir": None,
    }))
    data_file = tmp_path / "worker-coverage"
    # A fresh coverage process launches the worker; only the subprocess patch can measure it.
    launcher = project.write(
        "launch.py", "import subprocess, sys\nsubprocess.run(sys.argv[1:], check=True)\n"
    )
    result = subprocess.run(
        [
            sys.executable, "-m", "coverage", "run", "--rcfile", str(CONFIG), str(launcher),
            sys.executable, "-m", "behave_hive.worker",
            "--plan", str(plan),
        ],
        cwd=project.root, capture_output=True, text=True, check=False,
        env={**os.environ, "COVERAGE_FILE": str(data_file)},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    files = list(tmp_path.glob("worker-coverage*"))
    assert files
    measured = set()
    for path in files:
        data = CoverageData(basename=str(path))
        data.read()
        measured.update(data.measured_files())
    assert any(path.endswith("behave_hive/worker.py") for path in measured)
