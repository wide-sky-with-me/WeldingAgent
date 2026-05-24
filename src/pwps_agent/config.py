from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class LLMSettings(BaseModel):
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    temperature: float = 0.2
    timeout_seconds: int = 120
    structured_output_method: Literal["function_calling", "json_mode", "json_schema"] = (
        "function_calling"
    )
    thinking_type: Literal["", "enabled", "disabled"] = ""


class WebSearchSettings(BaseModel):
    provider: str = "tavily"
    max_results: int = 5
    timeout_seconds: int = 30
    tavily_api_key: str = ""
    tavily_search_depth: Literal["basic", "advanced"] = "basic"
    tavily_include_raw_content: bool = False
    brave_api_key: str = ""
    brave_country: str = "us"
    brave_lang: str = "en"
    brave_safety: str = "moderate"


class PathSettings(BaseModel):
    local_docs_dir: Path = Path("data/local_docs")
    output_dir: Path = Path("data/outputs")
    trace_dir: Path = Path("data/outputs/traces")


class Settings(BaseModel):
    llm: LLMSettings = Field(default_factory=LLMSettings)
    web_search: WebSearchSettings = Field(default_factory=WebSearchSettings)
    paths: PathSettings = Field(default_factory=PathSettings)


def load_settings(env_file: str | Path = ".env") -> Settings:
    values = dict(os.environ)
    values.update(_read_env_file(Path(env_file)))

    return Settings(
        llm=LLMSettings(
            api_key=values.get("LLM_API_KEY") or values.get("OPENAI_API_KEY", ""),
            base_url=values.get("LLM_BASE_URL") or values.get("OPENAI_BASE_URL", ""),
            model=values.get("LLM_MODEL") or values.get("OPENAI_MODEL", ""),
            temperature=_float(values.get("LLM_TEMPERATURE"), 0.2),
            timeout_seconds=_int(values.get("LLM_TIMEOUT_SECONDS"), 120),
            structured_output_method=values.get(
                "LLM_STRUCTURED_OUTPUT_METHOD",
                "function_calling",
            ),
            thinking_type=values.get("LLM_THINKING_TYPE", ""),
        ),
        web_search=WebSearchSettings(
            provider=values.get("WEB_SEARCH_PROVIDER", "tavily"),
            max_results=_int(values.get("WEB_SEARCH_MAX_RESULTS"), 5),
            timeout_seconds=_int(values.get("WEB_SEARCH_TIMEOUT_SECONDS"), 30),
            tavily_api_key=values.get("TAVILY_API_KEY", ""),
            tavily_search_depth=values.get("TAVILY_SEARCH_DEPTH", "basic"),
            tavily_include_raw_content=_bool(values.get("TAVILY_INCLUDE_RAW_CONTENT"), False),
            brave_api_key=values.get("BRAVE_SEARCH_API_KEY", ""),
            brave_country=values.get("BRAVE_SEARCH_COUNTRY", "us"),
            brave_lang=values.get("BRAVE_SEARCH_LANG", "en"),
            brave_safety=values.get("BRAVE_SEARCH_SAFETY", "moderate"),
        ),
        paths=PathSettings(
            local_docs_dir=Path(values.get("PWPS_LOCAL_DOCS_DIR", "data/local_docs")),
            output_dir=Path(values.get("PWPS_OUTPUT_DIR", "data/outputs")),
            trace_dir=Path(values.get("PWPS_TRACE_DIR", "data/outputs/traces")),
        ),
    )


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = _strip_quotes(value.strip())
    return values


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _int(value: str | None, default: int) -> int:
    if value in (None, ""):
        return default
    return int(value)


def _float(value: str | None, default: float) -> float:
    if value in (None, ""):
        return default
    return float(value)


def _bool(value: str | None, default: bool) -> bool:
    if value in (None, ""):
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
