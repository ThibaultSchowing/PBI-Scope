from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .private_data import validate_private_roots


def _cmd_validate_private(args: argparse.Namespace) -> int:
    roots = args.path or []
    summary = validate_private_roots(roots)

    print("Private dataset validation summary")
    print(f"  Roots: {summary['roots']}")
    print(f"  Sources found: {summary['sources_found']}")
    print(f"  Sources valid: {summary['sources_valid']}")
    print(f"  Sources invalid: {summary['sources_invalid']}")
    print("")

    for source in summary["sources"]:
        status = "VALID" if source.is_valid else "INVALID"
        print(f"[{status}] {source.source_db} ({source.source_dir})")
        if source.warnings:
            for warning in source.warnings:
                print(f"  - warning: {warning}")
        if source.errors:
            for error in source.errors:
                print(f"  - error: {error}")
        else:
            print(
                f"  - rows={source.stats['rows']}, unique_phages={source.stats['unique_phages']}, "
                f"unique_hosts={source.stats['unique_hosts']}"
            )
        print("")

    return 0 if summary["sources_invalid"] == 0 else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pbi", description="PBI command line utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_private = subparsers.add_parser(
        "validate-private",
        help="Validate private datasets without running the full pipeline",
    )
    validate_private.add_argument(
        "--path",
        action="append",
        required=True,
        help=(
            "Private data root directory containing one subdirectory per source. "
            "Can be provided multiple times."
        ),
    )
    validate_private.set_defaults(func=_cmd_validate_private)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
