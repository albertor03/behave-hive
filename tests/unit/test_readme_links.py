"""The README is also the PyPI project page, where relative links and images are broken."""

import re
from pathlib import Path

README = Path(__file__).resolve().parents[2] / "README.md"


def test_readme_links_and_images_are_absolute_or_anchors():
    targets = re.findall(r"\]\(([^)\s]+)", README.read_text(encoding="utf-8"))
    relative = [t for t in targets if not t.startswith(("https://", "#"))]
    assert not relative, f"use absolute GitHub URLs, PyPI cannot resolve: {relative}"
