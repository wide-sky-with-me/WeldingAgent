from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pwps_agent.core.fields import FIELD_DEFINITIONS
from pwps_agent.core.contracts import ConfirmationRecord, Evidence
from pwps_agent.core.state import PWPSState


SECTION_TITLES = {
    "A": "文件与项目元信息",
    "B": "焊接适用范围",
    "C": "焊材与辅助材料",
    "D": "焊接参数",
    "E": "热处理与温控",
}


def build_confirmation_view(state: PWPSState) -> dict[str, Any]:
    evidence_by_id = {item.evidence_id: item for item in state.evidence}
    groups = []
    for section, definitions in FIELD_DEFINITIONS.items():
        fields = []
        for field_id, _label in definitions:
            field = state.fields[field_id]
            if not _field_needs_confirmation(field):
                continue
            evidence_ids = set(field.evidence_ids)
            for candidate in field.candidates:
                evidence_ids.update(candidate.get("evidence_ids", []))
            fields.append(
                {
                    "field_id": field.field_id,
                    "label": field.label,
                    "current_value": field.value,
                    "status": field.status,
                    "confidence": field.confidence,
                    "note": field.note,
                    "candidates": list(field.candidates)
                    or _candidate_from_current_value(field),
                    "evidence": [
                        _evidence_snippet(evidence_by_id[evidence_id])
                        for evidence_id in sorted(evidence_ids)
                        if evidence_id in evidence_by_id
                    ],
                    "risks": _risks_for_field(state, field_id),
                }
            )
        if fields:
            groups.append(
                {
                    "group_id": f"section_{section}",
                    "section": section,
                    "title": SECTION_TITLES[section],
                    "fields": fields,
                }
            )
    return {
        "run_id": state.run_id,
        "interaction_mode": state.interaction_mode,
        "clarification_questions": list(state.clarification_questions),
        "groups": groups,
    }


def confirm_fields(
    state: PWPSState,
    field_values: dict[str, Any],
    user_message: str,
    rationale_shown: str | None = None,
    evidence_ids_shown: list[str] | None = None,
    user_rationale: str | None = None,
    action: str = "modified",
    supersedes_confirmation_id: str | None = None,
) -> PWPSState:
    updated = state.model_copy(deep=True)
    field_ids = list(field_values)
    previous_values = {
        field_id: _field_snapshot(updated.fields[field_id])
        for field_id in field_ids
    }

    for field_id, value in field_values.items():
        field = updated.fields[field_id]
        field.value = value
        field.status = "user_confirmed"
        field.confidence = "high"
        field.source = {"type": "user_confirmation"}
        field.confirmation = {
            "required": False,
            "confirmed": True,
            "confirmed_by": "user",
            "confirmed_at": _now_iso(),
            "user_note": user_message,
            "user_rationale": user_rationale,
        }

    record = ConfirmationRecord(
        confirmation_id=f"confirm_{len(updated.confirmations) + 1}",
        field_ids=field_ids,
        action=action,
        values=field_values,
        previous_values=previous_values,
        user_message=user_message,
        user_rationale=user_rationale,
        rationale_shown=rationale_shown,
        evidence_ids_shown=evidence_ids_shown or [],
        supersedes_confirmation_id=supersedes_confirmation_id,
        created_at=_now_iso(),
    )
    updated.confirmations.append(record)
    updated.trace.append(
        {
            "step": len(updated.trace) + 1,
            "node": "guided_confirmation",
            "event_type": "user_confirmation",
            "summary": f"User confirmed fields: {', '.join(field_ids)}",
            "payload": {"field_ids": field_ids},
        }
    )
    return updated


