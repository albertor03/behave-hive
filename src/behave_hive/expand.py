"""Expand `Examples:` tables whose body is a single cell pointing to a CSV file.

Supported forms (a single cell under `Examples:`):

    Examples:
      | read('data/login.csv') |

    Examples:
      | data/login.csv |

The path is relative to the .feature directory. The first CSV row holds the
headers (the <placeholder> names).
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from behave.i18n import languages

from behave_hive.errors import ExamplesDataError, HiveError

LANGUAGE_RE = re.compile(r"^\s*#\s*language\s*:\s*(?P<lang>\S+)\s*$")
READ_RE = re.compile(r"""^read\(\s*(['"])(?P<path>.+?)\1\s*\)$""")
DOCSTRING_DELIMITERS = ('"""', "'''")
EXPANDED_MARKER = ".behave-hive-expanded"
DATA_KINDS = {".csv": "csv", ".json": "json"}
# Number of the first data row in error messages and reports: a CSV counts its header as row 1
FIRST_DATA_ROW = {"csv": 2, "json": 1}


@dataclass(frozen=True)
class ExamplesRef:
    """An Examples table found in a feature: `kind` is "csv" or "inline"; `line` is 1-based."""

    kind: str
    line: int
    data_path: str | None


@dataclass(frozen=True)
class RowSource:
    """Where a generated data row came from: its line in the expanded text and its CSV row."""

    expanded_line: int
    data_path: Path
    data_row: int


@dataclass(frozen=True)
class ExpandResult:
    text: str
    sources: list[RowSource] = field(default_factory=list)


def _directive_language(lines: list[str]) -> str | None:
    """Language from a `# language: xx` directive in the leading non-content lines."""
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if not stripped.startswith("#"):
            return None
        m = LANGUAGE_RE.match(line)
        if m:
            return m.group("lang")
    return None


def _examples_keywords(lang: str) -> tuple[str, ...]:
    entry = languages.get(lang) or languages["en"]
    return tuple(entry["examples"])


def _cells(line: str) -> list[str] | None:
    stripped = line.strip()
    if not (stripped.startswith("|") and stripped.endswith("|")):
        return None
    return [c.strip() for c in re.split(r"(?<!\\)\|", stripped)[1:-1]]


def _data_ref_from_cell(cell: str) -> tuple[str, str] | None:
    """`(kind, path)` when the cell references a data file (`csv` or `json`), else None."""
    m = READ_RE.match(cell)
    path = m.group("path") if m else cell
    kind = DATA_KINDS.get(Path(path).suffix.lower())
    return (kind, path) if kind else None


def _is_blank_or_comment(line: str) -> bool:
    stripped = line.strip()
    return not stripped or stripped.startswith("#")


@dataclass(frozen=True)
class _Table:
    """An Examples table: `row` is the 0-based index of its first row line."""

    kind: str
    row: int
    data_path: str | None


def _skip_blank_or_comment(lines: list[str], start: int) -> int:
    index = start
    while index < len(lines) and _is_blank_or_comment(lines[index]):
        index += 1
    return index


def _table_after(lines: list[str], keyword_line: int, feature: Path | None) -> _Table | None:
    """The table whose first row follows the `Examples:` line, or None when it has no rows."""
    first = _skip_blank_or_comment(lines, keyword_line + 1)
    cells = _cells(lines[first]) if first < len(lines) else None
    if cells is None:
        return None
    ref = _data_ref_from_cell(cells[0]) if len(cells) == 1 else None
    if ref:
        after = _skip_blank_or_comment(lines, first + 1)
        if after < len(lines) and lines[after].strip().startswith("|"):
            raise ExamplesDataError(
                "a data file reference does not allow additional rows", feature=feature, line=first + 1
            )
    return _Table(ref[0] if ref else "inline", first, ref[1] if ref else None)


def _find_tables(lines: list[str], lang: str, feature: Path | None = None) -> list[_Table]:
    """Context-aware scan: docstring contents are never interpreted (D2)."""
    keywords = _examples_keywords(_directive_language(lines) or lang)
    tables = []
    delimiter = None
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if delimiter is not None:
            if stripped.startswith(delimiter):
                delimiter = None
        elif stripped.startswith(DOCSTRING_DELIMITERS):
            delimiter = stripped[:3]
        elif any(stripped.startswith(f"{kw}:") for kw in keywords):
            table = _table_after(lines, i, feature)
            if table is not None:
                tables.append(table)
                i = table.row
        i += 1
    return tables


def classify_examples(text: str, lang: str) -> list[ExamplesRef]:
    """Classify every Examples table of `text` as `csv` or `inline` (D2)."""
    lines = text.splitlines(keepends=True)
    return [ExamplesRef(t.kind, t.row + 1, t.data_path) for t in _find_tables(lines, lang)]


def _read_text(path: Path, error: Callable[..., ExamplesDataError]) -> str:
    try:
        with open(path, encoding="utf-8-sig", newline="") as f:
            return f.read()
    except FileNotFoundError:
        raise error("Examples data file not found") from None
    except UnicodeDecodeError:
        raise error("Examples data file is not valid UTF-8") from None
    except OSError as exc:
        raise error(f"cannot read Examples data file: {exc}") from None


def _load_csv(csv_path: Path, error: Callable[..., ExamplesDataError]) -> list[list[str]]:
    text = _read_text(csv_path, error)
    try:
        return [r for r in csv.reader(io.StringIO(text, newline="")) if r]
    except csv.Error as exc:
        raise error(f"cannot read Examples CSV: {exc}") from None


def _has_line_break(text: str) -> bool:
    return "\r" in text or "\n" in text


def _validate_header(rows: list[list[str]], error: Callable[..., ExamplesDataError]) -> list[str]:
    if len(rows) < 2:
        raise error("Examples CSV needs a header and at least one data row", 1 if rows else None)
    header = [c.strip() for c in rows[0]]
    if "" in header:
        raise error("empty header", 1)
    if len(set(header)) != len(header):
        raise error("duplicated header", 1)
    return header


def _validate_rows(rows: list[list[str]], width: int, error: Callable[..., ExamplesDataError]) -> None:
    for number, row in enumerate(rows, start=1):
        if len(row) != width:
            raise error(f"row has {len(row)} cells, the header has {width}", number)
        if any(_has_line_break(c) for c in row):
            raise error("a cell contains a line break", number)


def read_csv_rows(data_path: Path, *, feature: Path | None = None, line: int | None = None) -> list[list[str]]:
    """Read and validate a CSV (spec:csv-examples/CSV file contract).

    Returns the header plus the data rows. Physically empty lines are dropped; the
    row numbers used in errors count the header as row 1.
    """

    def error(message: str, row: int | None = None) -> ExamplesDataError:
        return ExamplesDataError(message, feature=feature, line=line, data_path=data_path, data_row=row)

    rows = _load_csv(data_path, error)
    header = _validate_header(rows, error)
    _validate_rows(rows, len(header), error)
    return rows


class _Object(list):
    """A JSON object kept as its (key, value) pairs, so a repeated key stays visible."""


def _json_cell(value: object, key: str, number: int, error: Callable[..., ExamplesDataError]) -> str:
    if isinstance(value, list):
        raise error(f"nested value in key {key!r}", number)
    if isinstance(value, str):
        if _has_line_break(value):
            raise error(f"a value contains a line break (key {key!r})", number)
        return value
    return "" if value is None else json.dumps(value)


def _json_row(element: object, number: int, error: Callable[..., ExamplesDataError]) -> dict[str, str]:
    if not isinstance(element, _Object):
        raise error("every element must be an object", number)
    row: dict[str, str] = {}
    for raw_key, value in element:
        key = raw_key.strip()
        if not key or _has_line_break(key):
            raise error("empty key or key with a line break", number)
        if key in row:
            raise error(f"duplicated key {key!r}", number)
        row[key] = _json_cell(value, key, number, error)
    return row


def _json_objects(path: Path, error: Callable[..., ExamplesDataError]) -> list[object]:
    try:
        data = json.loads(_read_text(path, error), object_pairs_hook=_Object)
    except json.JSONDecodeError as exc:
        raise error(f"invalid JSON: {exc.msg} (line {exc.lineno}, column {exc.colno})") from None
    if isinstance(data, _Object) or not isinstance(data, list):
        raise error("the JSON file must be an array of objects")
    if not data:
        raise error("the JSON file needs at least one object")
    return data


def read_json_rows(json_path: Path, *, feature: Path | None = None, line: int | None = None) -> list[list[str]]:
    """Read and validate a JSON file (spec:json-examples/JSON file contract).

    Returns the header (keys of the first object) plus one row per object; error
    row numbers are the 1-based index of the object.
    """

    def error(message: str, row: int | None = None) -> ExamplesDataError:
        return ExamplesDataError(message, feature=feature, line=line, data_path=json_path, data_row=row)

    rows = [_json_row(element, number, error) for number, element in enumerate(_json_objects(json_path, error), 1)]
    header = list(rows[0])
    for number, row in enumerate(rows, start=1):
        missing = [key for key in header if key not in row]
        extra = [key for key in row if key not in header]
        if missing or extra:
            problem = f"missing key {missing}" if missing else f"unexpected key {extra}"
            raise error(problem, number)
    return [header, *([row[key] for key in header] for row in rows)]


READERS = {"csv": read_csv_rows, "json": read_json_rows}


def _format_row(row: list[str]) -> str:
    return "| " + " | ".join(c.replace("|", r"\|") for c in row) + " |"


def _line_ending(line: str) -> str:
    if line.endswith("\r\n"):
        return "\r\n"
    return "\n" if line.endswith("\n") else ""


def expand_feature_text(text: str, feature_path: Path, lang: str) -> ExpandResult:
    """Return the .feature text with its CSV Examples expanded (D2)."""
    feature_path = Path(feature_path)
    lines = text.splitlines(keepends=True)
    tables = [t for t in _find_tables(lines, lang, feature_path) if t.kind != "inline"]
    if not tables:
        return ExpandResult(text)

    file_ending = next((e for e in map(_line_ending, reversed(lines)) if e), "\n")
    out: list[str] = []
    sources: list[RowSource] = []
    cursor = 0
    for table in tables:
        out.extend(lines[cursor:table.row])
        ref_line = lines[table.row]
        data_path = Path(os.path.normpath(feature_path.parent / table.data_path))
        rows = READERS[table.kind](data_path, feature=feature_path, line=table.row + 1)
        indent = ref_line[: len(ref_line) - len(ref_line.lstrip())]
        ending = _line_ending(ref_line)
        separator = ending or file_ending
        first_line = sum(line.count("\n") for line in out) + 1
        generated = [indent + _format_row(r) for r in rows]
        for offset, _ in enumerate(rows[1:], start=1):
            sources.append(RowSource(first_line + offset, data_path, offset + FIRST_DATA_ROW[table.kind] - 1))
        out.extend(g + separator for g in generated[:-1])
        out.append(generated[-1] + ending)
        cursor = table.row + 1
    out.extend(lines[cursor:])
    return ExpandResult("".join(out), sources)


def _validate_destination(src: Path, dst: Path) -> None:
    """Reject a `dst` that could make `expand_features` delete something it should not."""
    if dst.is_symlink():
        raise HiveError(f"expansion destination is a symlink: {dst}")
    resolved = dst.resolve()
    if resolved == src or resolved in src.parents:
        raise HiveError(f"expansion destination {dst} is the source or contains it")
    if resolved.exists():
        if not resolved.is_dir():
            raise HiveError(f"expansion destination is not a directory: {dst}")
        if any(resolved.iterdir()) and not (resolved / EXPANDED_MARKER).is_file():
            raise HiveError(f"expansion destination is not empty and was not created by behave-hive: {dst}")


def expand_features(src_root: Path, dst: Path, lang: str) -> None:
    """Write the `.feature` files of `src_root`, with their data tables expanded, into `dst`.

    Nothing else is copied or linked: `run` expands in memory, and this is how to see the result.
    """
    src, dst = Path(src_root).resolve(), Path(dst)
    _validate_destination(src, dst)
    dst_resolved = dst.resolve()
    if dst_resolved.exists():
        _validate_destination(src, dst)
        shutil.rmtree(dst_resolved)
    dst_resolved.mkdir(parents=True)
    _validate_destination(src, dst)
    (dst_resolved / EXPANDED_MARKER).write_text("", encoding="utf-8")

    for path in sorted(src.rglob("*.feature")):
        target = dst_resolved / path.relative_to(src)
        with open(path, encoding="utf-8", newline="") as f:
            text = expand_feature_text(f.read(), path, lang).text
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8", newline="") as f:
            f.write(text)
