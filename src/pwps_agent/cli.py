from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pwps_agent.config import load_settings
from pwps_agent.workflows.auto_draft import run_auto_draft


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pwps-agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    auto_draft = subparsers.add_parser("auto-draft")
    auto_draft.add_argument("requirement")
    auto_draft.add_argument("--output-dir", type=Path, default=None)
    auto_draft.add_argument("--run-id", default="run_cli")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "auto-draft":
        settings = load_settings()
        if args.output_dir is not None:
            settings.paths.output_dir = args.output_dir
        try:
            result = run_auto_draft(
                args.requirement,
                settings=settings,
                run_id=args.run_id,
            )
        except Exception as exc:
            print(f"pwps-agent: {exc}", file=sys.stderr)
            return 1
        print(result.output_dir)
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
