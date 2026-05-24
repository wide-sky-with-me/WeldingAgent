import json
from urllib.error import HTTPError

import pytest

from pwps_agent.config import WebSearchSettings
from pwps_agent.knowledge.web_search_provider import (
    BraveSearchProvider,
    TavilySearchProvider,
    build_web_search_provider,
)


def test_build_web_search_provider_requires_real_provider_api_key() -> None:
    settings = WebSearchSettings(provider="tavily", tavily_api_key="")

    with pytest.raises(ValueError, match="TAVILY_API_KEY"):
        build_web_search_provider(settings)


def test_build_web_search_provider_rejects_unknown_provider() -> None:
    settings = WebSearchSettings(provider="unknown")

    with pytest.raises(ValueError, match="Unsupported web search provider"):
        build_web_search_provider(settings)


def test_tavily_response_parses_to_search_results() -> None:
    payload = {
        "results": [
            {
                "title": "WPS Example",
                "url": "https://example.com/wps",
                "content": "GMAW Q355B example.",
                "raw_content": "Long content",
                "score": 0.91,
            }
        ]
    }

    results = TavilySearchProvider.parse_response(
        query_id="kq_1",
        payload=payload,
    )

    assert results[0].provider == "tavily"
    assert results[0].url == "https://example.com/wps"
    assert results[0].snippet == "GMAW Q355B example."


def test_brave_response_parses_to_search_results() -> None:
    payload = {
        "web": {
            "results": [
                {
                    "title": "WPS Example",
                    "url": "https://example.com/wps",
                    "description": "GMAW Q355B example.",
                }
            ]
        }
    }

    results = BraveSearchProvider.parse_response(
        query_id="kq_1",
        payload=payload,
    )

    assert results[0].provider == "brave"
    assert results[0].url == "https://example.com/wps"
    assert results[0].snippet == "GMAW Q355B example."


def test_http_error_message_redacts_response_body() -> None:
    error = HTTPError(
        url="https://api.example/search",
        code=401,
        msg="Unauthorized",
        hdrs=None,
        fp=None,
    )

    assert "Unauthorized" in str(error)
    assert json.dumps({"secret": "value"}) not in str(error)


def test_tavily_provider_caches_results_by_query_text(monkeypatch) -> None:
    settings = WebSearchSettings(provider="tavily", tavily_api_key="key")
    calls = []

    def fake_post_json(url, payload, timeout):
        calls.append(payload["query"])
        return {
            "results": [
                {
                    "title": "Cached WPS",
                    "url": "https://example.com/cached",
                    "content": "cached content",
                    "score": 0.8,
                }
            ]
        }

    monkeypatch.setattr("pwps_agent.knowledge.web_search_provider._post_json", fake_post_json)
    provider = TavilySearchProvider(settings)

    first = provider.search("Q355B GMAW WPS", "kq_1")
    second = provider.search("Q355B GMAW WPS", "kq_2")

    assert calls == ["Q355B GMAW WPS"]
    assert first[0].result_id == "kq_1_tavily_1"
    assert second[0].result_id == "kq_2_tavily_1"


def test_tavily_provider_retries_transient_failures_with_backoff(monkeypatch) -> None:
    settings = WebSearchSettings(
        provider="tavily",
        tavily_api_key="key",
        max_retries=2,
        retry_backoff_seconds=0.01,
    )
    attempts = []
    sleeps = []

    def fake_post_json(url, payload, timeout):
        attempts.append(payload["query"])
        if len(attempts) < 3:
            raise TimeoutError("temporary timeout")
        return {
            "results": [
                {
                    "title": "Recovered WPS",
                    "url": "https://example.com/recovered",
                    "content": "recovered content",
                }
            ]
        }

    monkeypatch.setattr("pwps_agent.knowledge.web_search_provider._post_json", fake_post_json)
    monkeypatch.setattr("pwps_agent.knowledge.web_search_provider.sleep", sleeps.append)

    provider = TavilySearchProvider(settings)
    results = provider.search("Q355B GMAW WPS", "kq_retry")

    assert len(attempts) == 3
    assert sleeps == [0.01, 0.02]
    assert results[0].url == "https://example.com/recovered"


def test_tavily_provider_does_not_retry_non_transient_http_errors(monkeypatch) -> None:
    settings = WebSearchSettings(provider="tavily", tavily_api_key="key", max_retries=2)
    attempts = []

    def fake_post_json(url, payload, timeout):
        attempts.append(payload["query"])
        raise HTTPError(
            url="https://api.example/search",
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr("pwps_agent.knowledge.web_search_provider._post_json", fake_post_json)
    provider = TavilySearchProvider(settings)

    with pytest.raises(HTTPError):
        provider.search("Q355B GMAW WPS", "kq_auth")

    assert attempts == ["Q355B GMAW WPS"]
