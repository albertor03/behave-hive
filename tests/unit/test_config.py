import os
from pathlib import Path

import pytest

from behave_hive.config import HiveConfig, load_config
from behave_hive.errors import ConfigError


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def ini(section="behave_hive", **values):
    body = "\n".join(f"{k} = {v}" for k, v in values.items())
    return f"[{section}]\n{body}\n"


def load(cli=None, config_path=None, extra=None):
    return load_config(cli or {}, config_path, extra or [])


# --- 3.1 defaults ---------------------------------------------------------------


def test_defaults_without_any_file(project):
    cfg = load()
    assert cfg == HiveConfig(
        parallel=False,
        workers=os.cpu_count() or 1,
        scheme="scenario",
        chunk=0,
        results_dir=Path("reports"),
        formats=("cucumber", "html"),
        work_dir=Path(".behave-hive"),
        behave_args=(),
        paths=("features",),
        config_file=None,
    )


def test_defaults_config_is_immutable(project):
    with pytest.raises(Exception):
        load().parallel = True


# --- 3.2 lookup -----------------------------------------------------------------


def test_lookup_section_in_behave_ini(project):
    (project / "behave.ini").write_text(ini(parallel="true", workers="4"))
    cfg = load()
    assert (cfg.parallel, cfg.workers) == (True, 4)
    assert cfg.config_file == Path("behave.ini")


@pytest.mark.parametrize("name", ["behave.ini", ".behaverc", "setup.cfg", "tox.ini"])
def test_lookup_each_ini_file(project, name):
    (project / name).write_text(ini(workers="2"))
    assert load().workers == 2


def test_lookup_first_file_with_the_section_wins(project):
    (project / "behave.ini").write_text("[behave]\nlang = en\n")
    (project / "setup.cfg").write_text(ini(workers="2"))
    (project / "tox.ini").write_text(ini(workers="9"))
    cfg = load()
    assert cfg.workers == 2
    assert cfg.config_file == Path("setup.cfg")


def test_lookup_pyproject_toml(project):
    (project / "pyproject.toml").write_text("[tool.behave_hive]\nparallel = true\nworkers = 3\n")
    cfg = load()
    assert (cfg.parallel, cfg.workers) == (True, 3)


def test_lookup_pyproject_without_the_table_is_skipped(project):
    (project / "pyproject.toml").write_text("[tool.other]\nx = 1\n")
    assert load().config_file is None


def test_lookup_explicit_config_forces_that_file(project):
    (project / "behave.ini").write_text(ini(workers="4"))
    (project / "other.ini").write_text(ini(workers="7"))
    cfg = load(config_path=project / "other.ini")
    assert cfg.workers == 7


def test_lookup_explicit_config_without_section_fails(project):
    (project / "other.ini").write_text("[behave]\nlang = en\n")
    with pytest.raises(ConfigError, match="behave_hive"):
        load(config_path=project / "other.ini")


def test_lookup_explicit_config_missing_file_fails(project):
    with pytest.raises(ConfigError, match="nope.ini"):
        load(config_path=project / "nope.ini")


def test_lookup_explicit_toml_file(project):
    (project / "x.toml").write_text("[tool.behave_hive]\nchunk = 5\n")
    assert load(config_path=project / "x.toml").chunk == 5


def test_lookup_unknown_key_names_the_key(project):
    (project / "behave.ini").write_text(ini(worker="4"))
    with pytest.raises(ConfigError, match="worker"):
        load()


# --- 3.3 values -----------------------------------------------------------------


@pytest.mark.parametrize("text", ["true", "True", "YES", "on", "1"])
def test_values_boolean_true_as_text(project, text):
    (project / "behave.ini").write_text(ini(parallel=text))
    assert load().parallel is True


@pytest.mark.parametrize("text", ["false", "No", "OFF", "0"])
def test_values_boolean_false_as_text(project, text):
    (project / "behave.ini").write_text(ini(parallel=text))
    assert load().parallel is False


def test_values_toml_types(project):
    (project / "pyproject.toml").write_text(
        "[tool.behave_hive]\nparallel = true\nworkers = 3\nchunk = 2\n"
        'formats = ["cucumber", "html"]\npaths = ["a", "b"]\nbehave_args = ["-t", "@x y"]\n'
    )
    cfg = load()
    assert (cfg.parallel, cfg.workers, cfg.chunk) == (True, 3, 2)
    assert cfg.formats == ("cucumber", "html")
    assert cfg.paths == ("a", "b")
    assert cfg.behave_args == ("-t", "@x y")


@pytest.mark.parametrize("text", ["cucumber,html", "cucumber html", "cucumber, html"])
def test_values_lists_split_on_commas_or_spaces(project, text):
    (project / "behave.ini").write_text(ini(formats=text))
    assert load().formats == ("cucumber", "html")


def test_values_paths_split_on_commas_or_spaces(project):
    (project / "behave.ini").write_text(ini(paths="features/a, features/b"))
    assert load().paths == ("features/a", "features/b")


def test_values_behave_args_split_with_shell_rules(project):
    (project / "behave.ini").write_text(ini(behave_args='--tags="@smoke and not @wip" -D env=qa'))
    assert load().behave_args == ("--tags=@smoke and not @wip", "-D", "env=qa")


def test_values_percent_sign_is_literal(project):
    (project / "behave.ini").write_text(ini(behave_args="-D pct=50%"))
    assert load().behave_args == ("-D", "pct=50%")


def test_values_results_and_work_dir_are_paths(project):
    (project / "behave.ini").write_text(ini(results_dir="out/r", work_dir=".hive"))
    cfg = load()
    assert (cfg.results_dir, cfg.work_dir) == (Path("out/r"), Path(".hive"))


# --- 3.4 precedence -------------------------------------------------------------


def test_precedence_cli_overrides_file(project):
    (project / "behave.ini").write_text(ini(parallel="false", workers="4"))
    cfg = load(cli={"parallel": True, "workers": 2})
    assert (cfg.parallel, cfg.workers) == (True, 2)


def test_precedence_cli_no_parallel_overrides_file_parallel(project):
    (project / "behave.ini").write_text(ini(parallel="true"))
    assert load(cli={"parallel": False}).parallel is False


def test_precedence_unset_cli_values_do_not_override_file(project):
    (project / "behave.ini").write_text(ini(parallel="true", workers="4"))
    cfg = load(cli={"parallel": None, "workers": None, "scheme": None})
    assert (cfg.parallel, cfg.workers, cfg.scheme) == (True, 4, "scenario")


def test_precedence_file_overrides_default(project):
    (project / "behave.ini").write_text(ini(scheme="feature", chunk="3"))
    cfg = load()
    assert (cfg.scheme, cfg.chunk) == ("feature", 3)


def test_precedence_cli_paths_override_file_paths(project):
    (project / "behave.ini").write_text(ini(paths="features"))
    assert load(cli={"paths": ["x", "y"]}).paths == ("x", "y")


def test_precedence_extra_args_are_appended_after_behave_args(project):
    (project / "behave.ini").write_text(ini(behave_args="-D a=1"))
    assert load(extra=["-D", "b=2"]).behave_args == ("-D", "a=1", "-D", "b=2")
