"""Consolidation of the partial Cucumber results of every batch (D8)."""

from __future__ import annotations

import copy
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from behave_hive.errors import HiveError
from behave_hive.expand import RowSource
from behave_hive.formatters.cucumber import feature_id
from behave_hive.privacy import scrub, user_home
from behave_hive.roots import PathMap

EXTENSION = "x-behave-hive"


@dataclass
class Report:
    """Merged features; scenarios still carry the internal `x-behave-hive` extension."""

    features: list[dict]


def _absolute(text: str, cwd: Path) -> Path:
    path = Path(text)
    return path if path.is_absolute() else cwd / path


def _to_original(text: str, path_map: PathMap, cwd: Path) -> str:
    """Rewrite `text` (a path) from the expanded tree to the original one, relative to `cwd`."""
    absolute = _absolute(text, cwd)
    mapped = path_map.to_original(absolute)
    if mapped == absolute:
        return text
    try:
        return mapped.relative_to(cwd).as_posix()
    except ValueError:
        return mapped.as_posix()


def _rewrite_location(location: str, path_map: PathMap, cwd: Path) -> str:
    path, sep, line = location.rpartition(":")
    if not sep or not line.isdigit():
        return location
    return f"{_to_original(path, path_map, cwd)}:{line}"


def _rewrite_hooks_and_steps(element: dict, path_map: PathMap, cwd: Path) -> None:
    home = user_home()
    for item in (*element.get("steps", []), *element.get("before", []), *element.get("after", [])):
        match = item.get("match")
        if match and "location" in match:
            match["location"] = _rewrite_location(match["location"], path_map, cwd)
        result = item.get("result", {})
        if "error_message" in result:
            result["error_message"] = scrub(result["error_message"], path_map, cwd, home)


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


def _attach_source(scenario: dict, source: RowSource, path_map: PathMap, cwd: Path) -> None:
    data_path = _to_original(str(source.data_path), path_map, cwd)
    with suppress(ValueError):
        data_path = Path(data_path).relative_to(cwd).as_posix()
    scenario.setdefault(EXTENSION, {})["source"] = {"data_path": data_path, "data_row": source.data_row}


def _rewrite_feature(
    feature: dict, path_map: PathMap, sources: dict[Path, list[RowSource]], cwd: Path
) -> list[tuple[dict | None, dict]]:
    """Rewrite `feature` in place to its original uri and ids; return its background/scenario pairs."""
    row_sources = {s.expanded_line: s for s in sources.get(_absolute(feature["uri"], cwd), [])}
    uri = _to_original(feature["uri"], path_map, cwd)
    old_id, new_id = feature["id"], feature_id(uri)
    pairs = pair_backgrounds(feature["elements"])
    for background, scenario in pairs:
        for element in (background, scenario):
            if element is not None:
                _rewrite_hooks_and_steps(element, path_map, cwd)
        if scenario["id"].startswith(old_id):
            scenario["id"] = new_id + scenario["id"][len(old_id):]
        source = row_sources.get(scenario["line"])
        if source is not None:
            _attach_source(scenario, source, path_map, cwd)
    feature["uri"], feature["id"] = uri, new_id
    return pairs


def _order_elements(pairs: list[tuple[dict | None, dict]]) -> list[dict]:
    """Scenarios in line order, each preceded by its background."""
    ordered = sorted(pairs, key=lambda pair: pair[1]["line"])
    return [e for background, scenario in ordered for e in (background, scenario) if e is not None]


def merge(
    partials: list[list[dict]],
    path_map: PathMap,
    sources: dict[Path, list[RowSource]],
    cwd: Path | None = None,
) -> Report:
    """Merge the partial results, in batch order, into one report with original paths."""
    cwd = Path(cwd) if cwd is not None else Path.cwd()
    by_uri: dict[str, dict] = {}
    pairs_by_uri: dict[str, list[tuple[dict | None, dict]]] = {}

    for partial in partials:
        for feature in copy.deepcopy(partial):
            pairs = _rewrite_feature(feature, path_map, sources, cwd)
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
