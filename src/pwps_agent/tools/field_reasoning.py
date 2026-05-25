from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from pwps_agent.agent.prompt_loader import load_prompt
from pwps_agent.core.contracts import Evidence, ToolResult
from pwps_agent.core.state import PWPSState
from pwps_agent.llm.structured import complete_structured

BLOCKED_INFERRED_FIELDS = {
    "pwps_no",
    "revision_no",
    "date",
    "company",
    "project_name",
    "client",
    "contract_no",
}


class FieldCandidateOutput(BaseModel):
    """A traceable candidate value for a pWPS field derived from evidence."""

    field_id: str = Field(description="Target pWPS field ID.")
    value: Any = Field(description="Candidate field value derived from evidence.")
    status: str = Field(
        default="candidate",
        description="candidate, suggested, or need_confirmation.",
    )
    confidence: str = Field(
        default="unknown",
        description="Confidence label: high, medium, low, or unknown.",
    )
    evidence_ids: list[str] = Field(
        default_factory=list,
        description="Evidence IDs supporting this candidate.",
    )
    note: str | None = Field(
        default=None,
        description="Short explanation and confirmation/risk note for the candidate.",
    )


class FieldReasoningOutput(BaseModel):
    """Field candidates reasoned from pWPS evidence."""

    candidates: list[FieldCandidateOutput] = Field(
        default_factory=list,
        description="Candidate field values with evidence links.",
    )


def infer_candidates_from_evidence(evidence: list[Evidence]) -> dict[str, dict[str, Any]]:
    candidates: dict[str, dict[str, Any]] = {}
    for item in evidence:
        text = item.content.upper()
        if "ER50-6" in text and "filler_material" not in candidates:
            candidates["filler_material"] = {
                "value": "ER50-6",
                "evidence_ids": [item.evidence_id],
                "note": "Candidate filler material inferred from web evidence.",
            }
    return candidates


def apply_field_candidates(
    state: PWPSState,
    candidates: dict[str, dict[str, Any]],
) -> PWPSState:
    updated = state.model_copy(deep=True)
    for field_id, candidate in candidates.items():
        if field_id not in updated.fields:
            continue
        field = updated.fields[field_id]
        if _has_user_priority(field):
            field.candidates.append(
                {
                    "value": candidate.get("value"),
                    "status": "candidate",
                    "evidence_ids": list(candidate.get("evidence_ids", [])),
                    "note": candidate.get("note"),
                }
            )
            continue
        field.value = candidate.get("value")
        field.status = "candidate"
        field.confidence = "medium"
        field.note = candidate.get("note")
        field.evidence_ids = list(candidate.get("evidence_ids", []))
        field.source = {"type": "web", "evidence_ids": field.evidence_ids}
        field.confirmation = {"required": True, "confirmed": False}
        field.candidates.append(
            {
                "value": field.value,
                "status": "candidate",
                "evidence_ids": field.evidence_ids,
                "note": field.note,
            }
        )
    return updated


def _has_user_priority(field: Any) -> bool:
    source_type = (field.source or {}).get("type")
    return field.status == "user_confirmed" or field.status == "filled" and source_type in {
        None,
        "user_input",
        "user_confirmation",
    }


def reason_fields_from_evidence(
    state: PWPSState,
    evidence: list[Evidence],
    client: Any,
) -> ToolResult:
    output = complete_structured(
        client=client,
        system_prompt=load_prompt("field_reasoning"),
        user_prompt=_field_reasoning_user_prompt(state, evidence),
        schema=FieldReasoningOutput,
    )
    fields: dict[str, dict[str, Any]] = {}
    for candidate_output in output.candidates:
        candidate = candidate_output.model_dump()
        field_id = candidate["field_id"]
        if not field_id or field_id not in state.fields or field_id in BLOCKED_INFERRED_FIELDS:
            continue
        value = candidate.get("value")
        if value in (None, ""):
            continue
        if isinstance(value, str) and value.strip().lower() in {
            "candidate",
            "suggested",
            "need_confirmation",
            "missing",
            "unknown",
            "待确认",
        }:
            continue
        fields[field_id] = {
            "value": value,
            "status": candidate.get("status", "candidate"),
            "confidence": candidate.get("confidence", "unknown"),
            "evidence_ids": list(candidate.get("evidence_ids", [])),
            "note": candidate.get("note"),
            "source": {
                "type": "web",
                "evidence_ids": list(candidate.get("evidence_ids", [])),
            },
            "confirmation": {"required": True, "confirmed": False},
        }

    return ToolResult(
        tool_name="field_reasoning",
        success=True,
        state_patch={"fields": fields},
        summary=f"Generated {len(fields)} candidate fields from evidence.",
    )


def _field_reasoning_user_prompt(state: PWPSState, evidence: list[Evidence]) -> str:
    lines = [
        "Core fields:",
        str(state.core_fields),
        "",
        "Evidence:",
    ]
    for item in evidence:
        lines.append(f"- {item.evidence_id} [{item.source_type}] {item.content[:1500]}")
    return "\n".join(lines)
