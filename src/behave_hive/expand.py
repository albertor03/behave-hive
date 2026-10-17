"""Expand `Examples:` tables whose body is a single cell pointing to a CSV file.

Supported forms (a single cell under `Examples:`):

    Examples:
      | read('data/login.csv') |

    Examples:
      | data/login.csv |

The path is relative to the .feature directory. The first CSV row holds the
headers (the <placeholder> names).

NOTE: untested prototype; task group 2 covers it with tests and replaces the
hard-coded keyword regex with behave.i18n.
"""
import csv
import re
from dataclasses import dataclass
from pathlib import Path

from behave.i18n import languages

LANGUAGE_RE = re.compile(r"^\s*#\s*language\s*:\s*(?P<lang>\S+)\s*$")

EXAMPLES_RE = re.compile(r"^\s*(Examples|Scenarios|Ejemplos)\s*:", re.IGNORECASE)
READ_RE = re.compile(r"""^read\(\s*(['"])(?P<path>.+?)\1\s*\)$""")


@dataclass(frozen=True)
class ExamplesRef:
    """An Examples table found in a feature: `kind` is "csv" or "inline"; `line` is 1-based."""

    kind: str
    line: int
    csv_path: str | None


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


def classify_examples(text: str, lang: str) -> list[ExamplesRef]:
    """Classify every Examples table of `text` as `csv` or `inline` (D2)."""
    lines = text.splitlines()
    keywords = _examples_keywords(_directive_language(lines) or lang)
    refs = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not any(stripped.startswith(f"{kw}:") for kw in keywords):
            continue
        j = i + 1
        while j < len(lines) and (not lines[j].strip() or lines[j].strip().startswith("#")):
            j += 1
        cells = _cells(lines[j]) if j < len(lines) else None
        if cells is None:
            continue
        csv_path = _csv_path_from_cell(cells[0]) if len(cells) == 1 else None
        refs.append(ExamplesRef("csv" if csv_path else "inline", j + 1, csv_path))
    return refs


def _cells(line):
    stripped = line.strip()
    if not (stripped.startswith("|") and stripped.endswith("|")):
        return None
    return [c.strip() for c in re.split(r"(?<!\\)\|", stripped)[1:-1]]


def _csv_path_from_cell(cell):
    m = READ_RE.match(cell)
    if m:
        return m.group("path")
    if cell.lower().endswith(".csv"):
        return cell
    return None


def _format_row(row):
    return "| " + " | ".join(c.replace("|", r"\|").replace("\n", r"\n") for c in row) + " |"


def expand_feature_text(text, base_dir):
    """Return the .feature text with its CSV Examples expanded."""
    base_dir = Path(base_dir)
    lines = text.splitlines()
    out, i = [], 0
    while i < len(lines):
        out.append(lines[i])
        if not EXAMPLES_RE.match(lines[i]):
            i += 1
            continue
        i += 1
        # skip blank/comment lines up to the table
        j = i
        while j < len(lines) and (not lines[j].strip() or lines[j].strip().startswith("#")):
            j += 1
        cells = _cells(lines[j]) if j < len(lines) else None
        csv_name = _csv_path_from_cell(cells[0]) if cells and len(cells) == 1 else None
        if csv_name is None:
            continue  # regular Examples: left as is
        csv_file = base_dir / csv_name
        if not csv_file.is_file():
            raise FileNotFoundError(f"Examples CSV not found: {csv_file} (line {j + 1})")
        with open(csv_file, newline="", encoding="utf-8-sig") as f:
            rows = [r for r in csv.reader(f) if any(c.strip() for c in r)]
        if len(rows) < 2:
            raise ValueError(f"{csv_file}: needs a header and at least one data row")
        indent = re.match(r"\s*", lines[j]).group(0)
        out.extend(lines[i:j])                       # blank/comment lines in between
        out.extend(indent + _format_row(r) for r in rows)
        i = j + 1
    return "\n".join(out) + "\n"


def expand_tree(src, dst):
    """Copy `src` to `dst`: .feature files are expanded, everything else is symlinked.

    Steps and environment.py are linked, so `__file__.resolve()` points to the
    original and project-relative imports keep working.
    """
    src, dst = Path(src).resolve(), Path(dst).resolve()
    if src.is_file():
        dst.mkdir(parents=True, exist_ok=True)
        target = dst / src.name
        target.write_text(expand_feature_text(src.read_text(encoding="utf-8"), src.parent),
                          encoding="utf-8")
        return target
    dst.mkdir(parents=True, exist_ok=True)
    for path in sorted(src.rglob("*")):
        if "__pycache__" in path.parts or dst in path.parents or path == dst:
            continue
        rel = path.relative_to(src)
        target = dst / rel
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif path.suffix == ".feature":
            target.write_text(expand_feature_text(path.read_text(encoding="utf-8"), path.parent),
                              encoding="utf-8")
        else:
            if target.exists() or target.is_symlink():
                target.unlink()
            target.symlink_to(path)
    return dst
