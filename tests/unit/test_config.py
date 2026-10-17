import os
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from behave_hive.config import HiveConfig, build_behave_config, load_config, validate_behave_args, validate_effective
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
    with pytest.raises(FrozenInstanceError):
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
    with pytest.raises(ConfigError, match=r"nope\.ini"):
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


# --- 3.5 reserved behave arguments ----------------------------------------------

@pytest.mark.parametrize(
    "args, named",
    [
        (["features/other.feature"], "features/other.feature"),
        (["-t", "@a", "features"], "features"),
        (["@list.txt"], "@list.txt"),
        (["-f", "pretty"], "-f"),
        (["-fpretty"], "-f"),
        (["--format=pretty"], "--format"),
        (["--format", "pretty"], "--format"),
        (["-o", "out.txt"], "-o"),
        (["--outfile=out.txt"], "--outfile"),
        (["-r", "x:Y"], "-r"),
        (["--runner", "x:Y"], "--runner"),
        (["--junit"], "--junit"),
        (["--junit-directory", "d"], "--junit-directory"),
        (["--stop"], "--stop"),
        (["-d"], "-d"),
        (["--dry-run"], "--dry-run"),
        (["-i", "x"], "-i"),
        (["--include=x"], "--include"),
        (["-e", "x"], "-e"),
        (["--exclude", "x"], "--exclude"),
        (["-n", "x"], "-n"),
        (["--name=x"], "--name"),
        (["-w"], "-w"),
        (["--wip"], "--wip"),
    ],
)
def test_reserved_arguments_are_rejected_naming_the_option(args, named):
    with pytest.raises(ConfigError) as exc:
        validate_behave_args(args)
    assert named in str(exc.value)


def test_reserved_format_suggests_formats():
    with pytest.raises(ConfigError, match="formats"):
        validate_behave_args(["-f", "pretty"])


def test_reserved_positional_says_paths_go_before_double_dash():
    with pytest.raises(ConfigError, match="paths go before `--`"):
        validate_behave_args(["features/other.feature"])


@pytest.mark.parametrize(
    "args",
    [
        ["-t", "X"],
        ["-tX"],
        ["--tags=X"],
        ["--tags", "@a and not @b"],
        ["-D", "k=v"],
        ["-Dk=v"],
        ["--define", "k=v"],
        ["--lang", "es"],
        ["--no-capture"],
        ["--no-skipped"],
        ["--color", "-v"],
        [],
    ],
)
def test_reserved_allowed_arguments_are_accepted(args):
    validate_behave_args(args)


def test_reserved_arguments_from_the_file_and_after_double_dash_are_both_checked(project):
    (project / "behave.ini").write_text(ini(behave_args="-D a=1"))
    with pytest.raises(ConfigError, match="--stop"):
        load(extra=["--stop"])
    (project / "behave.ini").write_text(ini(behave_args="--stop"))
    with pytest.raises(ConfigError, match="--stop"):
        load()


# --- 3.6 value validation -------------------------------------------------------


@pytest.mark.parametrize(
    "key, value",
    [
        ("workers", "0"),
        ("workers", "-1"),
        ("chunk", "-1"),
        ("scheme", "batch"),
        ("formats", "cucumber, pdf"),
        ("workers", "many"),
        ("chunk", "1.5"),
        ("parallel", "maybe"),
        ("parallel", "2"),
    ],
)
def test_validation_rejects_invalid_values_naming_key_and_value(project, key, value):
    (project / "behave.ini").write_text(ini(**{key: value}))
    with pytest.raises(ConfigError) as exc:
        load()
    assert key in str(exc.value)
    assert value.split(",")[-1].strip() in str(exc.value)


def test_validation_toml_wrong_types(project):
    (project / "pyproject.toml").write_text('[tool.behave_hive]\nparallel = "maybe"\n')
    with pytest.raises(ConfigError, match="parallel"):
        load()


def test_validation_cli_values_are_validated_too(project):
    with pytest.raises(ConfigError, match="workers"):
        load(cli={"workers": 0})
    with pytest.raises(ConfigError, match="scheme"):
        load(cli={"scheme": "batch"})


