"""behave-hive configuration: `[behave_hive]` section, CLI overrides and validation (D9)."""

from __future__ import annotations

import configparser
import importlib.util
import os
import re
import shlex
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from behave.configuration import (
    Configuration,
    config_filenames,
    load_configuration,
    read_configuration,
    setup_parser,
)

from behave_hive.errors import ConfigError

SECTION = "behave_hive"
INI_FILES = ("behave.ini", ".behaverc", "setup.cfg", "tox.ini")
PYPROJECT = "pyproject.toml"
TRUE_VALUES = {"true", "yes", "on", "1"}
FALSE_VALUES = {"false", "no", "off", "0"}
SCHEMES = ("scenario", "feature")
FORMATS = ("allure", "cucumber", "html")

# Options controlled by behave-hive, with the alternative to suggest.
RESERVED_OPTIONS = {
    "-f": "use `formats`",
    "--format": "use `formats`",
    "-o": "reports go to `results_dir`",
    "--outfile": "reports go to `results_dir`",
    "-r": "the runner is controlled by behave-hive",
    "--runner": "the runner is controlled by behave-hive",
    "--junit": "use `formats` (JUnit is not supported)",
    "--junit-directory": "use `formats` (JUnit is not supported)",
}
UNSUPPORTED_OPTIONS = ("-d", "--dry-run", "--stop", "-i", "--include", "-e", "--exclude",
                       "-n", "--name", "-w", "--wip")


@dataclass(frozen=True)
class HiveConfig:
    parallel: bool
    workers: int
    scheme: str
    chunk: int
    results_dir: Path
    formats: tuple[str, ...]
    work_dir: Path
    behave_args: tuple[str, ...]
    paths: tuple[str, ...]
    config_file: Path | None
    report_name: str | None = None
    report_path: Path | None = None


def _to_bool(key: str, value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in TRUE_VALUES:
            return True
        if lowered in FALSE_VALUES:
            return False
    raise ConfigError(f"invalid value for '{key}': {value!r} is not a boolean")


def _to_int(key: str, value: Any) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str) and re.fullmatch(r"[+-]?\d+", value.strip()):
        return int(value.strip())
    raise ConfigError(f"invalid value for '{key}': {value!r} is not an integer")


def _to_list(key: str, value: Any) -> tuple[str, ...]:
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return tuple(value)
    if isinstance(value, str):
        return tuple(v for v in re.split(r"[,\s]+", value.strip()) if v)
    raise ConfigError(f"invalid value for '{key}': {value!r} is not a list")


def _to_args(key: str, value: Any) -> tuple[str, ...]:
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return tuple(value)
    if isinstance(value, str):
        try:
            return tuple(shlex.split(value))
        except ValueError as exc:
            raise ConfigError(f"invalid value for '{key}': {value!r} ({exc})") from None
    raise ConfigError(f"invalid value for '{key}': {value!r} is not a list of arguments")


def _to_path(key: str, value: Any) -> Path:
    if isinstance(value, str) and value.strip():
        return Path(value.strip())
    raise ConfigError(f"invalid value for '{key}': {value!r} is not a path")


def _to_str(key: str, value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    raise ConfigError(f"invalid value for '{key}': {value!r} is not a string")


CONVERTERS = {
    "parallel": _to_bool,
    "workers": _to_int,
    "scheme": _to_str,
    "chunk": _to_int,
    "results_dir": _to_path,
    "formats": _to_list,
    "work_dir": _to_path,
    "behave_args": _to_args,
    "paths": _to_list,
    "report_name": _to_str,
    "report_path": _to_path,
}


def _defaults() -> dict[str, Any]:
    return {
        "parallel": False,
        "workers": os.cpu_count() or 1,
        "scheme": "scenario",
        "chunk": 0,
        "results_dir": Path("reports"),
        "formats": ("cucumber", "html"),
        "work_dir": Path(".behave-hive"),
        "behave_args": (),
        "paths": ("features",),
        "report_name": None,
        "report_path": None,
    }


def _read_section(path: Path) -> dict[str, Any] | None:
    """The `[behave_hive]` section of `path`, or None if the file lacks it."""
    if path.suffix == ".toml":
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"cannot parse {path}: {exc}") from None
        return data.get("tool", {}).get(SECTION)
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(path, encoding="utf-8")
    except configparser.Error as exc:
        raise ConfigError(f"cannot parse {path}: {exc}") from None
    return dict(parser[SECTION]) if parser.has_section(SECTION) else None


