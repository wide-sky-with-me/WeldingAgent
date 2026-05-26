from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from pwps_agent.agent.prompt_loader import load_prompt
from pwps_agent.llm.structured import StructuredOutputClient, complete_structured


class InteractionResponseUnderstandingOutput(BaseModel):
    """Fields extracted from a free-form runtime interaction response."""

    fields: dict[str, Any] = Field(
        default_factory=dict,
        description="Requested pWPS field values explicitly present in the user's reply.",
    )
    missing_field_ids: list[str] = Field(
        default_factory=list,
        description="Requested field IDs still missing after reading the user's reply.",
    )
    follow_up_message: str = Field(
        default="",
        description="Natural follow-up question when requested fields are still missing.",
    )


def understand_interaction_response(
    interaction: dict,
    raw_text: str,
    client: StructuredOutputClient,
) -> dict[str, Any]:
    requested_field_ids = _requested_field_ids(interaction)
    output = complete_structured(
        client=client,
        system_prompt=load_prompt("interaction_response_understanding"),
        user_prompt=_user_prompt(interaction, raw_text, requested_field_ids),
        schema=InteractionResponseUnderstandingOutput,
    )
    fields = {
        str(field_id): value
        for field_id, value in output.fields.items()
        if str(field_id) in requested_field_ids and value not in (None, "")
    }
    missing = [
        field_id
        for field_id in requested_field_ids
        if field_id not in fields and field_id in set(output.missing_field_ids or requested_field_ids)
    ]
    if not missing:
        missing = [field_id for field_id in requested_field_ids if field_id not in fields]
    return {
        "fields": fields,
        "missing_field_ids": missing,
        "follow_up_message": output.follow_up_message.strip(),
    }


def _user_prompt(interaction: dict, raw_text: str, requested_field_ids: list[str]) -> str:
    title = interaction.get("title") or ""
    summary = interaction.get("summary") or ""
    questions = interaction.get("questions") or []
    prompts = [str(question.get("prompt") or "") for question in questions if isinstance(question, dict)]
    return "\n".join(
        [
            f"Interaction purpose: {interaction.get('purpose') or ''}",
            f"Title: {title}",
            f"Summary: {summary}",
            f"Requested field IDs: {', '.join(requested_field_ids)}",
            "Question prompts:",
            "\n".join(f"- {prompt}" for prompt in prompts if prompt),
            "User reply:",
            raw_text,
        ]
    ).strip()


def _requested_field_ids(interaction: dict) -> list[str]:
    field_ids: list[str] = []
    for question in interaction.get("questions") or []:
        if not isinstance(question, dict):
            if hasattr(question, "model_dump"):
                question = question.model_dump()
            else:
                question = dict(question)
        for field_id in question.get("field_ids") or []:
            field_id = str(field_id)
            if field_id not in field_ids:
                field_ids.append(field_id)
    return field_ids
