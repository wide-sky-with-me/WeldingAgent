from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from pwps_agent.config import load_settings
from pwps_agent.core.modes import (
    build_confirmation_view,
    confirm_fields,
    edit_confirmation,
    rollback_confirmation,
)
from pwps_agent.web.guided_confirmation import load_state, save_state, serve_guided_confirmation
from pwps_agent.workflows.guided_confirmation import (
    resume_guided_confirmation,
    resume_guided_confirmation_from_checkpoint,
)
from pwps_agent.workflows.supplement_update import (
    resume_supplement_update,
    resume_supplement_update_from_checkpoint,
)
from pwps_agent.workflows.auto_draft import run_graph_auto_draft, run_graph_guided_draft

LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pwps-agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    auto_draft = subparsers.add_parser("auto-draft")
    auto_draft.add_argument("requirement")
    auto_draft.add_argument("--output-dir", type=Path, default=None)
    auto_draft.add_argument("--run-id", default="run_cli")

    guided_draft = subparsers.add_parser("guided-draft")
    guided_draft.add_argument("requirement")
    guided_draft.add_argument("--output-dir", type=Path, default=None)
    guided_draft.add_argument("--run-id", default="run_cli")

    guided_confirm = subparsers.add_parser("guided-confirm")
    guided_confirm.add_argument("state_path", type=Path)
    guided_confirm.add_argument("--set", dest="set_values", action="append", default=[])
    guided_confirm.add_argument("--message", default="User confirmation from CLI.")
    guided_confirm.add_argument("--reason", default=None)
    guided_confirm.add_argument("--evidence-id", dest="evidence_ids", action="append", default=[])
    guided_confirm.add_argument("--edit", dest="edit_confirmation_id", default=None)
    guided_confirm.add_argument("--rollback", dest="rollback_confirmation_id", default=None)

    guided_confirm_view = subparsers.add_parser("guided-confirm-view")
    guided_confirm_view.add_argument("state_path", type=Path)

    guided_confirm_resume = subparsers.add_parser("guided-confirm-resume")
    guided_confirm_resume.add_argument("state_path", type=Path)
    guided_confirm_resume.add_argument("--set", dest="set_values", action="append", default=[])
    guided_confirm_resume.add_argument("--message", default="User confirmation from CLI.")
    guided_confirm_resume.add_argument("--reason", default=None)
    guided_confirm_resume.add_argument("--evidence-id", dest="evidence_ids", action="append", default=[])
    guided_confirm_resume.add_argument("--output-dir", type=Path, default=None)

    guided_confirm_resume_run = subparsers.add_parser("guided-confirm-resume-run")
    guided_confirm_resume_run.add_argument("run_id")
    guided_confirm_resume_run.add_argument("--set", dest="set_values", action="append", default=[])
    guided_confirm_resume_run.add_argument("--message", default="User confirmation from CLI.")
    guided_confirm_resume_run.add_argument("--reason", default=None)
    guided_confirm_resume_run.add_argument("--evidence-id", dest="evidence_ids", action="append", default=[])
    guided_confirm_resume_run.add_argument("--output-dir", type=Path, default=None)

    guided_confirm_web = subparsers.add_parser("guided-confirm-web")
    guided_confirm_web.add_argument("state_path", type=Path)
    guided_confirm_web.add_argument("--host", default="127.0.0.1")
    guided_confirm_web.add_argument("--port", type=int, default=8765)

    supplement_state = subparsers.add_parser("supplement-state")
    supplement_state.add_argument("state_path", type=Path)
    supplement_state.add_argument("--message", required=True)
    supplement_state.add_argument("--set", dest="set_values", action="append", default=[])
    supplement_state.add_argument("--output-dir", type=Path, default=None)

    supplement_run = subparsers.add_parser("supplement-run")
    supplement_run.add_argument("run_id")
    supplement_run.add_argument("--message", required=True)
    supplement_run.add_argument("--set", dest="set_values", action="append", default=[])
    supplement_run.add_argument("--output-dir", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_logging()
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "auto-draft":
        settings = load_settings()
        if args.output_dir is not None:
            settings.paths.output_dir = args.output_dir
        LOGGER.info(
            "Starting auto-draft run_id=%s planner=%s output_dir=%s",
            args.run_id,
            "llm",
            settings.paths.output_dir,
        )
        try:
            result = run_graph_auto_draft(
                args.requirement,
                settings=settings,
                run_id=args.run_id,
            )
        except Exception as exc:
            LOGGER.error("Auto-draft failed run_id=%s error=%s", args.run_id, exc)
            print(f"pwps-agent: {exc}", file=sys.stderr)
            return 1
        LOGGER.info(
            "Completed auto-draft run_id=%s status=%s output_dir=%s",
            args.run_id,
            result.state.status,
            result.output_dir,
        )
        print(result.output_dir)
        return 0

    if args.command == "guided-draft":
        settings = load_settings()
        if args.output_dir is not None:
            settings.paths.output_dir = args.output_dir
        LOGGER.info(
            "Starting guided-draft run_id=%s planner=%s output_dir=%s",
            args.run_id,
            "llm",
            settings.paths.output_dir,
        )
        try:
            result = run_graph_guided_draft(
                args.requirement,
                settings=settings,
                run_id=args.run_id,
            )
        except Exception as exc:
            LOGGER.error("Guided-draft failed run_id=%s error=%s", args.run_id, exc)
            print(f"pwps-agent: {exc}", file=sys.stderr)
            return 1
        LOGGER.info(
            "Completed guided-draft run_id=%s status=%s output_dir=%s",
            args.run_id,
            result.state.status,
            result.output_dir,
        )
        print(result.output_dir)
        return 0

    if args.command == "guided-confirm":
        try:
            state = load_state(args.state_path)
            if args.rollback_confirmation_id:
                updated = rollback_confirmation(
                    state,
                    confirmation_id=args.rollback_confirmation_id,
                    user_message=args.message,
                    reason=args.reason,
                )
            else:
                field_values = _parse_set_values(args.set_values)
                if args.edit_confirmation_id:
                    updated = edit_confirmation(
                        state,
                        confirmation_id=args.edit_confirmation_id,
                        field_values=field_values,
                        user_message=args.message,
                        user_rationale=args.reason,
                        evidence_ids_shown=args.evidence_ids,
                    )
                else:
                    updated = confirm_fields(
                        state,
                        field_values=field_values,
                        user_message=args.message,
                        user_rationale=args.reason,
                        evidence_ids_shown=args.evidence_ids,
                        action="modified",
                    )
            save_state(args.state_path, updated)
        except Exception as exc:
            print(f"pwps-agent: {exc}", file=sys.stderr)
            return 1
        print(updated.confirmations[-1].confirmation_id)
        return 0

    if args.command == "guided-confirm-view":
        try:
            state = load_state(args.state_path)
            print(json.dumps(build_confirmation_view(state), ensure_ascii=False, indent=2))
        except Exception as exc:
            print(f"pwps-agent: {exc}", file=sys.stderr)
            return 1
        return 0

    if args.command == "guided-confirm-resume":
        settings = load_settings()
        if args.output_dir is not None:
            settings.paths.output_dir = args.output_dir
        try:
            state = load_state(args.state_path)
            result = resume_guided_confirmation(
                state,
                {
                    "fields": _parse_set_values(args.set_values),
                    "message": args.message,
                    "reason": args.reason,
                    "evidence_ids_shown": args.evidence_ids,
                    "action": "accepted",
                },
                settings=settings,
            )
            save_state(args.state_path, result.state)
        except Exception as exc:
            print(f"pwps-agent: {exc}", file=sys.stderr)
            return 1
        print(result.output_dir)
        return 0

    if args.command == "guided-confirm-resume-run":
        settings = load_settings()
        if args.output_dir is not None:
            settings.paths.output_dir = args.output_dir
        try:
            result = resume_guided_confirmation_from_checkpoint(
                run_id=args.run_id,
                payload={
                    "fields": _parse_set_values(args.set_values),
                    "message": args.message,
                    "reason": args.reason,
                    "evidence_ids_shown": args.evidence_ids,
                    "action": "accepted",
                },
                settings=settings,
            )
        except Exception as exc:
            print(f"pwps-agent: {exc}", file=sys.stderr)
            return 1
        print(result.output_dir)
        return 0

    if args.command == "guided-confirm-web":
        try:
            serve_guided_confirmation(args.state_path, host=args.host, port=args.port)
        except KeyboardInterrupt:
            return 0
        except Exception as exc:
            print(f"pwps-agent: {exc}", file=sys.stderr)
            return 1

    if args.command == "supplement-state":
        settings = load_settings()
        if args.output_dir is not None:
            settings.paths.output_dir = args.output_dir
        try:
            state = load_state(args.state_path)
            result = resume_supplement_update(
                state,
                {
                    "supplement": args.message,
                    "fields": _parse_set_values(args.set_values),
                },
                settings=settings,
            )
            save_state(args.state_path, result.state)
        except Exception as exc:
            print(f"pwps-agent: {exc}", file=sys.stderr)
            return 1
        print(result.output_dir)
        return 0

    if args.command == "supplement-run":
        settings = load_settings()
        if args.output_dir is not None:
            settings.paths.output_dir = args.output_dir
        try:
            result = resume_supplement_update_from_checkpoint(
                run_id=args.run_id,
                payload={
                    "supplement": args.message,
                    "fields": _parse_set_values(args.set_values),
                },
                settings=settings,
            )
        except Exception as exc:
            print(f"pwps-agent: {exc}", file=sys.stderr)
            return 1
        print(result.output_dir)
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2


def _parse_set_values(values: list[str]) -> dict[str, str]:
    parsed = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"--set must use field=value format: {value}")
        field_id, field_value = value.split("=", 1)
        if not field_id or not field_value:
            raise ValueError(f"--set must include non-empty field and value: {value}")
        parsed[field_id] = field_value
    if not parsed:
        raise ValueError("At least one --set field=value is required.")
    return parsed


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
        force=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())
