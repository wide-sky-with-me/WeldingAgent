from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pwps_agent.core.contracts import ConfirmationRecord, Evidence
from pwps_agent.core.state import PWPSState


def confirm_fields(
    state: PWPSState,
    field_values: dict[str, Any],
    user_message: str,
    rationale_shown: str | None = None,
    evidence_ids_shown: list[str] | None = None,
) -> PWPSState:
    updated = state.model_copy(deep=True)
    field_ids = list(field_values)

    for field_id, value in field_values.items():
        field = updated.fields[field_id]
        field.value = value
        field.status = "user_confirmed"
        field.confidence = "high"
        field.confirmation = {
            "required": False,
            "confirmed": True,
            "confirmed_by": "user",
            "confirmed_at": _now_iso(),
            "user_note": user_message,
        }

    record = ConfirmationRecord(
        confirmation_id=f"confirm_{len(updated.confirmations) + 1}",
        field_ids=field_ids,
        action="modified",
        values=field_values,
        user_message=user_message,
        rationale_shown=rationale_shown,
        evidence_ids_shown=evidence_ids_shown or [],
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
