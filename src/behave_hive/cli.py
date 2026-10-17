"""Command line entry point (D10)."""

from __future__ import annotations

import argparse
import sys
from importlib.metadata import version
from pathlib import Path

from behave_hive.errors import HiveError
from behave_hive.expand import expand_tree

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
    expand = sub.add_parser("expand", help="write the features tree with CSV Examples expanded")
    expand.add_argument("source", type=Path)
    expand.add_argument("dest", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    own, _behave_args = split_argv(list(sys.argv[1:] if argv is None else argv))
    try:
        args = build_parser().parse_args(own)
    except SystemExit as exc:  # --version, --help and usage errors
        return exc.code if isinstance(exc.code, int) else 0
    try:
        if args.command == "expand":
            expand_tree(args.source, args.dest, "en")
            return 0
    except HiveError as exc:
        print(f"behave-hive: error: {exc}", file=sys.stderr)
        return exc.exit_code
    return 0


if __name__ == "__main__":
    sys.exit(main())
