"""Consolidation of the partial Cucumber results of every batch (D8)."""

from __future__ import annotations

import copy
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from behave_hive.errors import HiveError
from behave_hive.expand import RowSource
from behave_hive.privacy import scrub, user_home

EXTENSION = "x-behave-hive"


@dataclass
class Report:
    """Merged features; scenarios still carry the internal `x-behave-hive` extension."""

    features: list[dict]


def _absolute(text: str, cwd: Path) -> Path:
    path = Path(text)
    return path if path.is_absolute() else cwd / path


def _scrub_hooks_and_steps(element: dict, cwd: Path) -> None:
    home = user_home()
    for item in (*element.get("steps", []), *element.get("before", []), *element.get("after", [])):
        result = item.get("result", {})
        if "error_message" in result:
            result["error_message"] = scrub(result["error_message"], cwd, home)


def pair_backgrounds(elements: list[dict]) -> list[tuple[dict | None, dict]]:
    """(background or None, scenario): a background is the element right before a scenario."""
    pairs = []
    pending = None
    for element in elements:
        if element["type"] == "background":
            pending = element
        else:
            pairs.append((pending, element))
            pending = None
    return pairs


def _attach_source(scenario: dict, source: RowSource, cwd: Path) -> None:
    data_path = source.data_path
    with suppress(ValueError):
        data_path = data_path.relative_to(cwd)
    scenario.setdefault(EXTENSION, {})["source"] = {"data_path": data_path.as_posix(), "data_row": source.data_row}


def _annotate_feature(
    feature: dict, sources: dict[Path, list[RowSource]], cwd: Path
) -> list[tuple[dict | None, dict]]:
    """Scrub `feature` in place and attach the data-file source of its rows; return its background/scenario pairs."""
    row_sources = {s.expanded_line: s for s in sources.get(_absolute(feature["uri"], cwd), [])}
    pairs = pair_backgrounds(feature["elements"])
    for background, scenario in pairs:
        for element in (background, scenario):
            if element is not None:
                _scrub_hooks_and_steps(element, cwd)
        source = row_sources.get(scenario["line"])
        if source is not None:
            _attach_source(scenario, source, cwd)
    return pairs


def _order_elements(pairs: list[tuple[dict | None, dict]]) -> list[dict]:
    """Scenarios in line order, each preceded by its background."""
    ordered = sorted(pairs, key=lambda pair: pair[1]["line"])
    return [e for background, scenario in ordered for e in (background, scenario) if e is not None]


def merge(
    partials: list[list[dict]],
    sources: dict[Path, list[RowSource]],
    cwd: Path | None = None,
) -> Report:
    """Merge the partial results, in batch order, into one report."""
    cwd = Path(cwd) if cwd is not None else Path.cwd()
    by_uri: dict[str, dict] = {}
    pairs_by_uri: dict[str, list[tuple[dict | None, dict]]] = {}

    for partial in partials:
        for feature in copy.deepcopy(partial):
            pairs = _annotate_feature(feature, sources, cwd)
            by_uri.setdefault(feature["uri"], feature)
            pairs_by_uri.setdefault(feature["uri"], []).extend(pairs)

    features = []
    for uri in sorted(by_uri):
        by_uri[uri]["elements"] = _order_elements(pairs_by_uri[uri])
        features.append(by_uri[uri])

    _check_unique(features)
    return Report(features)


def _check_unique(features: list[dict]) -> None:
    seen: set[str] = set()
    for feature in features:
        ids = [feature["id"], *(e["id"] for e in feature["elements"] if e["type"] == "scenario")]
        for item in ids:
            if item in seen:
                raise HiveError(f"duplicate id in the consolidated report (this is a bug): {item}")
            seen.add(item)


def to_cucumber(report: Report) -> list[dict]:
    """The report as plain Cucumber JSON, without the internal extension."""
    features = copy.deepcopy(report.features)
    for feature in features:
        for element in feature["elements"]:
            element.pop(EXTENSION, None)
    return features
