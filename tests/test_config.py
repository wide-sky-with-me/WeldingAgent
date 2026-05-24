from pathlib import Path

from pwps_agent.config import load_settings


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
