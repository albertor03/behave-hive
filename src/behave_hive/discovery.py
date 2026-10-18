"""Discovery of the units (`file:line` or whole features) to distribute (D4)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from behave.parser import ParserError, parse_file

from behave_hive.config import build_behave_config, validate_effective
from behave_hive.errors import ConfigError, HiveError
from behave_hive.roots import feature_files

SETUP_TAGS = ("setup", "teardown")


@dataclass(frozen=True)
class Unit:
    """A scenario (`line` set) or a whole feature (`line` is None)."""

    path: Path
    line: int | None = None

    @property
    def sort_key(self) -> tuple[str, int]:
        return str(self.path), self.line or 0


def discover_units(inputs: list[Path], behave_args: list[str], *, scheme: str, parallel: bool) -> list[Unit]:
    """Units of the features under `inputs` that match the effective tag expression.

    Uses the same effective configuration the behave workers build (D3/D4).
    """
    config = build_behave_config(behave_args)
    validate_effective(config, behave_args)
    per_scenario = parallel and scheme == "scenario"

    units: list[Unit] = []
    for path in feature_files(inputs):
        try:
            feature = parse_file(str(path), language=config.lang)
        except ParserError as exc:
            raise HiveError(f"cannot parse {path}: {exc}") from None
        scenarios = list(feature.walk_scenarios())
        selected = [s for s in scenarios if s.should_run_with_tags(config.tag_expression)]
        if not selected:
            continue
        if per_scenario:
            for scenario in scenarios:
                if any(tag in SETUP_TAGS for tag in scenario.effective_tags):
                    raise ConfigError(
                        f"{path} has @setup/@teardown scenarios, which behave runs even when they are "
                        "not selected: use scheme = feature or sequential mode"
                    )
            units.extend(Unit(path, s.line) for s in selected)
        else:
            units.append(Unit(path, None))
    return sorted(units, key=lambda u: u.sort_key)
