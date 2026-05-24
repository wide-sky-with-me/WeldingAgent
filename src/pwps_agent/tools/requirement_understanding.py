from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from pwps_agent.agent.prompt_loader import load_prompt
from pwps_agent.core.contracts import ToolResult
from pwps_agent.core.state import PWPSState
from pwps_agent.llm.structured import StructuredOutputClient, complete_structured


CORE_FIELD_IDS = {
    "applicable_standard",
    "standard_year",
    "base_material",
    "base_material_standard",
    "thickness",
    "workpiece_type",
    "diameter",
    "welding_process",
    "joint_type",
    "groove_type",
    "welding_position",
    "service_condition",
}


class RequirementUnderstandingOutput(BaseModel):
    """Core pWPS fields extracted from the user's welding requirement."""

    core_fields: dict[str, Any] = Field(
        default_factory=dict,
        description="Core pWPS fields explicitly present in the user requirement.",
    )
    missing_core_fields: list[str] = Field(
        default_factory=list,
        description="Important core field IDs that are not provided or cannot be inferred safely.",
    )


def understand_requirement(
    state: PWPSState,
    client: StructuredOutputClient,
) -> ToolResult:
    output = complete_structured(
        client=client,
        system_prompt=load_prompt("requirement_understanding"),
        user_prompt=f"User requirement:\n{state.user_input}",
        schema=RequirementUnderstandingOutput,
    )
    core_fields = {
        key: value
        for key, value in output.core_fields.items()
        if key in CORE_FIELD_IDS and value not in (None, "")
    }
    core_fields.update(_normalize_explicit_user_fields(state.user_input, core_fields))
    field_patch = _field_patch_from_core_fields(state, core_fields)
    missing_core_fields = output.missing_core_fields

    return ToolResult(
        tool_name="requirement_understanding",
        success=True,
        state_patch={
            "core_fields": core_fields,
            "fields": field_patch,
            "clarification_questions": [
                {"field_id": field_id, "question": f"请确认 {field_id}。"}
                for field_id in missing_core_fields
            ],
        },
        summary="Extracted core pWPS fields from user requirement.",
    )


def _field_patch_from_core_fields(
    state: PWPSState,
    core_fields: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    patch: dict[str, dict[str, Any]] = {}
    for field_id, value in core_fields.items():
        if field_id not in state.fields:
            continue
        patch[field_id] = {
            "value": value,
            "status": "filled",
            "confidence": "high",
            "source": {"type": "user_input", "ref": "ev_user_input_1"},
            "evidence_ids": ["ev_user_input_1"],
        }
    return patch


def _normalize_explicit_user_fields(
    user_input: str,
    existing: dict[str, Any],
) -> dict[str, str]:
    normalized: dict[str, str] = {}

    if not existing.get("base_material"):
        material = re.search(r"\b([A-Z]{1,4}\d{2,4}[A-Z]?)\b", user_input)
        if material:
            value = material.group(1)
            if value.upper() not in {"GMAW", "SMAW", "GTAW", "FCAW", "SAW"}:
                normalized["base_material"] = value

    if not existing.get("applicable_standard"):
        standard = re.search(r"\b(AWS\s+D\d+(?:\.\d+)?)\b", user_input, flags=re.IGNORECASE)
        if standard:
            normalized["applicable_standard"] = re.sub(r"\s+", " ", standard.group(1)).upper()

    if not existing.get("thickness"):
        thickness = re.search(r"\b(\d+(?:\.\d+)?)\s*(mm|毫米)\b", user_input, flags=re.IGNORECASE)
        if thickness:
            normalized["thickness"] = f"{thickness.group(1)}{thickness.group(2).lower()}"

    if not existing.get("welding_process"):
        process = re.search(r"\b(GMAW|SMAW|GTAW|FCAW|SAW)\b", user_input, flags=re.IGNORECASE)
        if process:
            normalized["welding_process"] = process.group(1).upper()

    if not existing.get("joint_type"):
        lowered = user_input.lower()
        if "butt joint" in lowered or "对接" in user_input:
            normalized["joint_type"] = "butt joint"

    if not existing.get("welding_position"):
        lowered = user_input.lower()
        if "flat" in lowered or "平焊" in user_input:
            normalized["welding_position"] = "flat"

    if not existing.get("workpiece_type"):
        if "板材" in user_input or "板" in user_input.lower() or "plate" in user_input.lower():
            normalized["workpiece_type"] = "plate"
        elif "管材" in user_input or "管" in user_input.lower() or "pipe" in user_input.lower():
            normalized["workpiece_type"] = "pipe"

    return normalized