def _find_section(config_path: Path | None) -> tuple[Path | None, dict[str, Any]]:
    if config_path is not None:
        config_path = Path(config_path)
        if not config_path.is_file():
            raise ConfigError(f"configuration file not found: {config_path}")
        section = _read_section(config_path)
        if section is None:
            raise ConfigError(f"{config_path} has no [{SECTION}] section")
        return config_path, section
    for name in (*INI_FILES, PYPROJECT):
        candidate = Path(name)
        if candidate.is_file():
            section = _read_section(candidate)
            if section is not None:
                return candidate, section
    return None, {}


def load_config(cli: dict[str, Any], config_path: Path | None, extra_args: list[str]) -> HiveConfig:
    """Resolve the configuration: default < file < CLI; `extra_args` follow `behave_args`."""
    found, section = _find_section(config_path)
    values = _defaults()
    for key, raw in section.items():
        if key not in CONVERTERS:
            raise ConfigError(f"unknown key '{key}' in [{SECTION}] of {found}")
        values[key] = CONVERTERS[key](key, raw)
    for key, raw in cli.items():
        if raw is None:
            continue
        values[key] = CONVERTERS[key](key, raw) if isinstance(raw, str) else raw
    values["behave_args"] = (*values["behave_args"], *extra_args)
    _validate(values)
    root = found.resolve().parent if found is not None else Path.cwd()
    report_name = values["report_name"] or _project_name(root)
    report_path = (root / (values["report_path"] or "report.html")).resolve()
    if report_path.is_dir():
        raise ConfigError(f"invalid report_path: {report_path} is a directory (use an HTML filename)")
    return HiveConfig(
        parallel=values["parallel"],
        workers=values["workers"],
        scheme=values["scheme"],
        chunk=values["chunk"],
        results_dir=values["results_dir"],
        formats=tuple(values["formats"]),
        work_dir=values["work_dir"],
        behave_args=tuple(values["behave_args"]),
        paths=tuple(values["paths"]),
        config_file=found,
        report_name=report_name,
        report_path=report_path,
    )


