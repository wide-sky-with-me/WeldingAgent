from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from pwps_agent.core.contracts import ToolResult
from pwps_agent.core.modes import GUIDED_CORE_CONFIRMATION_FIELDS
from pwps_agent.core.state import PWPSState


class GuidedOption(BaseModel):
    value: Any
    suitability: str
    risk_note: str
    recommended: bool = False
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: str = "unknown"


class GuidedOptionSet(BaseModel):
    field_id: str
    question: str
    options: list[GuidedOption]
    requires_user_confirmation: bool = True


def build_guided_options(state: PWPSState, _client: object | None = None) -> ToolResult:
    option_sets = [_option_set_for_field(state, field_id) for field_id in _target_fields(state)]
    option_sets = [option_set for option_set in option_sets if option_set is not None]
    fields_patch: dict[str, dict[str, Any]] = {}
    for option_set in option_sets:
        fields_patch.update(merge_guided_option_set(option_set)["fields"])
    return ToolResult(
        tool_name="guided_options",
        success=True,
        state_patch={"fields": fields_patch},
        summary=f"Prepared guided options for {len(option_sets)} fields.",
    )


def merge_guided_option_set(option_set: GuidedOptionSet) -> dict[str, Any]:
    return {
        "fields": {
            option_set.field_id: {
                "status": "need_confirmation",
                "candidates": [option.model_dump() for option in option_set.options],
                "confirmation": {
                    "required": option_set.requires_user_confirmation,
                    "confirmed": False,
                    "question": option_set.question,
                },
                "source": {"type": "llm_guided_options"},
                "note": option_set.question,
            }
        }
    }


def _target_fields(state: PWPSState) -> list[str]:
    target: list[str] = []
    for field_id in GUIDED_CORE_CONFIRMATION_FIELDS:
        field = state.fields[field_id]
        if field.status in {"missing", "candidate", "suggested", "need_confirmation", "conflict"} or field.candidates:
            target.append(field_id)
    for field_id in ("filler_material", "shielding_gas", "preheat_temperature", "pwht"):
        field = state.fields[field_id]
        if field.status in {"candidate", "suggested", "need_confirmation", "conflict"} or field.candidates:
            target.append(field_id)
    return list(dict.fromkeys(target))


def _option_set_for_field(state: PWPSState, field_id: str) -> GuidedOptionSet | None:
    field = state.fields[field_id]
    options = [
        GuidedOption(
            value=candidate.get("value"),
            suitability=str(candidate.get("suitability") or candidate.get("note") or "Candidate from current evidence."),
            risk_note=str(candidate.get("risk_note") or "Confirm against project requirements before promotion."),
            recommended=bool(candidate.get("recommended", index == 0)),
            evidence_ids=list(candidate.get("evidence_ids") or []),
            confidence=str(candidate.get("confidence") or field.confidence),
        )
        for index, candidate in enumerate(field.candidates)
        if candidate.get("value") not in (None, "")
    ]
    if not options and field.value not in (None, ""):
        options.append(
            GuidedOption(
                value=field.value,
                suitability="Current field value proposed by the agent.",
                risk_note="Confirm against project requirements before promotion.",
                recommended=True,
                evidence_ids=list(field.evidence_ids),
                confidence=field.confidence,
            )
        )
    if not options and field_id == "welding_process":
        options = [
            GuidedOption(
                value="GMAW",
                suitability="High productivity option for plate and shop welding when shielding gas is available.",
                risk_note="Confirm shielding gas, transfer mode, and project/process constraints.",
                recommended=True,
            ),
            GuidedOption(
                value="SMAW",
                suitability="Flexible for site, repair, or lower-equipment scenarios.",
                risk_note="Lower productivity and electrode control need review.",
            ),
        ]
    if not options:
        return None
    return GuidedOptionSet(
        field_id=field_id,
        question=f"Confirm {field.label}.",
        options=options,
        requires_user_confirmation=True,
    )
