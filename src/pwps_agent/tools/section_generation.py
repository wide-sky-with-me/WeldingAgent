from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from pwps_agent.core.fields import FIELD_DEFINITIONS
from pwps_agent.core.state import PWPSState
from pwps_agent.core.contracts import ToolResult
from pwps_agent.render.markdown import SECTION_TITLES


class SectionField(BaseModel):
    field_id: str
    label: str
    value: Any
    status: str
    confidence: str
    evidence_ids: list[str] = Field(default_factory=list)
    source: dict[str, Any] | None = None
    note: str = ""


class GeneratedSection(BaseModel):
    section: str
    title: str
    fields: list[SectionField]


def generate_sections(state: PWPSState) -> ToolResult:
    sections: dict[str, dict[str, Any]] = {}
    for section_id, definitions in FIELD_DEFINITIONS.items():
        fields = []
        for field_id, _label in definitions:
            field = state.fields[field_id]
            fields.append(
                SectionField(
                    field_id=field.field_id,
                    label=field.label,
                    value="待确认" if field.value in (None, "") else field.value,
                    status=field.status,
                    confidence=field.confidence,
                    evidence_ids=list(field.evidence_ids),
                    source=field.source,
                    note=field.note or "",
                )
            )
        sections[section_id] = GeneratedSection(
            section=section_id,
            title=SECTION_TITLES[section_id],
            fields=fields,
        ).model_dump()

    return ToolResult(
        tool_name="section_generation",
        success=True,
        state_patch={"sections": sections},
        summary="Generated structured A/B/C/D/E draft sections.",
    )
