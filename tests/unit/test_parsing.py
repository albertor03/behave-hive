import inspect
from pathlib import Path

import behave.parser
import behave.runner_util
import pytest

from behave_hive import parsing
from behave_hive.errors import ExamplesDataError

OUTLINE = (
    "Feature: F\n"
    "  Scenario Outline: S\n"
    '    Given value "<v>"\n'
    "\n"
    "    Examples:\n"
    "      | {ref} |\n"
)


def write(tmp_path, ref="data.csv", name="a.feature"):
    path = tmp_path / name
    path.write_text(OUTLINE.format(ref=ref), encoding="utf-8")
    return path


def test_parse_expanded_reads_the_rows_of_a_csv_in_memory(tmp_path):
    (tmp_path / "data.csv").write_text("v\none\ntwo\n", encoding="utf-8")
    path = write(tmp_path)
    feature = parsing.parse_expanded(str(path))
    assert [s.name for s in feature.walk_scenarios()] == ["S -- @1.1 ", "S -- @1.2 "]
    assert Path(feature.filename).resolve() == path.resolve()
    assert path.read_text(encoding="utf-8") == OUTLINE.format(ref="data.csv")


def test_parse_expanded_reads_the_rows_of_a_json(tmp_path):
    (tmp_path / "data.json").write_text('[{"v": "one"}, {"v": "two"}, {"v": "three"}]', encoding="utf-8")
    feature = parsing.parse_expanded(str(write(tmp_path, "data.json")))
    assert len(list(feature.walk_scenarios())) == 3


def test_parse_expanded_keeps_a_feature_without_data_tables(tmp_path):
    path = tmp_path / "plain.feature"
    path.write_text(OUTLINE.format(ref="v").replace("| v |", "| v |\n      | x |"), encoding="utf-8")
    feature = parsing.parse_expanded(str(path), language="en")
    assert len(list(feature.walk_scenarios())) == 1


def test_parse_expanded_uses_the_language_of_the_feature(tmp_path):
    (tmp_path / "data.csv").write_text("v\none\n", encoding="utf-8")
    path = tmp_path / "es.feature"
    path.write_text(
        "# language: es\nCaracterística: F\n  Esquema del escenario: S\n    Dado value \"<v>\"\n\n"
        "    Ejemplos:\n      | data.csv |\n",
        encoding="utf-8",
    )
    assert len(list(parsing.parse_expanded(str(path)).walk_scenarios())) == 1


def test_parse_expanded_reports_a_bad_data_file_as_a_hive_error(tmp_path):
    with pytest.raises(ExamplesDataError):
        parsing.parse_expanded(str(write(tmp_path, "missing.csv")))


def test_install_replaces_the_parser_behave_uses(monkeypatch):
    monkeypatch.setattr(behave.parser, "parse_file", behave.parser.parse_file)
    parsing.install()
    assert behave.parser.parse_file is parsing.parse_expanded


def test_behave_still_parses_features_through_the_module_attribute():
    """`install` only works while behave calls `gherkin.parse_file` on the parser module."""
    assert behave.runner_util.gherkin is behave.parser
    assert "gherkin.parse_file(" in inspect.getsource(behave.runner_util.parse_features)
