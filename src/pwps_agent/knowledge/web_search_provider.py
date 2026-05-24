from __future__ import annotations

import json
from abc import ABC, abstractmethod
from time import sleep
from typing import Any
from urllib.error import HTTPError, URLError
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
        self._response_cache: dict[str, dict[str, Any]] = {}

    def search(self, query: str, query_id: str) -> list[SearchResult]:
        request_payload = {
            "api_key": self.settings.tavily_api_key,
            "query": query,
            "search_depth": self.settings.tavily_search_depth,
            "max_results": self.settings.max_results,
            "include_raw_content": self.settings.tavily_include_raw_content,
        }
        cache_key = _cache_key("tavily", query)
        response = _cached_or_fetch(
            cache=self._response_cache,
            cache_key=cache_key,
            settings=self.settings,
            fetch=lambda: _post_json(
                self.endpoint,
                request_payload,
                timeout=self.settings.timeout_seconds,
            ),
        )
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
        self._response_cache: dict[str, dict[str, Any]] = {}

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
        cache_key = _cache_key("brave", query)
        response = _cached_or_fetch(
            cache=self._response_cache,
            cache_key=cache_key,
            settings=self.settings,
            fetch=lambda: _get_json(url, headers=headers, timeout=self.settings.timeout_seconds),
        )
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


def _cached_or_fetch(
    cache: dict[str, dict[str, Any]],
    cache_key: str,
    settings: WebSearchSettings,
    fetch,
) -> dict[str, Any]:
    if settings.cache_enabled and cache_key in cache:
        return cache[cache_key]
    response = _with_retries(fetch, settings)
    if settings.cache_enabled:
        cache[cache_key] = response
    return response


def _with_retries(fetch, settings: WebSearchSettings) -> dict[str, Any]:
    max_retries = max(0, settings.max_retries)
    for attempt in range(max_retries + 1):
        try:
            return fetch()
        except Exception as exc:
            if attempt >= max_retries or not _is_retryable(exc):
                raise
            sleep(settings.retry_backoff_seconds * (2**attempt))
    raise RuntimeError("unreachable web search retry state")


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, HTTPError):
        return exc.code == 429 or 500 <= exc.code < 600
    if isinstance(exc, TimeoutError | URLError):
        return True
    return False


def _cache_key(provider: str, query: str) -> str:
    return f"{provider}:{' '.join(query.strip().lower().split())}"


def _quote(value: str) -> str:
    from urllib.parse import quote

    return quote(value)