def rollback_confirmation(
    state: PWPSState,
    confirmation_id: str,
    user_message: str,
    reason: str | None = None,
) -> PWPSState:
    target = _find_confirmation(state, confirmation_id)
    updated = state.model_copy(deep=True)
    for field_id, snapshot in target.previous_values.items():
        if field_id not in updated.fields:
            continue
        field = updated.fields[field_id]
        for key, value in snapshot.items():
            setattr(field, key, value)

    record = ConfirmationRecord(
        confirmation_id=f"confirm_{len(updated.confirmations) + 1}",
        field_ids=list(target.field_ids),
        action="rolled_back",
        values={},
        user_message=user_message,
        user_rationale=reason,
        evidence_ids_shown=list(target.evidence_ids_shown),
        rolled_back_confirmation_id=confirmation_id,
        created_at=_now_iso(),
    )
    updated.confirmations.append(record)
    updated.trace.append(
        {
            "step": len(updated.trace) + 1,
            "node": "guided_confirmation",
            "event_type": "confirmation_rollback",
            "summary": f"Rolled back confirmation: {confirmation_id}",
            "payload": {"confirmation_id": confirmation_id, "field_ids": target.field_ids},
        }
    )
    return updated


def edit_confirmation(
    state: PWPSState,
    confirmation_id: str,
    field_values: dict[str, Any],
    user_message: str,
    rationale_shown: str | None = None,
    evidence_ids_shown: list[str] | None = None,
    user_rationale: str | None = None,
) -> PWPSState:
    _find_confirmation(state, confirmation_id)
    return confirm_fields(
        state,
        field_values=field_values,
        user_message=user_message,
        rationale_shown=rationale_shown,
        evidence_ids_shown=evidence_ids_shown,
        user_rationale=user_rationale,
        action="edited",
        supersedes_confirmation_id=confirmation_id,
    )


def apply_supplement(
    state: PWPSState,
    supplement: str,
    field_values: dict[str, Any],
) -> PWPSState:
    updated = state.model_copy(deep=True)
    updated.interaction_mode = "supplement_update"
    evidence_id = f"ev_user_supplement_{len(updated.evidence) + 1}"
    updated.evidence.append(
        Evidence(
            evidence_id=evidence_id,
            source_type="user_input",
            content=supplement,
            related_fields=list(field_values),
            reliability="high",
        )
    )

    for field_id, value in field_values.items():
        field = updated.fields[field_id]
        field.value = value
        field.status = "filled"
        field.confidence = "high"
        field.source = {"type": "user_input", "ref": evidence_id}
        if evidence_id not in field.evidence_ids:
            field.evidence_ids.append(evidence_id)

    updated.trace.append(
        {
            "step": len(updated.trace) + 1,
            "node": "supplement_update",
            "event_type": "state_update",
            "summary": "Applied user supplement.",
            "payload": {"field_ids": list(field_values)},
        }
    )
    return updated


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _field_needs_confirmation(field) -> bool:
    return field.status in {"candidate", "suggested", "need_confirmation", "conflict"} or bool(
        field.candidates
    )


def _candidate_from_current_value(field) -> list[dict[str, Any]]:
    if field.value in (None, ""):
        return []
    return [
        {
            "value": field.value,
            "confidence": field.confidence,
            "evidence_ids": list(field.evidence_ids),
            "note": field.note,
        }
    ]


def _evidence_snippet(evidence: Evidence) -> dict[str, Any]:
    content = evidence.content
    return {
        "evidence_id": evidence.evidence_id,
        "source_type": evidence.source_type,
        "source_ref": evidence.source_ref,
        "content": content if len(content) <= 360 else f"{content[:357]}...",
        "reliability": evidence.reliability,
        "confidence": evidence.confidence,
    }


def _risks_for_field(state: PWPSState, field_id: str) -> list[dict[str, Any]]:
    matched = []
    for risk in state.risks:
        risk_field_ids = set(risk.get("field_ids", []))
        if risk.get("field_id") == field_id or field_id in risk_field_ids:
            matched.append(risk)
    return matched


def _field_snapshot(field) -> dict[str, Any]:
    return {
        "value": field.value,
        "unit": field.unit,
        "candidates": list(field.candidates),
        "source": field.source,
        "evidence_ids": list(field.evidence_ids),
        "confirmation": dict(field.confirmation),
        "confidence": field.confidence,
        "status": field.status,
        "note": field.note,
    }


def _find_confirmation(state: PWPSState, confirmation_id: str) -> ConfirmationRecord:
    for record in state.confirmations:
        if record.confirmation_id == confirmation_id:
            return record
    raise ValueError(f"Unknown confirmation_id: {confirmation_id}")
