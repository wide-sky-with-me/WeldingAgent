from __future__ import annotations

import sys
from typing import Any, Callable, TextIO

from pwps_agent.config import Settings
from pwps_agent.core.state import PWPSState
from pwps_agent.interaction.normalizer import normalize_interaction_response
from pwps_agent.interaction.terminal import collect_terminal_response
from pwps_agent.workflows.auto_draft import AutoDraftResult
from pwps_agent.workflows.interaction_resume import resume_interaction

TerminalCollector = Callable[[dict, TextIO, TextIO], str]


def continue_interactive_run(
    result: AutoDraftResult,
    settings: Settings,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    collector: TerminalCollector | None = None,
) -> AutoDraftResult:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    collector = collector or collect_terminal_response

    if not should_prompt_inline(result.state, stdin=stdin):
        return result

    current = result
    while should_prompt_inline(current.state, stdin=stdin):
        interaction = current.state.pending_interaction or {}
        payload = collect_terminal_payload(
            interaction,
            stdin,
            stdout,
            collector=collector,
        )
        resumed = resume_interaction(current.state, payload, settings=settings)
        current = AutoDraftResult(state=resumed.state, output_dir=resumed.output_dir)
    return current


def collect_terminal_payload(
    interaction: dict,
    stdin: TextIO,
    stdout: TextIO,
    collector: TerminalCollector | None = None,
) -> dict:
    collector = collector or collect_terminal_response
    questions = _questions(interaction)
    if len(questions) <= 1:
        return _collect_question_payload(interaction, stdin, stdout, collector)

    payloads: list[dict] = []
    for question in questions:
        question_interaction = _interaction_for_question(interaction, question)
        payloads.append(_collect_question_payload(question_interaction, stdin, stdout, collector))
    return _merge_question_payloads(interaction, payloads)


def should_prompt_inline(state: PWPSState, stdin: TextIO | None = None) -> bool:
    stdin = stdin or sys.stdin
    isatty = getattr(stdin, "isatty", None)
    return (
        state.status == "need_user_input"
        and bool(state.pending_interaction)
        and callable(isatty)
        and bool(isatty())
    )


def _interaction_for_question(interaction: dict, question: dict[str, Any]) -> dict:
    question_interaction = dict(interaction)
    question_interaction["questions"] = [question]
    return question_interaction


def _collect_question_payload(
    interaction: dict,
    stdin: TextIO,
    stdout: TextIO,
    collector: TerminalCollector,
) -> dict:
    questions = _questions(interaction)
    question = questions[0] if questions else {}
    if _is_free_text_question(question):
        return _collect_free_text_payload(interaction, question, stdin, stdout, collector)

    raw_text = collector(interaction, stdin, stdout)
    return normalize_interaction_response(interaction, raw_text)


def _collect_free_text_payload(
    interaction: dict,
    question: dict[str, Any],
    stdin: TextIO,
    stdout: TextIO,
    collector: TerminalCollector,
) -> dict:
    field_ids = [str(field_id) for field_id in question.get("field_ids") or []]
    if len(field_ids) == 1:
        raw_text = collector(interaction, stdin, stdout)
        return _terminal_field_payload(
            interaction=interaction,
            fields={field_ids[0]: raw_text},
            message=raw_text,
        )

    fields: dict[str, str] = {}
    messages: list[str] = []
    for field_id in field_ids:
        field_interaction = _interaction_for_question(
            interaction,
            {
                **question,
                "field_ids": [field_id],
                "prompt": f"{question.get('prompt') or 'Please provide input.'}\n{field_id}",
            },
        )
        raw_text = collector(field_interaction, stdin, stdout)
        fields[field_id] = raw_text
        messages.append(f"{field_id}={raw_text}")

    if question.get("required", True) and field_ids and set(fields) != set(field_ids):
        raise ValueError("Required terminal free-text fields were not collected.")
    return _terminal_field_payload(
        interaction=interaction,
        fields=fields,
        message="\n".join(messages),
    )


def _terminal_field_payload(
    *,
    interaction: dict,
    fields: dict[str, Any],
    message: str,
) -> dict:
    return {
        "request_id": str(interaction.get("request_id") or ""),
        "fields": fields,
        "selected_options": [],
        "message": message,
        "reason": "terminal_free_text_fields",
        "evidence_ids_shown": [],
        "action": "modified",
        "unresolved_text": "",
    }


def _is_free_text_question(question: dict[str, Any]) -> bool:
    return question.get("input_kind") == "free_text" and not question.get("options")


def _merge_question_payloads(interaction: dict, payloads: list[dict]) -> dict:
    fields: dict[str, Any] = {}
    selected_options: list[dict[str, Any]] = []
    evidence_ids: list[str] = []
    messages: list[str] = []
    unresolved_text: list[str] = []
    actions: list[str] = []

    for payload in payloads:
        fields.update(payload.get("fields") or {})
        selected_options.extend(payload.get("selected_options") or [])
        for evidence_id in payload.get("evidence_ids_shown") or []:
            evidence_id = str(evidence_id)
            if evidence_id not in evidence_ids:
                evidence_ids.append(evidence_id)
        message = str(payload.get("message") or "")
        if message:
            messages.append(message)
        unresolved = str(payload.get("unresolved_text") or "")
        if unresolved:
            unresolved_text.append(unresolved)
        action = str(payload.get("action") or "")
        if action:
            actions.append(action)

    return {
        "request_id": str(interaction.get("request_id") or ""),
        "fields": fields,
        "selected_options": selected_options,
        "message": "\n".join(messages),
        "reason": "terminal_question_answers",
        "evidence_ids_shown": evidence_ids,
        "action": "accepted" if actions and all(action == "accepted" for action in actions) else "modified",
        "unresolved_text": "\n".join(unresolved_text),
    }


def _questions(interaction: dict) -> list[dict[str, Any]]:
    return [_as_dict(question) for question in interaction.get("questions") or []]


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return dict(value)
