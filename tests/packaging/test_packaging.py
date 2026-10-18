"""Builds the wheel and sdist and installs the wheel in clean venvs with pip and uv (D12)."""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.packaging

ROOT = Path(__file__).resolve().parents[2]

FEATURE = """\
Feature: Packaging
  Scenario Outline: Value
    Given value "<v>"

    Examples:
      | data.csv |
"""


def run(*command, cwd=None):
    result = subprocess.run([str(c) for c in command], cwd=cwd, capture_output=True, text=True, timeout=600)
    assert result.returncode == 0, f"{command}\n{result.stdout}\n{result.stderr}"
    return result


@pytest.fixture(scope="session")
def dist(tmp_path_factory):
    out = tmp_path_factory.mktemp("dist")
    run(sys.executable, "-m", "build", "--outdir", out, ROOT)
    return out


@pytest.fixture
def wheel(dist):
    (path,) = dist.glob("behave_hive-*.whl")
    return path


@pytest.fixture
def features(tmp_path):
    root = tmp_path / "features"
    (root / "steps").mkdir(parents=True)
    (root / "a.feature").write_text(FEATURE)
    (root / "data.csv").write_text("v\n1\n2\n")
    return root


def venv_executable(venv: Path, name: str) -> Path:
    return venv / "bin" / name


def project_version() -> str:
    import tomllib

    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


def check_installed(venv: Path, features: Path, tmp_path: Path) -> None:
    exe = venv_executable(venv, "behave-hive")
    assert run(exe, "--version").stdout.strip() == f"behave-hive {project_version()}"
    out = tmp_path / "expanded"
    run(exe, "expand", features, out)
    assert "| v |\n      | 1 |\n      | 2 |" in (out / "a.feature").read_text()


def test_build_produces_a_wheel_and_an_sdist(dist):
    assert len(list(dist.glob("behave_hive-*.whl"))) == 1
    assert len(list(dist.glob("behave_hive-*.tar.gz"))) == 1


def test_pip_installs_the_wheel_in_a_clean_venv(wheel, features, tmp_path):
    venv = tmp_path / "venv-pip"
    run(sys.executable, "-m", "venv", venv)
    run(venv_executable(venv, "pip"), "install", wheel)
    check_installed(venv, features, tmp_path)


def test_uv_installs_the_wheel_in_a_clean_venv(wheel, features, tmp_path):
    uv = shutil.which("uv")
    if uv is None:
        pytest.fail("uv is required for this test: install it with `brew install uv`")
    venv = tmp_path / "venv-uv"
    run(uv, "venv", venv)
    run(uv, "pip", "install", "--python", venv_executable(venv, "python"), wheel)
    check_installed(venv, features, tmp_path)


def test_extra_allure_installs_allure_behave_2_16_2(wheel, tmp_path):
    venv = tmp_path / "venv-extra"
    run(sys.executable, "-m", "venv", venv)
    run(venv_executable(venv, "pip"), "install", f"{wheel}[allure]")
    shown = run(venv_executable(venv, "pip"), "show", "allure-behave").stdout
    assert "Version: 2.16.2" in shown


def test_wheel_metadata_has_the_readme_the_urls_and_the_classifiers(wheel):
    import zipfile

    with zipfile.ZipFile(wheel) as zf:
        (name,) = [n for n in zf.namelist() if n.endswith(".dist-info/METADATA")]
        metadata = zf.read(name).decode("utf-8")
    assert "Project-URL: Homepage, https://github.com/albertor03/behave-hive" in metadata
    assert "Project-URL: Issues, https://github.com/albertor03/behave-hive/issues" in metadata
    assert "Author: Alberto Zapata" in metadata
    assert "License-Expression: MIT" in metadata
    assert "Classifier: Programming Language :: Python :: 3.14" in metadata
    assert "# behave-hive" in metadata and "Examples from CSV" in metadata
    assert "Requires-Dist: behave<1.4,>=1.3" in metadata


def test_wheel_contains_the_html_report_template(wheel):
    import zipfile

    with zipfile.ZipFile(wheel) as zf:
        assert "behave_hive/templates/report.html" in zf.namelist()
