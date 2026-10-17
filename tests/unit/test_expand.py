import textwrap
from pathlib import Path

import pytest

from behave_hive.errors import CsvExamplesError
from behave_hive.expand import ExamplesRef, RowSource, classify_examples, expand_feature_text

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


# --- 2.3 context-aware scanner -------------------------------------------------

def feature(body: str) -> str:
    return "Feature: F\n  Scenario Outline: S\n    Given value \"<user>\"\n" + textwrap.dedent(body)


@pytest.mark.parametrize("delimiter", ['"""', "'''"])
def test_docstring_with_examples_lookalike_is_untouched(delimiter, tmp_path):
    text = (
        "Feature: F\n"
        "  Scenario: S\n"
        "    Given the text is\n"
        f"      {delimiter}\n"
        "      Examples:\n"
        "      | data/login.csv |\n"
        f"      {delimiter}\n"
    )
    assert classify_examples(text, "en") == []
    assert expand_feature_text(text, tmp_path / "a.feature", "en").text == text


def test_docstring_other_delimiter_inside_does_not_close_it():
    text = (
        "Feature: F\n"
        "  Scenario: S\n"
        "    Given the text is\n"
        "      '''\n"
        '      """\n'
        "      Examples:\n"
        "      | data/login.csv |\n"
        "      '''\n"
        "  Scenario Outline: O\n"
        "    Examples:\n"
        "      | x.csv |\n"
    )
    refs = classify_examples(text, "en")
    assert [(r.kind, r.csv_path, r.line) for r in refs] == [("csv", "x.csv", 11)]


def test_extra_rows_after_csv_reference_raise_with_the_line(tmp_path):
    text = feature(
        """\
            Examples:
              | read('a.csv') |
              | x |
        """
    )
    with pytest.raises(CsvExamplesError) as exc:
        expand_feature_text(text, tmp_path / "login.feature", "en")
    assert exc.value.line == 5
    assert "login.feature" in str(exc.value)
    assert "line 5" in str(exc.value)


def test_extra_rows_after_comment_are_still_rejected():
    text = feature(
        """\
            Examples:
              | a.csv |
              # comment

              | x |
        """
    )
    with pytest.raises(CsvExamplesError):
        classify_examples(text, "en")


# --- 2.5 expansion -------------------------------------------------------------

def csv_file(tmp_path, content="user,password\nadmin,secret\nguest,\n", name="data.csv"):
    (tmp_path / name).write_bytes(content.encode())


def test_expansion_replaces_reference_keeping_indentation(tmp_path):
    csv_file(tmp_path)
    text = feature(
        """\
            Examples:
              | read('data.csv') |
        """
    )
    result = expand_feature_text(text, tmp_path / "a.feature", "en")
    assert result.text == feature(
        """\
            Examples:
              | user | password |
              | admin | secret |
              | guest |  |
        """
    )


def test_expansion_escapes_pipe(tmp_path):
    csv_file(tmp_path, "v\na|b\n")
    text = feature("Examples:\n  | data.csv |\n")
    assert r"| a\|b |" in expand_feature_text(text, tmp_path / "a.feature", "en").text


def test_expansion_resolves_path_relative_to_feature_with_dotdot(tmp_path):
    (tmp_path / "shared").mkdir()
    (tmp_path / "shared" / "u.csv").write_text("v\n1\n")
    (tmp_path / "auth").mkdir()
    text = feature("Examples:\n  | ../shared/u.csv |\n")
    result = expand_feature_text(text, tmp_path / "auth" / "a.feature", "en")
    assert "| 1 |" in result.text
    assert result.sources[0].csv_path == tmp_path / "shared" / "u.csv"


@pytest.mark.parametrize("eol", ["\n", "\r\n"])
@pytest.mark.parametrize("final_newline", [True, False])
def test_untouched_file_without_csv_is_byte_identical(tmp_path, eol, final_newline):
    text = eol.join(["Feature: F", "  Scenario: S", "    Given x", "    Examples:", "      | a |"])
    if final_newline:
        text += eol
    assert expand_feature_text(text, tmp_path / "a.feature", "en").text is text


def test_expansion_reference_on_last_line_without_newline_in_crlf_file(tmp_path):
    csv_file(tmp_path)
    text = 'Feature: F\r\n  Scenario Outline: S\r\n    Given x\r\n    Examples:\r\n      | read("data.csv") |'
    out = expand_feature_text(text, tmp_path / "a.feature", "en").text
    assert out.endswith("      | user | password |\r\n      | admin | secret |\r\n      | guest |  |")
    assert "\n" not in out.replace("\r\n", "")


def test_expansion_reference_on_last_line_in_lf_file_without_newline(tmp_path):
    csv_file(tmp_path, "v\n1\n")
    text = "Feature: F\n  Scenario Outline: S\n    Examples:\n      | data.csv |"
    out = expand_feature_text(text, tmp_path / "a.feature", "en").text
    assert out.endswith("      | v |\n      | 1 |")


def test_expansion_reference_on_last_line_uses_the_only_line_ending_of_the_file(tmp_path):
    csv_file(tmp_path, "v\n1\n")
    out = expand_feature_text("Examples:\n| data.csv |", tmp_path / "a.feature", "en")
    assert out.text == "Examples:\n| v |\n| 1 |"


def test_expansion_keeps_tags_and_inline_examples(tmp_path):
    csv_file(tmp_path, "user\nu1\nu2\n")
    text = feature(
        """\
            @smoke
            Examples: csv
              | read('data.csv') |

            Examples: inline
              | user |
              | x |
        """
    )
    out = expand_feature_text(text, tmp_path / "a.feature", "en").text
    assert out == feature(
        """\
            @smoke
            Examples: csv
              | user |
              | u1 |
              | u2 |

            Examples: inline
              | user |
              | x |
        """
    )


def test_expansion_two_csv_tables(tmp_path):
    csv_file(tmp_path, "v\n1\n", "a.csv")
    csv_file(tmp_path, "v\n2\n3\n", "b.csv")
    text = feature("Examples:\n  | a.csv |\nExamples:\n  | b.csv |\n")
    result = expand_feature_text(text, tmp_path / "f.feature", "en")
    lines = result.text.splitlines()
    assert [lines[s.expanded_line - 1] for s in result.sources] == ["  | 1 |", "  | 2 |", "  | 3 |"]


def test_expansion_sources_record_expanded_line_csv_and_row(tmp_path):
    csv_file(tmp_path)
    text = feature("Examples:\n  | data.csv |\n")
    result = expand_feature_text(text, tmp_path / "a.feature", "en")
    path = tmp_path / "data.csv"
    # header on line 5, data rows on 6 and 7; the header is CSV row 1
    assert result.sources == [RowSource(6, path, 2), RowSource(7, path, 3)]


def test_expansion_errors_name_feature_line_and_csv(tmp_path):
    text = feature("Examples:\n  | missing.csv |\n")
    with pytest.raises(CsvExamplesError) as exc:
        expand_feature_text(text, tmp_path / "a.feature", "en")
    assert exc.value.line == 5
    assert "a.feature" in str(exc.value) and "missing.csv" in str(exc.value)


def test_expansion_language_from_directive(tmp_path):
    csv_file(tmp_path, "v\n1\n", "users.csv")
    text = (I18N / "es_csv.feature").read_text(encoding="utf-8")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "users.csv").write_text("user\nu1\n")
    out = expand_feature_text(text, tmp_path / "a.feature", "en").text
    assert "| u1 |" in out
