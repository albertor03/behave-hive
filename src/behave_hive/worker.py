"""Runs one batch in its own behave process: `python -m behave_hive.worker --plan <plan.json>` (D3)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from behave.exception import ConfigError as BehaveConfigError
from behave.exception import TagExpressionError
from behave.formatter.base import StreamOpener

from behave_hive.config import build_behave_config

CUCUMBER = "behave_hive.formatters.cucumber:CucumberJSONFormatter"
ALLURE = "behave_hive.formatters.allure:AllureFormatter"
PATH_MAP_KEY = "behave_hive.path_map"


def _write_environment(allure_dir: Path, environment: dict[str, str]) -> None:
    if environment:
        allure_dir.mkdir(parents=True, exist_ok=True)
        lines = (f"{key}={value}\n" for key, value in environment.items())
        (allure_dir / "environment.properties").write_text("".join(lines), encoding="utf-8")


def run_plan(plan: dict) -> int:
    from behave.__main__ import run_behave

    args = ["@" + plan["locations_file"], *plan["behave_args"]]
    try:
        config = build_behave_config(args)
    except (BehaveConfigError, TagExpressionError) as exc:
        print(f"{exc.__class__.__name__}: {exc}", file=sys.stderr)
        return 1

    formats = [CUCUMBER]
    outputs = [StreamOpener(plan["cucumber_out"])]
    if plan.get("allure_dir"):
        formats.append(ALLURE)
        outputs.append(StreamOpener(plan["allure_dir"]))
        _write_environment(Path(plan["allure_dir"]), plan.get("environment", {}))
    formats.append("plain")
    outputs.append(StreamOpener(stream=sys.stdout))
    config.format = formats
    config.outputs = outputs
    config.show_skipped = True
    config.userdata[PATH_MAP_KEY] = json.dumps(plan.get("path_map", {}))
    return run_behave(config)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="behave_hive.worker")
    parser.add_argument("--plan", type=Path, required=True)
    args = parser.parse_args(argv)
    return run_plan(json.loads(args.plan.read_text(encoding="utf-8")))


if __name__ == "__main__":
    sys.exit(main())
