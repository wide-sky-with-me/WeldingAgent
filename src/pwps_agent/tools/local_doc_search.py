from __future__ import annotations

from pwps_agent.core.contracts import ToolResult
from pwps_agent.core.state import PWPSState
from pwps_agent.tools.evidence import search_results_to_evidence


def search_local_documents(state: PWPSState, provider) -> ToolResult:
    search_results = []
    for query in _local_doc_queries(state.knowledge_queries):
        query_text = str(query["query_text"])
        query_id = str(query["query_id"])
        search_results.extend(provider.search(query_text, query_id))

    evidence = search_results_to_evidence(search_results)
    return ToolResult(
        tool_name="local_doc_search",
        success=True,
        state_patch={
            "search_results": [result.model_dump() for result in search_results],
            "evidence": [item.model_dump() for item in evidence],
        },
        summary=f"Retrieved {len(search_results)} local document results.",
    )


def has_local_doc_queries(knowledge_queries: list[dict]) -> bool:
    return any(_query_prefers_local_doc(query) for query in knowledge_queries)


def _local_doc_queries(knowledge_queries: list[dict]) -> list[dict]:
    return [query for query in knowledge_queries if _query_prefers_local_doc(query)]


def _query_prefers_local_doc(query: dict) -> bool:
    preferred = query.get("preferred_sources") or []
    return "local_doc" in preferred