@pytest.mark.parametrize("scheme", ["scenario", "feature"])
@pytest.mark.parametrize("formats", ["allure", "cucumber", "html", "allure cucumber html"])
def test_validation_accepts_valid_scheme_and_formats(project, scheme, formats, monkeypatch):
    import importlib.util

    monkeypatch.setattr(importlib.util, "find_spec", lambda name: object())
    (project / "behave.ini").write_text(ini(scheme=scheme, formats=formats))
    assert load().scheme == scheme


# --- 3.7 allure -----------------------------------------------------------------


def test_missing_allure_suggests_the_extra(project, monkeypatch):
    import importlib.util

    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    (project / "behave.ini").write_text(ini(formats="allure"))
    with pytest.raises(ConfigError) as exc:
        load()
    assert 'pip install "behave-hive[allure]"' in str(exc.value)


def test_missing_allure_is_irrelevant_without_the_allure_format(project, monkeypatch):
    import importlib.util

    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    (project / "behave.ini").write_text(ini(formats="cucumber"))
    assert load().formats == ("cucumber",)


# --- 3.8 effective behave configuration -----------------------------------------

def effective(args=(), ini_text=None, project=None):
    if ini_text is not None:
        (project / "behave.ini").write_text(ini_text)
    cfg = build_behave_config(list(args))
    validate_effective(cfg, list(args))
    return cfg


def test_effective_nonexistent_formatter_and_outfiles_are_ignored(project):
    cfg = effective(ini_text="[behave]\nformat = nonexistent_formatter\noutfiles = x.txt\n", project=project)
    assert not (project / "x.txt").exists()
    assert cfg.tag_expression is not None


def test_effective_plain_configuration_is_accepted(project):
    effective(ini_text="[behave]\nlang = es\ndefault_tags = not @wip\n", project=project)


@pytest.mark.parametrize(
    "key, value",
    [
        ("stop", "true"),
        ("dry_run", "true"),
        ("steps_catalog", "true"),
        ("junit", "true"),
        ("wip", "true"),
        ("name", "login"),
        ("include_re", "login"),
        ("exclude_re", "login"),
        ("stage", "staging"),
        ("runner", "my.module:Runner"),
    ],
)
def test_effective_incompatible_key_in_file_names_key_and_file(project, key, value):
    with pytest.raises(ConfigError) as exc:
        effective(ini_text=f"[behave]\n{key} = {value}\n", project=project)
    assert key in str(exc.value)
    assert "behave.ini" in str(exc.value)


@pytest.mark.parametrize(
    "args, key",
    [
        (["--steps-catalog"], "steps_catalog"),
        (["--junit"], "junit"),
        (["--stop"], "stop"),
        (["-d"], "dry_run"),
        (["-w"], "wip"),
        (["-n", "x"], "name"),
        (["--name=x"], "name"),
        (["-i", "x"], "include"),
        (["-e", "x"], "exclude"),
        (["--stage", "s"], "stage"),
        (["-r", "a:B"], "runner"),
    ],
)
def test_effective_incompatible_argument_names_key_and_origin(project, args, key):
    with pytest.raises(ConfigError) as exc:
        effective(args)
    assert key in str(exc.value)
    assert "argument" in str(exc.value)


@pytest.mark.parametrize(
    "args",
    [["--version"], ["--tags-help"], ["--lang-list"], ["--lang-help", "es"], ["--lang", "help"]],
)
def test_effective_informational_options_are_rejected(project, args):
    with pytest.raises(ConfigError, match="informational"):
        effective(args)


def test_effective_argument_beats_file_in_the_reported_origin(project):
    with pytest.raises(ConfigError) as exc:
        effective(["--stop"], ini_text="[behave]\nstop = true\n", project=project)
    assert "argument" in str(exc.value)


def test_effective_tags_argument_overrides_default_tags(project):
    cfg = effective(
        ["--tags=@expected_fail"], ini_text="[behave]\ndefault_tags = not @expected_fail\n", project=project
    )
    assert cfg.tag_expression.check(["expected_fail"]) is True


# --- 3.9 behave ignores [behave_hive] -------------------------------------------


def test_behave_ignores_hive_section(make_project):
    project = make_project()
    project.write("features/a.feature", "Feature: F\n  Scenario: S\n    Given value \"ok\"\n")
    project.write("behave.ini", "[behave]\nlang = en\n\n[behave_hive]\nparallel = true\nworkers = 4\n")
    result = project.run("behave", "features")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "warning" not in result.stderr.lower()
