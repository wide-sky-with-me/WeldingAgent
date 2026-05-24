from __future__ import annotations

import json
from typing import Protocol, TypeVar
from urllib.request import Request, urlopen

from pydantic import BaseModel

from pwps_agent.config import LLMSettings

StructuredModelT = TypeVar("StructuredModelT", bound=BaseModel)


class JsonPostTransport(Protocol):
    def post_json(
        self,
        url: str,
        payload: dict,
        headers: dict[str, str],
        timeout: int,
    ) -> dict:
        ...


class UrllibJsonTransport:
    def post_json(
        self,
        url: str,
        payload: dict,
        headers: dict[str, str],
        timeout: int,
    ) -> dict:
        body = json.dumps(payload).encode("utf-8")
        request = Request(url, data=body, headers=headers, method="POST")
        with urlopen(request, timeout=timeout) as response:  # nosec B310 - configured LLM endpoint
            return json.loads(response.read().decode("utf-8"))


class OpenAICompatibleClient:
    def __init__(
        self,
        settings: LLMSettings,
        transport: JsonPostTransport | None = None,
    ) -> None:
        self.settings = settings
        self.transport = transport or UrllibJsonTransport()

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        self._validate_settings()
        payload = {
            "model": self.settings.model,
            "temperature": self.settings.temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.settings.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        response = self.transport.post_json(
            url=f"{self.settings.base_url.rstrip('/')}/chat/completions",
            payload=payload,
            headers=headers,
            timeout=self.settings.timeout_seconds,
        )
        content = response["choices"][0]["message"]["content"]
        return json.loads(content)

    def complete_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: type[StructuredModelT],
    ) -> StructuredModelT:
        payload = self.complete_json(system_prompt=system_prompt, user_prompt=user_prompt)
        return schema.model_validate(payload)

    def _validate_settings(self) -> None:
        missing = []
        if not self.settings.api_key:
            missing.append("LLM_API_KEY")
        if not self.settings.base_url:
            missing.append("LLM_BASE_URL")
        if not self.settings.model:
            missing.append("LLM_MODEL")
        if missing:
            raise ValueError(f"Missing LLM settings: {', '.join(missing)}")
