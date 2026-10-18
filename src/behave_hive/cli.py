"""Command line entry point (D10)."""

from __future__ import annotations

import argparse
import sys
from importlib.metadata import version
from pathlib import Path

from behave_hive.config import load_config
from behave_hive.errors import HiveError
from behave_hive.expand import expand_features
from behave_hive.runner import run_suite

__version__ = version("behave-hive")


def split_argv(argv: list[str]) -> tuple[list[str], list[str]]:
    """Split `argv` at the first `--`: (own arguments, arguments for behave)."""
    if "--" in argv:
        index = argv.index("--")
        return argv[:index], argv[index + 1:]
    return argv, []


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="behave-hive")
    parser.add_argument("--version", action="version", version=f"behave-hive {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run the suite sequentially or in parallel")
    run.add_argument("paths", nargs="*", help="features directories or files (default: from the configuration)")
    run.add_argument("--parallel", action=argparse.BooleanOptionalAction, default=None)
    run.add_argument("-w", "--workers", type=int)
    run.add_argument("--scheme", choices=("scenario", "feature"))
    run.add_argument("--chunk", type=int)
    run.add_argument("--results-dir", dest="results_dir", type=Path)
    run.add_argument("--formats")
    run.add_argument("--config", type=Path)
    run.add_argument("--keep-tmp", action="store_true")
    expand = sub.add_parser("expand", help="write the .feature files with their CSV and JSON Examples expanded")
    expand.add_argument("source", type=Path)
    expand.add_argument("dest", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    own, behave_args = split_argv(argv)
    try:
        args = build_parser().parse_args(own)
    except SystemExit as exc:  # --version, --help and usage errors
        return exc.code if isinstance(exc.code, int) else 0
    try:
        if args.command == "expand":
            expand_features(args.source, args.dest, "en")
            return 0
        cli = {
            key: getattr(args, key)
            for key in ("parallel", "workers", "scheme", "chunk", "results_dir", "formats")
        }
        cli["paths"] = args.paths or None
        return run_suite(load_config(cli, args.config, behave_args), keep_tmp=args.keep_tmp, argv=argv)
    except KeyboardInterrupt:
        return 130
    except HiveError as exc:
        print(f"behave-hive: error: {exc}", file=sys.stderr)
        return exc.exit_code


if __name__ == "__main__":
    sys.exit(main())
