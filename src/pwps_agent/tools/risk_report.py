from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from pwps_agent.core.state import PWPSState
from pwps_agent.core.contracts import ToolResult
from pwps_agent.core.evidence_policy import evidence_strength, may_promote_candidate


THERMAL_FIELDS = {
    "preheat_temperature",
    "interpass_temperature",
    "post_heat",
    "pwht",
    "holding_temperature",
    "holding_time",
}

KEY_CHOICE_FIELDS = {
    "applicable_standard",
    "base_material",
    "workpiece_type",
    "welding_process",
    "joint_type",
    "welding_position",
    "filler_material",
    "shielding_gas",
    "preheat_temperature",
    "interpass_temperature",
    "pwht",
}


class RiskItem(BaseModel):
    field_id: str
    risk_type: str
    severity: str
    message: str
    evidence_ids: list[str]


def generate_risk_report(state: PWPSState) -> ToolResult:
    risks = _risk_items(state)
    report = _field_report(state, risks)
    return ToolResult(
        tool_name="risk_report",
        success=True,
        state_patch={
            "field_report": report,
            "risks": [risk.model_dump() for risk in risks],
        },
        summary=f"Generated risk report with {len(risks)} risk items.",
    )


def _risk_items(state: PWPSState) -> list[RiskItem]:
    risks: list[RiskItem] = []
    evidence_by_id = {item.evidence_id: item for item in state.evidence}
    for field in state.fields.values():
        linked_evidence = [
            evidence_by_id[evidence_id]
            for evidence_id in field.evidence_ids
            if evidence_id in evidence_by_id
        ]
        if field.status == "missing":
            risks.append(
                RiskItem(
                    field_id=field.field_id,
                    risk_type="missing_field",
                    severity="medium",
                    message=f"{field.label} is missing and needs confirmation.",
                    evidence_ids=list(field.evidence_ids),
                )
            )
        if field.confidence == "low":
            risks.append(
                RiskItem(
                    field_id=field.field_id,
                    risk_type="low_confidence",
                    severity="medium",
                    message=f"{field.label} has low confidence and should be reviewed.",
                    evidence_ids=list(field.evidence_ids),
                )
            )
        if field.field_id in THERMAL_FIELDS and field.status in {"missing", "candidate", "suggested", "need_confirmation"}:
            risks.append(
                RiskItem(
                    field_id=field.field_id,
                    risk_type="thermal_control",
                    severity="high",
                    message=f"{field.label} is thermal-control sensitive and needs source-backed confirmation.",
                    evidence_ids=list(field.evidence_ids),
                )
            )
        if field.status in {"candidate", "suggested"} and any(
            evidence_by_id.get(evidence_id)
            and evidence_by_id[evidence_id].source_type == "web"
            for evidence_id in field.evidence_ids
        ):
            risks.append(
                RiskItem(
                    field_id=field.field_id,
                    risk_type="web_reference_only",
                    severity="medium",
                    message=f"{field.label} is based on web reference only; treat as candidate, not verified fact.",
                    evidence_ids=list(field.evidence_ids),
                )
            )
        if field.status in {"candidate", "suggested", "need_confirmation"}:
            strength = evidence_strength(linked_evidence)
            if strength == "weak":
                risks.append(
                    RiskItem(
                        field_id=field.field_id,
                        risk_type="weak_evidence",
                        severity="medium",
                        message=f"{field.label} is supported only by weak or missing evidence.",
                        evidence_ids=list(field.evidence_ids),
                    )
                )
            if not may_promote_candidate(
                linked_evidence,
                requires_human_confirmation=field.field_id in KEY_CHOICE_FIELDS
                or state.interaction_mode == "guided_confirmation",
            ):
                risks.append(
                    RiskItem(
                        field_id=field.field_id,
                        risk_type="confirmation_required",
                        severity="high" if field.field_id in KEY_CHOICE_FIELDS else "medium",
                        message=f"{field.label} must remain draft-only until confirmed.",
                        evidence_ids=list(field.evidence_ids),
                    )
                )
    return _dedupe_risks(risks)


def _field_report(state: PWPSState, risks: list[RiskItem]) -> dict[str, Any]:
    missing = []
    candidate = []
    suggested = []
    user_confirmed = []
    conflict = []
    retained_candidates = {}

    for field in state.fields.values():
        if field.status == "missing":
            missing.append(field.field_id)
        elif field.status == "candidate":
            candidate.append(field.field_id)
        elif field.status == "suggested":
            suggested.append(field.field_id)
        elif field.status == "user_confirmed":
            user_confirmed.append(field.field_id)
        elif field.status == "conflict":
            conflict.append(field.field_id)
        if field.candidates:
            retained_candidates[field.field_id] = list(field.candidates)

    return {
        "summary": {
            "field_count": len(state.fields),
            "interaction_mode": state.interaction_mode,
            "risk_count": len(risks),
        },
        "missing_fields": missing,
        "candidate_fields": candidate,
        "suggested_fields": suggested,
        "user_confirmed_fields": user_confirmed,
        "conflict_fields": conflict,
        "retained_candidates": retained_candidates,
        "evidence_map": {
            field.field_id: list(field.evidence_ids)
            for field in state.fields.values()
            if field.evidence_ids
        },
        "risks": [risk.model_dump() for risk in risks],
        "notes": ["This report describes draft field status only."],
    }


def _dedupe_risks(risks: list[RiskItem]) -> list[RiskItem]:
    seen = set()
    deduped = []
    for risk in risks:
        key = (risk.field_id, risk.risk_type)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(risk)
    return deduped
