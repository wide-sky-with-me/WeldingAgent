from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from pwps_agent.core.contracts import Evidence
from pwps_agent.core.fields import FieldState
from pwps_agent.core.quality import DraftQualityReport
from pwps_agent.core.state import PWPSState


ALLOWED_PATCH_KEYS = {
    "core_fields",
    "knowledge_queries",
    "search_results",
    "evidence",
    "fields",
    "clarification_questions",
    "risks",
    "sections",
    "draft_markdown",
    "draft_html",
    "field_report",
    "quality_report",
    "refinement_attempts",
    "max_refinement_attempts",
    "status",
}


def merge_state_patch(state: PWPSState, patch: dict[str, Any]) -> PWPSState:
    updated = state.model_copy(deep=True)
    for key in patch:
        if key not in ALLOWED_PATCH_KEYS:
            _append_merge_warning(
                updated,
                "Ignored unknown state patch key.",
                {"key": key},
            )

    updated.core_fields.update(patch.get("core_fields", {}))
    _extend_unique_dicts(updated.knowledge_queries, patch.get("knowledge_queries", []), "query_id")
    _extend_unique_dicts(updated.search_results, patch.get("search_results", []), "result_id")
    _extend_unique_evidence(updated, patch.get("evidence", []))
    _merge_fields(updated, patch.get("fields", {}))
    updated.clarification_questions.extend(patch.get("clarification_questions", []))
    updated.risks.extend(patch.get("risks", []))
    updated.sections.update(patch.get("sections", {}))
    if "draft_markdown" in patch:
        updated.draft_markdown = str(patch["draft_markdown"])
    if "draft_html" in patch:
        updated.draft_html = str(patch["draft_html"])
    if "field_report" in patch:
        updated.field_report = dict(patch["field_report"])
    if "quality_report" in patch:
        _merge_quality_report(updated, patch["quality_report"])
    if "refinement_attempts" in patch:
        _merge_refinement_counter(
            updated,
            "refinement_attempts",
            patch["refinement_attempts"],
            0,
        )
    if "max_refinement_attempts" in patch:
        _merge_refinement_counter(
            updated,
            "max_refinement_attempts",
            patch["max_refinement_attempts"],
            1,
        )
    if "status" in patch:
        updated.status = patch["status"]
    return updated


def _merge_quality_report(state: PWPSState, value: Any) -> None:
    if value is None:
        state.quality_report = None
        return
    try:
        state.quality_report = DraftQualityReport.model_validate(value).model_dump()
    except ValidationError as exc:
        _append_merge_warning(
            state,
            "Ignored invalid quality report patch.",
            {"key": "quality_report", "error": str(exc)},
        )


def _merge_refinement_counter(
    state: PWPSState,
    key: str,
    value: Any,
    minimum: int,
) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        _append_merge_warning(
            state,
            "Ignored invalid refinement counter patch.",
            {"key": key, "value": value, "minimum": minimum},
        )
        return
    setattr(state, key, value)


def _merge_fields(state: PWPSState, fields_patch: dict[str, dict[str, Any]]) -> None:
    for field_id, field_patch in fields_patch.items():
        if field_id not in state.fields:
            _append_merge_warning(
                state,
                "Ignored unknown field patch.",
                {"field_id": field_id},
            )
            continue
        field_patch = _normalize_field_patch(state, field_id, field_patch)
        field = state.fields[field_id]
        incoming_value = field_patch.get("value")
        if (
            incoming_value not in (None, "")
            and field.value not in (None, "")
            and incoming_value != field.value
            and _field_priority(field.status, field.source) > _patch_priority(field_patch)
        ):
            field.candidates.append(_candidate_from_patch(field_patch))
            continue
        for key, value in field_patch.items():
            setattr(field, key, value)
        if field.source is None:
            field.source = {}
        field.source.setdefault("updated_at", _now_iso())


def _normalize_field_patch(
    state: PWPSState,
    field_id: str,
    field_patch: dict[str, Any],
) -> dict[str, Any]:
    normalized = dict(field_patch)
    status = normalized.get("status")
    if status == "confirmed":
        normalized["status"] = "filled"
        return normalized
    if status is not None and status not in FieldState.model_fields["status"].annotation.__args__:
        _append_merge_warning(
            state,
            "Normalized invalid field status to candidate.",
            {"field_id": field_id, "status": status},
        )
        normalized["status"] = "candidate"
    return normalized


def _candidate_from_patch(field_patch: dict[str, Any]) -> dict[str, Any]:
    return {
        "value": field_patch.get("value"),
        "status": field_patch.get("status", "candidate"),
        "confidence": field_patch.get("confidence", "unknown"),
        "evidence_ids": list(field_patch.get("evidence_ids", [])),
        "source": field_patch.get("source"),
        "note": field_patch.get("note"),
        "created_at": _now_iso(),
    }


def _field_priority(status: str, source: dict[str, Any] | None) -> int:
    if status == "user_confirmed":
        return 100
    source_type = (source or {}).get("type")
    if status == "filled" and source_type in {None, "user_input", "user_confirmation"}:
        return 80
    if status == "filled":
        return 70
    if status in {"candidate", "suggested", "need_confirmation"}:
        return 40
    return 0


def _patch_priority(field_patch: dict[str, Any]) -> int:
    return _field_priority(
        str(field_patch.get("status", "candidate")),
        field_patch.get("source"),
    )


def _extend_unique_dicts(target: list[dict[str, Any]], values: list[dict[str, Any]], key: str) -> None:
    existing = {item.get(key) for item in target}
    for value in values:
        identifier = value.get(key)
        if identifier in existing:
            continue
        target.append(value)
        existing.add(identifier)


def _extend_unique_evidence(state: PWPSState, values: list[Any]) -> None:
    existing = {evidence.evidence_id for evidence in state.evidence}
    for value in values:
        try:
            evidence = value if isinstance(value, Evidence) else Evidence.model_validate(value)
        except ValidationError as exc:
            _append_merge_warning(
                state,
                "Ignored invalid evidence patch.",
                {"error": str(exc)},
            )
            continue
        if evidence.evidence_id in existing:
            continue
        state.evidence.append(evidence)
        existing.add(evidence.evidence_id)


def _append_merge_warning(state: PWPSState, summary: str, payload: dict[str, Any]) -> None:
    state.trace.append(
        {
            "step": len(state.trace) + 1,
            "node": "state_merge",
            "event_type": "merge_warning",
            "summary": summary,
            "payload": payload,
        }
    )


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()
