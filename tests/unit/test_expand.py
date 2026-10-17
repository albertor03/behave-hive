from pathlib import Path

import pytest

from behave_hive.expand import ExamplesRef, classify_examples

I18N = Path(__file__).parent.parent / "fixtures" / "i18n"


def outline(examples_rows: str, keyword: str = "Examples") -> str:
    return (
        "Feature: F\n"
        "  Scenario Outline: S\n"
        '    Given value "<user>"\n'
        "\n"
        f"    {keyword}:\n"
        f"{examples_rows}"
    )


@pytest.mark.parametrize(
    "cell, path",
    [
        ("read('data/login.csv')", "data/login.csv"),
        ('read("data/login.csv")', "data/login.csv"),
        ("read( 'data/login.csv' )", "data/login.csv"),
        ("data/login.CSV", "data/login.CSV"),
        ("../shared/users.csv", "../shared/users.csv"),
    ],
)
def test_classification_csv_cell(cell, path):
    refs = classify_examples(outline(f"      | {cell} |\n"), "en")
    assert refs == [ExamplesRef(kind="csv", line=6, csv_path=path)]


def test_classification_inline_table():
    refs = classify_examples(outline("      | user | password |\n      | a | b |\n"), "en")
    assert refs == [ExamplesRef(kind="inline", line=6, csv_path=None)]


def test_classification_single_non_csv_cell_is_inline():
    refs = classify_examples(outline("      | user |\n      | a |\n"), "en")
    assert [r.kind for r in refs] == ["inline"]


def test_classification_two_cells_are_inline_even_if_first_looks_like_csv():
    refs = classify_examples(outline("      | a.csv | b |\n"), "en")
    assert [r.kind for r in refs] == ["inline"]


def test_classification_scenarios_keyword_is_an_examples_keyword():
    refs = classify_examples(outline("      | a.csv |\n", keyword="Scenarios"), "en")
    assert [r.kind for r in refs] == ["csv"]


def test_classification_skips_blank_and_comment_lines_before_the_table():
    text = outline("\n      # note\n      | a.csv |\n")
    refs = classify_examples(text, "en")
    assert refs == [ExamplesRef(kind="csv", line=8, csv_path="a.csv")]


def test_classification_tagged_examples_and_two_tables():
    text = (
        "Feature: F\n"
        "  Scenario Outline: S\n"
        "    Given x\n"
        "    @a\n"
        "    Examples: csv\n"
        "      | read('a.csv') |\n"
        "    Examples: inline\n"
        "      | user |\n"
        "      | u |\n"
    )
    refs = classify_examples(text, "en")
    assert [(r.kind, r.line) for r in refs] == [("csv", 6), ("inline", 8)]


def test_classification_examples_without_table_yields_nothing():
    assert classify_examples("Feature: F\n  Examples:\n", "en") == []


def test_classification_language_from_directive_es():
    text = (I18N / "es_csv.feature").read_text(encoding="utf-8")
    refs = classify_examples(text, "en")
    assert refs == [ExamplesRef(kind="csv", line=7, csv_path="data/users.csv")]


def test_classification_language_from_directive_fr():
    text = (I18N / "fr_csv.feature").read_text(encoding="utf-8")
    refs = classify_examples(text, "en")
    assert refs == [ExamplesRef(kind="csv", line=7, csv_path="data/users.csv")]


def test_classification_language_from_parameter_without_directive():
    text = (I18N / "es_no_directive.feature").read_text(encoding="utf-8")
    refs = classify_examples(text, "es")
    assert [r.kind for r in refs] == ["inline"]
    assert refs[0].line == 6


def test_classification_english_keyword_is_ignored_under_another_language():
    refs = classify_examples(outline("      | a.csv |\n"), "es")
    assert refs == []
