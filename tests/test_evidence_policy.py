from pwps_agent.core.contracts import Evidence
from pwps_agent.core.evidence_policy import evidence_strength, may_promote_candidate


def test_official_plus_textbook_evidence_can_support_recommendation():
    evidence = [
        Evidence(
            evidence_id="ev1",
            source_type="web",
            source_tier="official_standard",
            confidence="high",
            content="AWS reference",
        ),
        Evidence(
            evidence_id="ev2",
            source_type="local_doc",
            source_tier="textbook",
            confidence="medium",
            content="Local guide",
        ),
    ]

    assert evidence_strength(evidence) == "strong"
    assert may_promote_candidate(evidence, requires_human_confirmation=False) is True


def test_webpage_only_evidence_cannot_promote_key_choice():
    evidence = [
        Evidence(
            evidence_id="ev1",
            source_type="web",
            source_tier="webpage",
            confidence="low",
            content="Blog snippet",
        ),
    ]

    assert evidence_strength(evidence) == "weak"
    assert may_promote_candidate(evidence, requires_human_confirmation=True) is False
