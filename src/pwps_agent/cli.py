from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, TextIO

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
from pwps_agent.workflows.interaction_resume import resume_interaction
from pwps_agent.workflows.supplement_update import (
    resume_supplement_update,
    resume_supplement_update_from_checkpoint,
)
from pwps_agent.workflows.auto_draft import (
    AutoDraftResult,
    run_graph_auto_draft,
    run_graph_guided_draft,
)

LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pwps-agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    draft = subparsers.add_parser("draft")
    draft.add_argument("requirement")
    draft.add_argument("--output-dir", type=Path, default=None)
    draft.add_argument("--run-id", default="run_cli")

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

    interaction_resume = subparsers.add_parser("interaction-resume")
    interaction_resume.add_argument("state_path", type=Path)
    interaction_resume.add_argument("--set", dest="set_values", action="append", default=[])
    interaction_resume.add_argument("--message", default="User runtime interaction response.")
    interaction_resume.add_argument("--reason", default=None)
    interaction_resume.add_argument("--evidence-id", dest="evidence_ids", action="append", default=[])
    interaction_resume.add_argument("--output-dir", type=Path, default=None)

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

    if args.command == "draft":
        settings = load_settings()
        if args.output_dir is not None:
            settings.paths.output_dir = args.output_dir
        LOGGER.info(
            "Starting draft run_id=%s mode=%s planner=%s output_dir=%s",
            args.run_id,
            settings.workflow.interaction_mode,
            "llm",
            settings.paths.output_dir,
        )
        try:
            if settings.workflow.interaction_mode == "guided_confirmation":
                result = run_graph_guided_draft(
                    args.requirement,
                    settings=settings,
                    run_id=args.run_id,
                )
            else:
                result = run_graph_auto_draft(
                    args.requirement,
                    settings=settings,
                    run_id=args.run_id,
                )
            result = _continue_interactive_run(result, settings)
        except Exception as exc:
            LOGGER.error("Draft failed run_id=%s error=%s", args.run_id, exc)
            print(f"pwps-agent: {exc}", file=sys.stderr)
            return 1
        LOGGER.info(
            "Completed draft run_id=%s mode=%s status=%s output_dir=%s",
            args.run_id,
            result.state.interaction_mode,
            result.state.status,
            result.output_dir,
        )
        print(result.output_dir)
        return 0

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
            result = _continue_interactive_run(result, settings)
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
            result = _continue_interactive_run(result, settings)
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

    if args.command == "interaction-resume":
        settings = load_settings()
        if args.output_dir is not None:
            settings.paths.output_dir = args.output_dir
        try:
            state = load_state(args.state_path)
            result = resume_interaction(
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


def _continue_interactive_run(result: AutoDraftResult, settings) -> AutoDraftResult:
    if not _should_prompt_inline(result.state):
        return result

    current = result
    while _should_prompt_inline(current.state):
        payload = _read_interaction_payload(current.state.pending_interaction or {})
        current = resume_interaction(current.state, payload, settings=settings)
    return AutoDraftResult(state=current.state, output_dir=current.output_dir)


def _should_prompt_inline(state) -> bool:
    return (
        state.status == "need_user_input"
        and bool(state.pending_interaction)
        and sys.stdin.isatty()
    )


def _read_interaction_payload(
    interaction: dict[str, Any],
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> dict[str, Any]:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    print("", file=stdout)
    print(f"[需要用户输入] {interaction.get('title', 'Runtime interaction')}", file=stdout)
    summary = interaction.get("summary")
    if summary:
        print(str(summary), file=stdout)

    fields: dict[str, str] = {}
    evidence_ids: list[str] = []
    messages: list[str] = []
    for question in interaction.get("questions", []):
        question_payload = _prompt_for_question(question, stdin=stdin, stdout=stdout)
        fields.update(question_payload["fields"])
        evidence_ids.extend(question_payload["evidence_ids"])
        if question_payload["message"]:
            messages.append(question_payload["message"])

    if not fields:
        raise ValueError("Runtime interaction requires at least one field value.")

    return {
        "fields": fields,
        "message": "\n".join(messages) or "User runtime interaction response.",
        "reason": "Collected inline from interactive CLI.",
        "evidence_ids_shown": evidence_ids,
        "action": "accepted",
    }


def _prompt_for_question(
    question: dict[str, Any],
    *,
    stdin: TextIO,
    stdout: TextIO,
) -> dict[str, Any]:
    prompt = str(question.get("prompt") or "Please provide input.")
    input_kind = question.get("input_kind")
    options = list(question.get("options") or [])
    field_ids = [str(field_id) for field_id in question.get("field_ids", [])]

    print("", file=stdout)
    print(prompt, file=stdout)
    if options:
        _print_options(options, stdout=stdout)
        selected = _read_required_line("选择编号或直接输入值: ", stdin=stdin, stdout=stdout)
        fields, evidence_ids, message = _fields_from_option_input(
            selected,
            options,
            field_ids,
        )
        return {
            "fields": fields,
            "evidence_ids": evidence_ids,
            "message": message,
        }

    if input_kind == "free_text" and len(field_ids) > 1:
        fields = {}
        messages = []
        for field_id in field_ids:
            value = _read_required_line(f"{field_id}: ", stdin=stdin, stdout=stdout)
            fields[field_id] = value
            messages.append(f"{field_id}={value}")
        return {"fields": fields, "evidence_ids": [], "message": "; ".join(messages)}

    field_id = field_ids[0] if field_ids else "user_response"
    value = _read_required_line(f"{field_id}: ", stdin=stdin, stdout=stdout)
    return {
        "fields": {field_id: value},
        "evidence_ids": [],
        "message": f"{field_id}={value}",
    }


def _print_options(options: list[dict[str, Any]], *, stdout: TextIO) -> None:
    for index, option in enumerate(options, start=1):
        marker = " [推荐]" if option.get("recommended") else ""
        label = option.get("label") or option.get("value")
        print(f"{index}. {label}{marker}", file=stdout)
        suitability = option.get("suitability")
        if suitability:
            print(f"   适用性: {suitability}", file=stdout)
        risk_note = option.get("risk_note")
        if risk_note:
            print(f"   风险: {risk_note}", file=stdout)


def _fields_from_option_input(
    selected: str,
    options: list[dict[str, Any]],
    field_ids: list[str],
) -> tuple[dict[str, str], list[str], str]:
    if selected.isdigit():
        index = int(selected)
        if not 1 <= index <= len(options):
            raise ValueError(f"Selection out of range: {selected}")
        option = options[index - 1]
        field_updates = {
            str(field_id): str(value)
            for field_id, value in dict(option.get("field_updates") or {}).items()
            if value not in (None, "")
        }
        if not field_updates and field_ids:
            field_updates[field_ids[0]] = str(option.get("value"))
        return (
            field_updates,
            [str(evidence_id) for evidence_id in option.get("evidence_ids", [])],
            f"selected option {index}: {option.get('label') or option.get('value')}",
        )

    if "=" in selected:
        return _parse_inline_field_values(selected), [], selected

    if not field_ids:
        raise ValueError("Free-form option input requires a target field.")
    return {field_ids[0]: selected}, [], f"{field_ids[0]}={selected}"


def _parse_inline_field_values(value: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for part in value.split(","):
        if "=" not in part:
            raise ValueError(f"Expected field=value pair: {part}")
        field_id, field_value = part.split("=", 1)
        field_id = field_id.strip()
        field_value = field_value.strip()
        if not field_id or not field_value:
            raise ValueError(f"Expected non-empty field=value pair: {part}")
        fields[field_id] = field_value
    return fields


def _read_required_line(prompt: str, *, stdin: TextIO, stdout: TextIO) -> str:
    while True:
        print(prompt, end="", flush=True, file=stdout)
        value = stdin.readline()
        if value == "":
            raise EOFError("Input ended while waiting for runtime interaction response.")
        value = value.strip()
        if value:
            return value
        print("不能为空。", file=stdout)


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
        force=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())
