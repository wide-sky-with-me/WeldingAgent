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
