from __future__ import annotations

from typing import Literal

from pwps_agent.core.contracts import Evidence


EvidenceStrength = Literal["strong", "medium", "weak"]

_TIER_SCORE = {
    "official_standard": 3,
    "textbook": 2,
    "user": 2,
    "webpage": 1,
    "llm": 0,
    "unknown": 0,
}

_CONFIDENCE_SCORE = {
    "high": 3,
    "medium": 2,
    "low": 1,
    "unknown": 0,
}


def evidence_strength(evidence: list[Evidence]) -> EvidenceStrength:
    if not evidence:
        return "weak"
    tier_scores = [_TIER_SCORE.get(item.source_tier, 0) for item in evidence]
    confidence_scores = [_CONFIDENCE_SCORE.get(item.confidence, 0) for item in evidence]
    if max(tier_scores, default=0) >= 3 and max(confidence_scores, default=0) >= 2:
        if len(evidence) >= 2 or max(confidence_scores, default=0) >= 3:
            return "strong"
    if max(tier_scores, default=0) >= 2 and max(confidence_scores, default=0) >= 2:
        return "medium"
    if len(evidence) >= 2 and max(tier_scores, default=0) >= 1 and max(confidence_scores, default=0) >= 2:
        return "medium"
    return "weak"


def may_promote_candidate(
    evidence: list[Evidence],
    *,
    requires_human_confirmation: bool,
) -> bool:
    if requires_human_confirmation:
        return False
    return evidence_strength(evidence) in {"strong", "medium"}
