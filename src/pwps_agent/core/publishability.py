from __future__ import annotations

from typing import Literal

from pwps_agent.core.fields import FieldState


Publishability = Literal[
    "draft_publishable",
    "needs_confirmation",
    "reference_only",
    "blocked",
]

BLOCKED_METADATA_FIELDS = {
    "pwps_no",
    "revision_no",
    "date",
    "company",
    "project_name",
    "client",
    "contract_no",
}


def publishability_for_field(field: FieldState) -> Publishability:
    source_type = _source_type(field)
    if field.status == "user_confirmed":
        return "draft_publishable"
    if field.status == "filled" and source_type in {None, "user_input", "user_confirmation"}:
        return "draft_publishable"
    if field.field_id in BLOCKED_METADATA_FIELDS and source_type not in {
        "user_input",
        "user_confirmation",
    }:
        if field.value not in (None, "") or field.candidates:
            return "blocked"
    if field.status in {"candidate", "suggested", "need_confirmation", "conflict"}:
        if source_type in {"web", "local_doc", "model_fallback", "llm"}:
            return "reference_only" if field.status in {"candidate", "suggested"} else "needs_confirmation"
        return "needs_confirmation"
    if field.status == "filled" and source_type not in {"user_input", "user_confirmation"}:
        return "needs_confirmation"
    if field.status == "missing":
        return "needs_confirmation"
    return "reference_only"


def _source_type(field: FieldState) -> str | None:
    if not field.source:
        return None
    value = field.source.get("type") or field.source.get("source_type")
    return str(value) if value else None
