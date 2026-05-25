from pathlib import Path

from pwps_agent.config import load_settings


EXPECTED_ENV_TEMPLATE_KEYS = {
    "LLM_API_KEY",
    "LLM_BASE_URL",
    "LLM_MODEL",
    "LLM_TEMPERATURE",
    "LLM_TIMEOUT_SECONDS",
    "LLM_STRUCTURED_OUTPUT_METHOD",
    "LLM_THINKING_TYPE",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OPENAI_MODEL",
    "KNOWLEDGE_SOURCES",
    "SUPERVISOR_PLANNER",
    "WEB_SEARCH_PROVIDER",
    "WEB_SEARCH_MAX_RESULTS",
    "WEB_SEARCH_TIMEOUT_SECONDS",
    "WEB_SEARCH_MAX_RETRIES",
    "WEB_SEARCH_RETRY_BACKOFF_SECONDS",
    "WEB_SEARCH_CACHE_ENABLED",
    "TAVILY_API_KEY",
    "TAVILY_SEARCH_DEPTH",
    "TAVILY_INCLUDE_RAW_CONTENT",
    "BRAVE_SEARCH_API_KEY",
    "BRAVE_SEARCH_COUNTRY",
    "BRAVE_SEARCH_LANG",
    "BRAVE_SEARCH_SAFETY",
    "PWPS_LOCAL_DOCS_DIR",
    "LOCAL_DOC_MAX_RESULTS",
    "LOCAL_DOC_SNIPPET_CHARS",
    "PWPS_OUTPUT_DIR",
    "PWPS_TRACE_DIR",
}


def test_loads_provider_neutral_llm_settings_from_env_file(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "LLM_API_KEY=secret-key",
                "LLM_BASE_URL=https://llm.example/v1",
                "LLM_MODEL=compat-model",
                "LLM_TEMPERATURE=0.1",
                "LLM_STRUCTURED_OUTPUT_METHOD=function_calling",
                "LLM_THINKING_TYPE=disabled",
                "SUPERVISOR_PLANNER=llm",
                "WEB_SEARCH_PROVIDER=brave",
                "BRAVE_SEARCH_API_KEY=brave-key",
            ]
        ),
        encoding="utf-8",
    )

    settings = load_settings(env_file)

    assert settings.llm.api_key == "secret-key"
    assert settings.llm.base_url == "https://llm.example/v1"
    assert settings.llm.model == "compat-model"
    assert settings.llm.temperature == 0.1
    assert settings.llm.structured_output_method == "function_calling"
    assert settings.llm.thinking_type == "disabled"
    assert settings.supervisor.planner == "llm"
    assert settings.web_search.provider == "brave"
    assert settings.web_search.brave_api_key == "brave-key"


def test_supervisor_planner_defaults_to_deterministic(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")

    settings = load_settings(env_file)

    assert settings.supervisor.planner == "deterministic"


def test_loads_configured_knowledge_source_order(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("KNOWLEDGE_SOURCES=web,model\n", encoding="utf-8")

    settings = load_settings(env_file)

    assert settings.knowledge.sources == ["web", "model"]
    assert settings.knowledge.local_doc_enabled is False
    assert settings.knowledge.web_enabled is True
    assert settings.knowledge.model_fallback_enabled is True


def test_openai_aliases_do_not_override_provider_neutral_settings(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "LLM_API_KEY=neutral-key",
                "LLM_BASE_URL=https://neutral.example/v1",
                "LLM_MODEL=neutral-model",
                "OPENAI_API_KEY=openai-key",
                "OPENAI_BASE_URL=https://openai.example/v1",
                "OPENAI_MODEL=openai-model",
            ]
        ),
        encoding="utf-8",
    )

    settings = load_settings(env_file)

    assert settings.llm.api_key == "neutral-key"
    assert settings.llm.base_url == "https://neutral.example/v1"
    assert settings.llm.model == "neutral-model"


def test_env_template_documents_all_supported_environment_keys() -> None:
    template = Path(".env.template").read_text(encoding="utf-8")
    documented_keys = {
        line.split("=", 1)[0].strip()
        for line in template.splitlines()
        if line.strip() and not line.lstrip().startswith("#") and "=" in line
    }

    assert documented_keys == EXPECTED_ENV_TEMPLATE_KEYS
