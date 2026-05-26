from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from pwps_agent.agent.prompt_loader import load_prompt
from pwps_agent.core.contracts import ToolResult
from pwps_agent.core.state import PWPSState
from pwps_agent.llm.structured import complete_structured


VALID_PURPOSES = {
    "similar_case",
    "material_reference",
    "filler_reference",
    "parameter_reference",
    "thermal_reference",
    "standard_background",
    "other",
}


class KnowledgeQueryPlan(BaseModel):
    """A targeted knowledge query that supports specific missing or risky pWPS fields."""

    query_id: str | None = Field(
        default=None,
        description="Stable query identifier. Leave empty when the caller should assign one.",
    )
    purpose: str = Field(
        default="other",
        description="Search purpose such as similar_case, filler_reference, or parameter_reference.",
    )
    query_text: str = Field(description="The exact local or web search query to run.")
    target_fields: list[str] = Field(
        default_factory=list,
        description="Field IDs this query is intended to support.",
    )
    rationale: str = Field(description="Why this query is useful for the current state.")
    preferred_sources: list[str] = Field(
        default_factory=lambda: ["web"],
        description="Preferred source types such as local_doc or web.",
    )
    context: dict[str, Any] = Field(
        default_factory=dict,
        description="Small structured context useful for trace and later ranking.",
    )


class KnowledgePlanningOutput(BaseModel):
    """Planned knowledge queries for the next pWPS evidence-gathering step."""

    queries: list[KnowledgeQueryPlan] = Field(
        default_factory=list,
        description="One to three targeted knowledge queries.",
    )


def plan_knowledge_queries(state: PWPSState, client: Any) -> ToolResult:
    errors: list[str] = []
    try:
        output = complete_structured(
            client=client,
            system_prompt=load_prompt("knowledge_planning"),
            user_prompt=_user_prompt(state),
            schema=KnowledgePlanningOutput,
        )
        queries = _normalize_queries([query.model_dump() for query in output.queries])
    except Exception as exc:  # noqa: BLE001 - keep graph running on provider parser failures
        errors = [str(exc)]
        queries = []
    if not queries:
        queries = [_fallback_query(state)]

    return ToolResult(
        tool_name="knowledge_planning",
        success=True,
        state_patch={"knowledge_queries": queries},
        errors=errors,
        summary=f"Planned {len(queries)} knowledge queries.",
    )


def _normalize_queries(raw_queries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    queries: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_queries, start=1):
        query_text = str(raw.get("query_text", "")).strip()
        target_fields = [field for field in raw.get("target_fields", []) if isinstance(field, str)]
        if not query_text or not target_fields:
            continue
        purpose = raw.get("purpose", "other")
        if purpose not in VALID_PURPOSES:
            purpose = "other"
        queries.append(
            {
                "query_id": raw.get("query_id") or f"kq_{index:03d}",
                "purpose": purpose,
                "query_text": query_text,
                "target_fields": target_fields,
                "rationale": raw.get("rationale", ""),
                "preferred_sources": raw.get("preferred_sources", ["web"]),
                "context": raw.get("context", {}),
            }
        )
    return queries


def _fallback_query(state: PWPSState) -> dict[str, Any]:
    known_values = [
        state.core_fields.get("base_material"),
        state.core_fields.get("thickness"),
        state.core_fields.get("welding_process"),
        state.core_fields.get("workpiece_type"),
    ]
    query_text = " ".join(str(value) for value in known_values if value)
    if not query_text:
        query_text = state.user_input
    query_text = f"{query_text} pWPS WPS similar case missing fields"
    return {
        "query_id": "kq_fallback_1",
        "purpose": "similar_case",
        "query_text": query_text,
        "target_fields": _missing_high_value_fields(state),
        "rationale": "Fallback query because model planning returned no usable query.",
        "preferred_sources": ["web"],
        "context": {"fallback": True},
    }


def _missing_high_value_fields(state: PWPSState) -> list[str]:
    priority = [
        "welding_position",
        "filler_material",
        "shielding_gas",
        "current_range",
        "voltage_range",
        "travel_speed",
        "preheat_temperature",
        "interpass_temperature",
    ]
    missing = [
        field_id
        for field_id in priority
        if field_id in state.fields and state.fields[field_id].status == "missing"
    ]
    return missing or ["filler_material", "current_range", "voltage_range"]


def _user_prompt(state: PWPSState) -> str:
    known_fields = {
        field_id: field.value
        for field_id, field in state.fields.items()
        if field.value not in (None, "") and field.status in {"filled", "user_confirmed"}
    }
    missing_fields = [
        field_id for field_id, field in state.fields.items() if field.status == "missing"
    ]
    candidate_fields = [
        field_id
        for field_id, field in state.fields.items()
        if field.status in {"candidate", "suggested", "need_confirmation", "conflict"}
    ]
    quality_report = state.quality_report or {}
    previous_queries = [query.get("query_text") for query in state.knowledge_queries]
    return "\n".join(
        [
            f"user_input: {state.user_input}",
            f"known_fields: {known_fields}",
            f"core_fields: {state.core_fields}",
            f"missing_fields: {missing_fields}",
            f"candidate_or_risk_fields: {candidate_fields}",
            f"quality_refinement_focus_fields: {quality_report.get('refinement_focus_fields', [])}",
            f"quality_critical_missing_fields: {quality_report.get('critical_missing_fields', [])}",
            f"quality_weak_evidence_fields: {quality_report.get('weak_evidence_fields', [])}",
            f"previous_query_texts: {previous_queries}",
        ]
    )
