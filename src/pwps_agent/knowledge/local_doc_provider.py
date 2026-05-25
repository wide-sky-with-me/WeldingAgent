from __future__ import annotations

import re
from pathlib import Path

from pwps_agent.core.contracts import SearchResult


SUPPORTED_SUFFIXES = {".md", ".markdown", ".txt"}


class LocalDocumentProvider:
    def __init__(
        self,
        docs_dir: Path,
        max_results: int = 5,
        snippet_chars: int = 420,
    ) -> None:
        self.docs_dir = docs_dir
        self.max_results = max_results
        self.snippet_chars = snippet_chars

    def search(self, query: str, query_id: str) -> list[SearchResult]:
        terms = _terms(query)
        if not terms or not self.docs_dir.exists():
            return []

        scored: list[tuple[float, Path, str]] = []
        for path in sorted(self.docs_dir.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            score = _score(text, terms)
            if score <= 0:
                continue
            scored.append((score, path, _snippet(text, terms, self.snippet_chars)))

        scored.sort(key=lambda item: (-item[0], str(item[1])))
        results: list[SearchResult] = []
        for index, (score, path, snippet) in enumerate(scored[: self.max_results], start=1):
            rel_path = path.relative_to(self.docs_dir)
            results.append(
                SearchResult(
                    result_id=f"{query_id}_local_{index}",
                    query_id=query_id,
                    source_type="local_doc",
                    provider="local_doc",
                    title=str(rel_path),
                    url=str(rel_path),
                    snippet=snippet,
                    score=score,
                )
            )
        return results


def _terms(query: str) -> list[str]:
    return [
        term.lower()
        for term in re.findall(r"[A-Za-z0-9][A-Za-z0-9.+/%-]*", query)
        if len(term) >= 2
    ]


def _score(text: str, terms: list[str]) -> float:
    lowered = text.lower()
    score = 0.0
    for term in terms:
        count = lowered.count(term)
        if count:
            score += 1.0 + min(count, 5) * 0.25
    return score


def _snippet(text: str, terms: list[str], snippet_chars: int) -> str:
    lowered = text.lower()
    first_match = min(
        (lowered.find(term) for term in terms if lowered.find(term) >= 0),
        default=0,
    )
    start = max(0, first_match - snippet_chars // 4)
    end = min(len(text), start + snippet_chars)
    return " ".join(text[start:end].split())
