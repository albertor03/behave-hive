import re
from pathlib import Path

CHANGELOG = Path(__file__).resolve().parents[2] / "CHANGELOG.md"


def test_changelog_follows_keep_a_changelog_and_lists_the_four_capabilities_of_0_1_0():
    text = CHANGELOG.read_text(encoding="utf-8")
    assert text.startswith("# Changelog")
    assert re.search(r"\]\(https://keepachangelog\.com/en/1\.1\.0/\)", text)
    assert "## [0.1.0]" in text
    released = text.split("## [0.1.0]", 1)[1].lower()
    for capability in ("csv examples", "configuration", "parallel", "report"):
        assert capability in released, capability
