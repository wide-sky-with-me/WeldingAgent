import json

from pwps_agent.config import LLMSettings
from pwps_agent.llm.openai_compatible import OpenAICompatibleClient


class RecordingTransport:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls: list[dict] = []

    def post_json(
        self,
        url: str,
        payload: dict,
        headers: dict[str, str],
        timeout: int,
    ) -> dict:
        self.calls.append(
            {
                "url": url,
                "payload": payload,
                "headers": headers,
                "timeout": timeout,
            }
        )
        return self.payload


def test_openai_compatible_client_posts_chat_completions_payload() -> None:
    transport = RecordingTransport(
        {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({"ok": True}),
                    }
                }
            ]
        }
    )
    client = OpenAICompatibleClient(
        LLMSettings(
            api_key="secret",
            base_url="https://llm.example/v1/",
            model="compat-model",
            temperature=0.1,
            timeout_seconds=45,
        ),
        transport=transport,
    )

    content = client.complete_json(
        system_prompt="Return JSON.",
        user_prompt="Extract fields.",
    )

    assert content == {"ok": True}
    call = transport.calls[0]
    assert call["url"] == "https://llm.example/v1/chat/completions"
    assert call["headers"]["Authorization"] == "Bearer secret"
    assert call["payload"]["model"] == "compat-model"
    assert call["payload"]["temperature"] == 0.1
    assert call["payload"]["response_format"] == {"type": "json_object"}
    assert call["timeout"] == 45


def test_openai_compatible_client_rejects_missing_model_settings() -> None:
    client = OpenAICompatibleClient(LLMSettings(api_key="", base_url="", model=""))

    try:
        client.complete_json("system", "user")
    except ValueError as exc:
        assert "LLM_API_KEY" in str(exc)
        assert "LLM_BASE_URL" in str(exc)
        assert "LLM_MODEL" in str(exc)
    else:
        raise AssertionError("Expected missing configuration failure")
