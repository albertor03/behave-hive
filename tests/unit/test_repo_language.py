"""Everything versioned is in English (D12): no Spanish-specific characters outside tests/fixtures/i18n/."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXEMPT = "tests/fixtures/i18n/"
# Spanish accented vowels, u with diaeresis, n with tilde and inverted punctuation (both cases),
# written with escapes so this file does not flag itself
SPANISH = re.compile("[\u00e1\u00e9\u00ed\u00f3\u00fa\u00fc\u00f1\u00bf\u00a1\u00c1\u00c9\u00cd\u00d3\u00da\u00dc\u00d1]")


def find_violations(root: Path, files: list[str]) -> list[str]:
    found = []
    for name in files:
        if name.startswith(EXEMPT):
            continue
        try:
            text = (root / name).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary or unreadable: not text
        for number, line in enumerate(text.splitlines(), start=1):
            if SPANISH.search(line):
                found.append(f"{name}:{number}")
    return found


def tracked_files() -> list[str]:
    result = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True)
    return result.stdout.splitlines()


def test_the_tracked_tree_has_no_spanish_characters_outside_the_i18n_fixtures():
    assert find_violations(ROOT, tracked_files()) == []


def test_the_guard_reports_file_and_line_of_a_spanish_character(tmp_path):
    (tmp_path / "bad.py").write_text("ok\n# comment with \u00f1\n", encoding="utf-8")
    assert find_violations(tmp_path, ["bad.py"]) == ["bad.py:2"]


def test_the_guard_skips_the_i18n_fixtures_and_binary_files(tmp_path):
    (tmp_path / "tests/fixtures/i18n").mkdir(parents=True)
    (tmp_path / "tests/fixtures/i18n/es.feature").write_text("Caracter\u00edstica: x\n", encoding="utf-8")
    (tmp_path / "blob.bin").write_bytes(b"\xff\xfe\x00\xf1")
    assert find_violations(tmp_path, ["tests/fixtures/i18n/es.feature", "blob.bin"]) == []
