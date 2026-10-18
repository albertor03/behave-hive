"""Parse `.feature` files with their CSV and JSON Examples expanded in memory (D1)."""

from __future__ import annotations

from pathlib import Path

import behave.parser
from behave.model import Feature

from behave_hive.expand import RowSource, expand_feature_text


def parse_expanded(filename: str, language: str | None = None) -> Feature:
    """Like `behave.parser.parse_file`, but the data-file tables are replaced by their rows first.

    The feature keeps the original `filename`; its line numbers are those of the expanded text.
    """
    path = Path(filename)
    text = path.read_bytes().decode("utf8")
    expanded = expand_feature_text(text, path, language or "en")
    return behave.parser.parse_feature(expanded.text, language, filename)


def install() -> None:
    """Make behave parse every feature through `parse_expanded` (it calls `gherkin.parse_file`)."""
    behave.parser.parse_file = parse_expanded


def row_sources(features: list[Path], lang: str) -> dict[Path, list[RowSource]]:
    """The data-file row behind each generated line of every feature that has data tables."""
    found = {}
    for feature in features:
        expanded = expand_feature_text(feature.read_bytes().decode("utf8"), feature, lang)
        if expanded.sources:
            found[feature] = expanded.sources
    return found
