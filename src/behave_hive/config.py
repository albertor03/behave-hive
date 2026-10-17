"""behave-hive configuration: `[behave_hive]` section, CLI overrides and validation (D9)."""

from __future__ import annotations

import configparser
import os
import re
import shlex
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from behave_hive.errors import ConfigError

SECTION = "behave_hive"
INI_FILES = ("behave.ini", ".behaverc", "setup.cfg", "tox.ini")
PYPROJECT = "pyproject.toml"
TRUE_VALUES = {"true", "yes", "on", "1"}
FALSE_VALUES = {"false", "no", "off", "0"}


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
        values[key] = raw if key in ("parallel", "workers", "chunk") else CONVERTERS[key](key, raw)
    values["behave_args"] = (*values["behave_args"], *extra_args)
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
    )
