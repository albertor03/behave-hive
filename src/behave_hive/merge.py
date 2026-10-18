"""Consolidation of the partial Cucumber results of every batch (D8)."""

from __future__ import annotations

import copy
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from behave_hive.errors import HiveError
from behave_hive.expand import RowSource
from behave_hive.formatters.cucumber import feature_id
from behave_hive.privacy import scrub
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
    for step in element.get("steps", []):
        match = step.get("match")
        if match and "location" in match:
            match["location"] = _rewrite_location(match["location"], path_map, cwd)
    for item in (*element.get("steps", []), *element.get("before", []), *element.get("after", [])):
        result = item.get("result", {})
        if "error_message" in result:
            result["error_message"] = scrub(result["error_message"], path_map, cwd, Path.home())
    for hook in (*element.get("before", []), *element.get("after", [])):
        match = hook.get("match")
        if match and "location" in match:
            match["location"] = _rewrite_location(match["location"], path_map, cwd)


def _pairs(elements: list[dict]) -> list[tuple[dict | None, dict]]:
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
            expanded = _absolute(feature["uri"], cwd)
            uri = _to_original(feature["uri"], path_map, cwd)
            old_id = feature["id"]
            new_id = feature_id(uri)
            row_sources = {s.expanded_line: s for s in sources.get(expanded, [])}
            pairs = _pairs(feature["elements"])
            for background, scenario in pairs:
                for element in (background, scenario):
                    if element is not None:
                        _rewrite_hooks_and_steps(element, path_map, cwd)
                if scenario["id"].startswith(old_id):
                    scenario["id"] = new_id + scenario["id"][len(old_id):]
                source = row_sources.get(scenario["line"])
                if source is not None:
                    csv_path = _to_original(str(source.csv_path), path_map, cwd)
                    with suppress(ValueError):
                        csv_path = Path(csv_path).relative_to(cwd).as_posix()
                    scenario.setdefault(EXTENSION, {})["source"] = {
                        "csv_path": csv_path,
                        "csv_row": source.csv_row,
                    }
            feature["uri"], feature["id"] = uri, new_id
            if uri not in by_uri:
                by_uri[uri] = feature
                pairs_by_uri[uri] = []
            pairs_by_uri[uri].extend(pairs)

    features = []
    for uri in sorted(by_uri):
        feature = by_uri[uri]
        ordered = sorted(pairs_by_uri[uri], key=lambda pair: pair[1]["line"])
        feature["elements"] = [e for background, scenario in ordered for e in (background, scenario) if e is not None]
        features.append(feature)

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
