from __future__ import annotations

from pwps_agent.core.contracts import Evidence, SearchResult

LOW_QUALITY_SOURCE_MARKERS = (
    "facebook.com",
    "instagram.com",
    "scribd.com",
    "myshopify.com",
    "/forum/",
    "topic_show",
)


def search_results_to_evidence(results: list[SearchResult]) -> list[Evidence]:
    evidence: list[Evidence] = []
    for result in results:
        content_parts = [part for part in [result.title, result.snippet, result.raw_content] if part]
        source_tier, reliability = _classify_source(result)
        evidence.append(
            Evidence(
                evidence_id=f"ev_{result.result_id}",
                query_id=result.query_id,
                result_id=result.result_id,
                source_type=result.source_type,
                source_ref=result.url,
                content="\n".join(content_parts),
                extracted_claims=[result.snippet] if result.snippet else [],
                source_tier=source_tier,
                reliability=reliability,
                confidence=reliability,
                note=(
                    f"{source_tier.replace('_', ' ').title()} reference from "
                    f"{result.provider}; treat as candidate evidence."
                ),
            )
        )
    return evidence


def is_low_quality_source_ref(source_ref: str | None) -> bool:
    if not source_ref:
        return False
    lowered = source_ref.lower()
    return any(marker in lowered for marker in LOW_QUALITY_SOURCE_MARKERS)


def _classify_source(result: SearchResult) -> tuple[str, str]:
    if result.source_type == "local_doc":
        return "textbook", "medium"
    text = " ".join(part for part in [result.title, result.snippet, result.url] if part).lower()
    url = (result.url or "").lower()
    if any(domain in url for domain in ("aws.org", "iso.org", "asme.org", "astm.org")) and any(
        marker in text for marker in ("standard", "code", "d1.1", "specification")
    ):
        return "official_standard", "high"
    if any(marker in text for marker in ("textbook", "handbook", "manual", "chapter")):
        return "textbook", "medium"
    return "webpage", "low"
