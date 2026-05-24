from __future__ import annotations

from typing import Any, Protocol, TypeVar

from pydantic import BaseModel


StructuredModelT = TypeVar("StructuredModelT", bound=BaseModel)


class StructuredOutputClient(Protocol):
    def complete_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: type[StructuredModelT],
    ) -> StructuredModelT:
        ...


def complete_structured(
    client: Any,
    system_prompt: str,
    user_prompt: str,
    schema: type[StructuredModelT],
) -> StructuredModelT:
    if hasattr(client, "complete_structured"):
        return client.complete_structured(system_prompt, user_prompt, schema)
    payload = client.complete_json(system_prompt=system_prompt, user_prompt=user_prompt)
    return schema.model_validate(payload)
