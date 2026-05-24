from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel

from pwps_agent.config import LLMSettings


StructuredModelT = TypeVar("StructuredModelT", bound=BaseModel)


class LangChainStructuredClient:
    def __init__(self, settings: LLMSettings, chat_model: Any | None = None) -> None:
        self.settings = settings
        self._chat_model = chat_model

    def complete_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: type[StructuredModelT],
    ) -> StructuredModelT:
        self._validate_settings()
        structured_llm = self._model().with_structured_output(
            schema,
            method=self.settings.structured_output_method,
        )
        result = structured_llm.invoke(
            [
                ("system", system_prompt),
                ("user", user_prompt),
            ]
        )
        return schema.model_validate(result)

    def _model(self) -> Any:
        if self._chat_model is not None:
            return self._chat_model

        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            raise RuntimeError(
                "langchain-openai is required for LangChain structured output. "
                "Install dependencies with `uv sync`."
            ) from exc

        kwargs = {
            "model": self.settings.model,
            "api_key": self.settings.api_key,
            "base_url": self.settings.base_url,
            "temperature": self.settings.temperature,
            "timeout": self.settings.timeout_seconds,
        }
        if self.settings.thinking_type:
            kwargs["extra_body"] = {"thinking": {"type": self.settings.thinking_type}}
        self._chat_model = ChatOpenAI(**kwargs)
        return self._chat_model

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
