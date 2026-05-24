from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any
from urllib.request import Request, urlopen

from pwps_agent.config import WebSearchSettings
from pwps_agent.core.contracts import SearchResult


class WebSearchProvider(ABC):
    @abstractmethod
    def search(self, query: str, query_id: str) -> list[SearchResult]:
        raise NotImplementedError


class TavilySearchProvider(WebSearchProvider):
    endpoint = "https://api.tavily.com/search"

    def __init__(self, settings: WebSearchSettings) -> None:
        if not settings.tavily_api_key:
            raise ValueError("TAVILY_API_KEY is required for Tavily web search.")
        self.settings = settings

    def search(self, query: str, query_id: str) -> list[SearchResult]:
        payload = {
            "api_key": self.settings.tavily_api_key,
            "query": query,
            "search_depth": self.settings.tavily_search_depth,
            "max_results": self.settings.max_results,
            "include_raw_content": self.settings.tavily_include_raw_content,
        }
        response = _post_json(self.endpoint, payload, timeout=self.settings.timeout_seconds)
        return self.parse_response(query_id=query_id, payload=response)

    @staticmethod
    def parse_response(query_id: str, payload: dict[str, Any]) -> list[SearchResult]:
        results = []
        for index, item in enumerate(payload.get("results", []), start=1):
            results.append(
                SearchResult(
                    result_id=f"{query_id}_tavily_{index}",
                    query_id=query_id,
                    provider="tavily",
                    title=item.get("title"),
                    url=item.get("url"),
                    snippet=item.get("content") or "",
                    raw_content=item.get("raw_content"),
                    score=item.get("score"),
                )
            )
        return results


class BraveSearchProvider(WebSearchProvider):
    endpoint = "https://api.search.brave.com/res/v1/web/search"

    def __init__(self, settings: WebSearchSettings) -> None:
        if not settings.brave_api_key:
            raise ValueError("BRAVE_SEARCH_API_KEY is required for Brave web search.")
        self.settings = settings

    def search(self, query: str, query_id: str) -> list[SearchResult]:
        url = (
            f"{self.endpoint}?q={_quote(query)}"
            f"&count={self.settings.max_results}"
            f"&country={_quote(self.settings.brave_country)}"
            f"&search_lang={_quote(self.settings.brave_lang)}"
            f"&safesearch={_quote(self.settings.brave_safety)}"
        )
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": self.settings.brave_api_key,
        }
        response = _get_json(url, headers=headers, timeout=self.settings.timeout_seconds)
        return self.parse_response(query_id=query_id, payload=response)

    @staticmethod
    def parse_response(query_id: str, payload: dict[str, Any]) -> list[SearchResult]:
        results = []
        for index, item in enumerate(payload.get("web", {}).get("results", []), start=1):
            results.append(
                SearchResult(
                    result_id=f"{query_id}_brave_{index}",
                    query_id=query_id,
                    provider="brave",
                    title=item.get("title"),
                    url=item.get("url"),
                    snippet=item.get("description") or "",
                )
            )
        return results


def build_web_search_provider(settings: WebSearchSettings) -> WebSearchProvider:
    provider = settings.provider.strip().lower()
    if provider == "tavily":
        return TavilySearchProvider(settings)
    if provider == "brave":
        return BraveSearchProvider(settings)
    raise ValueError(f"Unsupported web search provider: {settings.provider}")


def _post_json(url: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:  # nosec B310 - configured API endpoint
        return json.loads(response.read().decode("utf-8"))


def _get_json(url: str, headers: dict[str, str], timeout: int) -> dict[str, Any]:
    request = Request(url, headers=headers, method="GET")
    with urlopen(request, timeout=timeout) as response:  # nosec B310 - configured API endpoint
        return json.loads(response.read().decode("utf-8"))


def _quote(value: str) -> str:
    from urllib.parse import quote

    return quote(value)
