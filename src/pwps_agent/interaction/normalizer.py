from __future__ import annotations

from typing import Any


def normalize_interaction_response(
    interaction: dict,
    raw_text: str,
    explicit_fields: dict | None = None,
) -> dict:
    """Normalize adapter-provided interaction input into a resume payload."""

    request_id = str(interaction.get("request_id") or "")
    message = raw_text
    normalized_text = raw_text.strip()

    if explicit_fields is not None:
        return _payload(
            request_id=request_id,
            fields=_clean_fields(explicit_fields),
            selected_options=[],
            message=message,
            reason="explicit_fields",
            evidence_ids_shown=[],
            action="modified",
            unresolved_text="",
        )

    inline_fields = _parse_field_pairs(normalized_text)
    if inline_fields is not None:
        return _payload(
            request_id=request_id,
            fields=inline_fields,
            selected_options=[],
            message=message,
            reason="parsed_field_pairs",
            evidence_ids_shown=[],
            action="modified",
            unresolved_text="",
        )

    option_match = _match_option(interaction, normalized_text)
    if option_match is not None:
        fields, selected_options, evidence_ids = option_match
        return _payload(
            request_id=request_id,
            fields=fields,
            selected_options=selected_options,
            message=message,
            reason="matched_option",
            evidence_ids_shown=evidence_ids,
            action="accepted",
            unresolved_text="",
        )

    return _payload(
        request_id=request_id,
        fields={},
        selected_options=[],
        message=message,
        reason="unresolved_free_text",
        evidence_ids_shown=[],
        action="modified",
        unresolved_text=message,
    )


def _payload(
    *,
    request_id: str,
    fields: dict[str, Any],
    selected_options: list[dict[str, Any]],
    message: str,
    reason: str,
    evidence_ids_shown: list[str],
    action: str,
    unresolved_text: str,
) -> dict:
    return {
        "request_id": request_id,
        "fields": fields,
        "selected_options": selected_options,
        "message": message,
        "reason": reason,
        "evidence_ids_shown": evidence_ids_shown,
        "action": action,
        "unresolved_text": unresolved_text,
    }


def _parse_field_pairs(raw_text: str) -> dict[str, str] | None:
    if "=" not in raw_text:
        return None

    fields: dict[str, str] = {}
    for part in raw_text.split(","):
        if "=" not in part:
            return None
        field_id, value = part.split("=", 1)
        field_id = field_id.strip()
        value = value.strip()
        if not field_id or not value:
            return None
        fields[field_id] = value
    return fields


def _match_option(
    interaction: dict,
    raw_text: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]] | None:
    exact_matches = _exact_option_matches(interaction, raw_text)
    if len(exact_matches) == 1:
        question, option, index = exact_matches[0]
        return _selection(question, option, index)
    if len(exact_matches) > 1:
        return None

    if raw_text.isdigit():
        target_index = int(raw_text)
        questions_with_options = [
            question
            for question in _questions(interaction)
            if question.get("options")
        ]
        if len(questions_with_options) != 1:
            return None
        question = questions_with_options[0]
        options = list(question.get("options") or [])
        if 1 <= target_index <= len(options):
            return _selection(question, options[target_index - 1], target_index)
        return None

    return None


def _exact_option_matches(
    interaction: dict,
    raw_text: str,
) -> list[tuple[dict[str, Any], dict[str, Any], int]]:
    matches: list[tuple[dict[str, Any], dict[str, Any], int]] = []
    for question in _questions(interaction):
        for index, option in enumerate(question.get("options") or [], start=1):
            value = option.get("value")
            label = option.get("label")
            value_matches = value is not None and raw_text == str(value)
            label_matches = label is not None and raw_text == str(label)
            if value_matches or label_matches:
                matches.append((question, option, index))
    return matches


def _selection(
    question: dict[str, Any],
    option: dict[str, Any],
    option_index: int,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    fields = _clean_fields(option.get("field_updates") or {})
    if not fields:
        field_ids = list(question.get("field_ids") or [])
        value = option.get("value")
        if field_ids and value not in (None, ""):
            fields[str(field_ids[0])] = value

    selected_option = {
        "question_id": str(question.get("question_id") or ""),
        "option_index": option_index,
        "value": option.get("value"),
        "label": option.get("label"),
        "field_updates": fields,
    }
    evidence_ids = [str(evidence_id) for evidence_id in option.get("evidence_ids") or []]
    return fields, [selected_option], evidence_ids


def _questions(interaction: dict) -> list[dict[str, Any]]:
    return [_as_dict(question) for question in interaction.get("questions") or []]


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return dict(value)


def _clean_fields(fields: dict) -> dict[str, Any]:
    return {
        str(field_id): value
        for field_id, value in dict(fields).items()
        if field_id not in (None, "") and value not in (None, "")
    }
