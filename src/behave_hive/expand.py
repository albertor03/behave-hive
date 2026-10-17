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
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from behave.i18n import languages

from behave_hive.errors import CsvExamplesError, HiveError

LANGUAGE_RE = re.compile(r"^\s*#\s*language\s*:\s*(?P<lang>\S+)\s*$")
READ_RE = re.compile(r"""^read\(\s*(['"])(?P<path>.+?)\1\s*\)$""")
DOCSTRING_DELIMITERS = ('"""', "'''")
EXPANDED_MARKER = ".behave-hive-expanded"


@dataclass(frozen=True)
class ExamplesRef:
    """An Examples table found in a feature: `kind` is "csv" or "inline"; `line` is 1-based."""

    kind: str
    line: int
    csv_path: str | None


@dataclass(frozen=True)
class RowSource:
    """Where a generated data row came from: its line in the expanded text and its CSV row."""

    expanded_line: int
    csv_path: Path
    csv_row: int


@dataclass(frozen=True)
class ExpandResult:
    text: str
    sources: list[RowSource] = field(default_factory=list)


@dataclass(frozen=True)
class TreeResult:
    sources_by_file: dict[Path, list[RowSource]] = field(default_factory=dict)


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


def _csv_path_from_cell(cell: str) -> str | None:
    m = READ_RE.match(cell)
    if m:
        return m.group("path")
    if cell.lower().endswith(".csv"):
        return cell
    return None


def _is_blank_or_comment(line: str) -> bool:
    stripped = line.strip()
    return not stripped or stripped.startswith("#")


@dataclass(frozen=True)
class _Table:
    """An Examples table: `row` is the 0-based index of its first row line."""

    kind: str
    row: int
    csv_path: str | None


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
            j = i + 1
            while j < len(lines) and _is_blank_or_comment(lines[j]):
                j += 1
            cells = _cells(lines[j]) if j < len(lines) else None
            if cells is not None:
                csv_path = _csv_path_from_cell(cells[0]) if len(cells) == 1 else None
                if csv_path:
                    k = j + 1
                    while k < len(lines) and _is_blank_or_comment(lines[k]):
                        k += 1
                    if k < len(lines) and lines[k].strip().startswith("|"):
                        raise CsvExamplesError(
                            "a CSV reference does not allow additional rows",
                            feature=feature,
                            line=j + 1,
                        )
                tables.append(_Table("csv" if csv_path else "inline", j, csv_path))
                i = j
        i += 1
    return tables


def classify_examples(text: str, lang: str) -> list[ExamplesRef]:
    """Classify every Examples table of `text` as `csv` or `inline` (D2)."""
    lines = text.splitlines(keepends=True)
    return [ExamplesRef(t.kind, t.row + 1, t.csv_path) for t in _find_tables(lines, lang)]


def read_csv_rows(csv_path: Path, *, feature: Path | None = None, line: int | None = None) -> list[list[str]]:
    """Read and validate a CSV (spec:csv-examples/CSV file contract).

    Returns the header plus the data rows. Physically empty lines are dropped; the
    row numbers used in errors count the header as row 1.
    """

    def error(message: str, row: int | None = None) -> CsvExamplesError:
        return CsvExamplesError(message, feature=feature, line=line, csv_path=csv_path, csv_row=row)

    try:
        with open(csv_path, encoding="utf-8-sig", newline="") as f:
            rows = [r for r in csv.reader(f) if r]
    except FileNotFoundError:
        raise error("Examples CSV not found") from None
    except UnicodeDecodeError:
        raise error("Examples CSV is not valid UTF-8") from None
    except (OSError, csv.Error) as exc:
        raise error(f"cannot read Examples CSV: {exc}") from None

    if len(rows) < 2:
        raise error("Examples CSV needs a header and at least one data row", 1 if rows else None)
    header = [c.strip() for c in rows[0]]
    if "" in header:
        raise error("empty header", 1)
    if len(set(header)) != len(header):
        raise error("duplicated header", 1)
    for number, row in enumerate(rows, start=1):
        if len(row) != len(header):
            raise error(f"row has {len(row)} cells, the header has {len(header)}", number)
        if any("\r" in c or "\n" in c for c in row):
            raise error("a cell contains a line break", number)
    return rows


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
    tables = [t for t in _find_tables(lines, lang, feature_path) if t.kind == "csv"]
    if not tables:
        return ExpandResult(text)

    file_ending = next((e for e in map(_line_ending, reversed(lines)) if e), "\n")
    out: list[str] = []
    sources: list[RowSource] = []
    cursor = 0
    for table in tables:
        out.extend(lines[cursor:table.row])
        ref_line = lines[table.row]
        csv_path = Path(os.path.normpath(feature_path.parent / table.csv_path))
        rows = read_csv_rows(csv_path, feature=feature_path, line=table.row + 1)
        indent = ref_line[: len(ref_line) - len(ref_line.lstrip())]
        ending = _line_ending(ref_line)
        separator = ending or file_ending
        first_line = sum(line.count("\n") for line in out) + 1
        generated = [indent + _format_row(r) for r in rows]
        for offset, _ in enumerate(rows[1:], start=1):
            sources.append(RowSource(first_line + offset, csv_path, offset + 1))
        out.extend(g + separator for g in generated[:-1])
        out.append(generated[-1] + ending)
        cursor = table.row + 1
    out.extend(lines[cursor:])
    return ExpandResult("".join(out), sources)


def _validate_destination(src: Path, dst: Path) -> None:
    """Reject a `dst` that could make `expand_tree` delete something it should not."""
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


def expand_tree(src_root: Path, dst: Path, lang: str) -> TreeResult:
    """Copy `src_root` to `dst`: .feature files are expanded, everything else is symlinked.

    Steps and environment.py are linked, so `__file__` resolves to the original
    and project-relative imports keep working.
    """
    src, dst = Path(src_root).resolve(), Path(dst)
    _validate_destination(src, dst)
    dst_resolved = dst.resolve()
    if dst_resolved.exists():
        shutil.rmtree(dst_resolved)
    dst_resolved.mkdir(parents=True)
    (dst_resolved / EXPANDED_MARKER).write_text("", encoding="utf-8")

    sources_by_file: dict[Path, list[RowSource]] = {}
    for path in sorted(src.rglob("*")):
        if (
            "__pycache__" in path.parts
            or path == dst_resolved
            or dst_resolved in path.parents
            or path in dst_resolved.parents
        ):
            continue
        target = dst_resolved / path.relative_to(src)
        if path.is_symlink() or (not path.is_dir() and path.suffix != ".feature"):
            os.symlink(path.resolve(), target)
        elif path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            with open(path, encoding="utf-8", newline="") as f:
                result = expand_feature_text(f.read(), path, lang)
            with open(target, "w", encoding="utf-8", newline="") as f:
                f.write(result.text)
            if result.sources:
                sources_by_file[target] = result.sources
    return TreeResult(sources_by_file)
