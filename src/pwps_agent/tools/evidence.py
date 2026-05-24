from __future__ import annotations

from pwps_agent.core.contracts import Evidence, SearchResult


def search_results_to_evidence(results: list[SearchResult]) -> list[Evidence]:
    evidence: list[Evidence] = []
    for result in results:
        content_parts = [part for part in [result.title, result.snippet, result.raw_content] if part]
        evidence.append(
            Evidence(
                evidence_id=f"ev_{result.result_id}",
                query_id=result.query_id,
                result_id=result.result_id,
                source_type="web",
                source_ref=result.url,
                content="\n".join(content_parts),
                extracted_claims=[result.snippet] if result.snippet else [],
                reliability="low",
                note=f"Web reference from {result.provider}; treat as candidate evidence.",
            )
        )
    return evidence
