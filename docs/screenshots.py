"""Regenerate the README screenshots in docs/images/ from a real run of example/.

    python docs/screenshots.py

Needs the dev setup (behave-hive, allure and playwright installed, chromium downloaded).
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
IMAGES = ROOT / "docs" / "images"
MAX_KB = 250


def run_example(work: Path) -> Path:
    """Copy example/ to `work`, run everything (the failing table included) and return the HTML report."""
    project = work / "example"
    shutil.copytree(ROOT / "example", project, ignore=shutil.ignore_patterns("reports", ".behave-hive", "__pycache__"))
    # "not @none" replaces default_tags, so the table that fails on purpose runs too
    subprocess.run([sys.executable, "-m", "behave_hive.cli", "run", "--", "--tags=not @none"], cwd=project, check=False)
    return project / "reports" / "report.html"


def main() -> None:
    IMAGES.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp, sync_playwright() as playwright:
        report = run_example(Path(tmp))
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1100, "height": 800})

        page.goto(report.as_uri())
        page.screenshot(path=IMAGES / "report-overview.png")

        # The traceback names directories of this machine; the headline above it keeps the error visible
        page.add_style_tag(content="pre { display: none; }")
        page.locator("details.scenario[open]").first.screenshot(path=IMAGES / "report-failure.png")

        filtered = browser.new_page(viewport={"width": 1100, "height": 800})
        filtered.goto(report.as_uri() + "#status=passed&tag=@smoke")
        filtered.click("#expand-all")
        top = filtered.locator(".toolbar").evaluate("el => el.getBoundingClientRect().top + window.scrollY") - 8
        clip = {"x": 0, "y": top, "width": 1100, "height": 330}
        filtered.screenshot(path=IMAGES / "report-filters.png", full_page=True, clip=clip)
        browser.close()

    for image in sorted(IMAGES.glob("*.png")):
        size = image.stat().st_size // 1024
        print(f"{image.relative_to(ROOT)}: {size} KB")
        if size > MAX_KB:
            sys.exit(f"{image.name} is over {MAX_KB} KB; shrink the viewport or crop it")


if __name__ == "__main__":
    main()