def _project_name(root: Path) -> str:
    metadata = root / PYPROJECT
    if metadata.is_file():
        try:
            data = tomllib.loads(metadata.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise ConfigError(f"cannot read project name from {metadata}: {exc}") from None
        project = data.get("project")
        name = project.get("name") if isinstance(project, dict) else None
        if isinstance(name, str) and name.strip():
            return name.strip()
    return root.name or "behave-hive"


def _options_taking_a_value() -> set[str]:
    """Option strings of behave's parser that consume the following argument."""
    taking = set()
    for action in setup_parser()._actions:
        if action.option_strings and action.nargs is None:
            taking.update(action.option_strings)
    return taking


def _reject_option(token: str, option: str) -> ConfigError:
    if option in RESERVED_OPTIONS:
        return ConfigError(f"behave argument '{token}' ({option}) is not allowed: {RESERVED_OPTIONS[option]}")
    return ConfigError(f"behave argument '{token}' ({option}) is not supported by behave-hive")


def validate_behave_args(args: list[str] | tuple[str, ...]) -> None:
    """Reject the behave arguments that behave-hive controls or does not support (D4)."""
    with_value = _options_taking_a_value()
    reserved = set(RESERVED_OPTIONS) | set(UNSUPPORTED_OPTIONS)
    tokens = iter(args)
    for token in tokens:
        if token.startswith("--"):
            option, has_value = token.split("=", 1)[0], "=" in token
        elif token.startswith("-") and len(token) > 1:
            option, has_value = token[:2], len(token) > 2
        else:
            what = "@file" if token.startswith("@") else "positional argument"
            raise ConfigError(f"{what} '{token}' is not allowed in behave arguments: paths go before `--`")
        if option in reserved:
            raise _reject_option(token, option)
        if option in with_value and not has_value:
            next(tokens, None)


def _validate(values: dict[str, Any]) -> None:
    if values["workers"] < 1:
        raise ConfigError(f"invalid value for 'workers': {values['workers']} (must be >= 1)")
    if values["chunk"] < 0:
        raise ConfigError(f"invalid value for 'chunk': {values['chunk']} (must be >= 0)")
    if values["scheme"] not in SCHEMES:
        raise ConfigError(f"invalid value for 'scheme': {values['scheme']!r} (use one of {', '.join(SCHEMES)})")
    for fmt in values["formats"]:
        if fmt not in FORMATS:
            raise ConfigError(f"invalid value for 'formats': {fmt!r} (use {', '.join(FORMATS)})")
    if "allure" in values["formats"] and importlib.util.find_spec("allure_behave") is None:
        raise ConfigError('format \'allure\' needs allure-behave: pip install "behave-hive[allure]"')
    validate_behave_args(values["behave_args"])


# (config attribute, key reported to the user, option strings) in the order they are checked.
# `wip` goes before `stop` and `steps_catalog` before `dry_run`: behave turns `--wip` into a
# stop and `--steps-catalog` into a dry run, and the user's option must be the one reported.
INCOMPATIBLE = (
    ("wip", "wip", ("-w", "--wip")),
    ("stop", "stop", ("--stop",)),
    ("steps_catalog", "steps_catalog", ("--steps-catalog",)),
    ("dry_run", "dry_run", ("-d", "--dry-run")),
    ("junit", "junit", ("--junit",)),
    ("name", "name", ("-n", "--name")),
    ("include_re", "include_re", ("-i", "--include")),
    ("exclude_re", "exclude_re", ("-e", "--exclude")),
    ("stage", "stage", ("--stage",)),
)
DEFAULT_RUNNER = "behave.runner:Runner"
INFORMATIONAL = (
    ("version", "--version"),
    ("tags_help", "--tags-help"),
    ("lang_list", "--lang-list"),
    ("lang_help", "--lang-help"),
)


def build_behave_config(args: list[str]) -> Configuration:
    """behave's configuration for `args`, without validating or adding user formatters (D3/D4)."""
    defaults: dict[str, Any] = {}
    load_configuration(defaults)
    defaults.pop("format", None)
    defaults.pop("outfiles", None)
    return Configuration(args, load_config=False, **defaults)


def _file_origins() -> dict[str, str]:
    """Which behave configuration file sets each key (the last one read wins)."""
    origins: dict[str, str] = {}
    for filename in config_filenames():
        for key in read_configuration(filename):
            origins[key] = os.path.normpath(filename)
    return origins


def _in_args(args: list[str], options: tuple[str, ...]) -> bool:
    return any(
        token == option or token.startswith(option + "=") or (not option.startswith("--") and token.startswith(option))
        for token in args
        for option in options
    )


def validate_effective(cfg: Configuration, args: list[str] | tuple[str, ...] = ()) -> None:
    """Reject behave settings that change what runs or end behave early (D4)."""
    args = list(args)
    origins = _file_origins()

    def origin(attribute: str, options: tuple[str, ...]) -> str:
        return "argument" if _in_args(args, options) else origins.get(attribute, "the behave configuration")

    for attribute, key, options in INCOMPATIBLE:
        if getattr(cfg, attribute, None):
            raise ConfigError(
                f"behave option '{key}' is not supported by behave-hive (set in {origin(attribute, options)})"
            )
    if cfg.runner != DEFAULT_RUNNER:
        raise ConfigError(
            f"behave option 'runner' is not supported by behave-hive (set in {origin('runner', ('-r', '--runner'))})"
        )
    for attribute, option in INFORMATIONAL:
        if getattr(cfg, attribute, None):
            raise ConfigError(f"informational option '{option}' ends behave without running scenarios")
    if cfg.lang == "help":
        raise ConfigError("informational option '--lang help' ends behave without running scenarios")
