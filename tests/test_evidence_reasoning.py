from pwps_agent.core.contracts import SearchResult
from pwps_agent.core.state import create_initial_state
from pwps_agent.tools.evidence import (
    is_low_quality_source_ref,
    search_results_to_evidence,
)
from pwps_agent.tools.field_reasoning import reason_fields_from_evidence
from pwps_agent.tools.field_reasoning import _field_reasoning_user_prompt


def test_search_results_convert_to_web_evidence() -> None:
    results = [
        SearchResult(
            result_id="r1",
            query_id="q1",
            provider="tavily",
            title="WPS example",
            url="https://example.com/wps",
            snippet="ER50-6 is used with GMAW.",
        )
    ]

    evidence = search_results_to_evidence(results)

    assert evidence[0].evidence_id == "ev_r1"
    assert evidence[0].source_type == "web"
    assert evidence[0].source_ref == "https://example.com/wps"
    assert "ER50-6" in evidence[0].content


def test_search_results_classify_source_tier_and_reliability() -> None:
    results = [
        SearchResult(
            result_id="official",
            query_id="q1",
            provider="brave",
            title="AWS D1.1 Structural Welding Code",
            url="https://www.aws.org/standards/page/d1.1",
            snippet="Official AWS standard page.",
        ),
        SearchResult(
            result_id="textbook",
            query_id="q1",
            provider="brave",
            title="Welding Handbook chapter",
            url="https://library.example.org/welding-handbook",
            snippet="Textbook style reference for GMAW.",
        ),
        SearchResult(
            result_id="webpage",
            query_id="q1",
            provider="brave",
            title="Blog WPS example",
            url="https://example.com/blog/wps",
            snippet="Generic webpage example.",
        ),
    ]

    evidence = search_results_to_evidence(results)

    assert [(item.source_tier, item.reliability) for item in evidence] == [
        ("official_standard", "high"),
        ("textbook", "medium"),
        ("webpage", "low"),
    ]


def test_low_quality_source_detection_flags_known_markers() -> None:
    assert is_low_quality_source_ref("https://facebook.com/example-wps") is True
    assert is_low_quality_source_ref("https://instagram.com/example-wps") is True
    assert is_low_quality_source_ref("https://scribd.com/document/123") is True
    assert is_low_quality_source_ref("https://shop.myshopify.com/products/wps") is True
    assert is_low_quality_source_ref("https://example.com/forum/wps-thread") is True
    assert is_low_quality_source_ref("https://example.com/topic_show.php?id=1") is True
    assert is_low_quality_source_ref("https://www.aws.org/standards/page/d1.1") is False
    assert is_low_quality_source_ref(None) is False


def test_field_reasoning_prompt_includes_field_schema_and_targets() -> None:
    state = create_initial_state(
        "Q355B 12mm plate GMAW butt joint flat position AWS D1.1 pWPS draft",
        "auto_draft",
        run_id="reasoning_context",
    )
    state.knowledge_queries = [
        {
            "query_id": "kq_002",
            "target_fields": ["filler_material", "polarity"],
            "purpose": "filler_reference",
        }
    ]
    state.quality_report = {
        "recommended_action": "refine_search",
        "refinement_focus_fields": ["filler_material"],
        "critical_missing_fields": ["polarity"],
        "weak_evidence_fields": ["shielding_gas"],
    }

    prompt = _field_reasoning_user_prompt(state, [])

    assert "filler_material" in prompt
    assert "焊材型号/分类号" in prompt
    assert "polarity" in prompt
    assert "blocked inferred fields" in prompt.lower()
    assert "project_name" in prompt
    assert "refinement_focus_fields=filler_material" in prompt


class StaticReasoningClient:
    def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        return {
            "candidates": [
                {
                    "field_id": "filler_material",
                    "value": "ER50-6",
                    "status": "candidate",
                    "confidence": "medium",
                    "evidence_ids": ["ev_r1"],
                    "note": "From web evidence; confirm against project standard.",
                },
                {
                    "field_id": "shielding_gas",
                    "value": "Ar+CO2",
                    "status": "candidate",
                    "confidence": "low",
                    "evidence_ids": ["ev_r1"],
                    "note": "Gas mixture was mentioned as a possible reference.",
                },
                {
                    "field_id": "project_name",
                    "value": "Invented Project",
                    "status": "candidate",
                    "confidence": "low",
                    "evidence_ids": ["ev_r1"],
                    "note": "Should be ignored because project metadata cannot be inferred.",
                },
            ]
        }


def test_reason_fields_from_evidence_maps_structured_llm_candidates() -> None:
    state = create_initial_state("Q355B GMAW", "auto_draft")
    evidence = search_results_to_evidence(
        [
            SearchResult(
                result_id="r1",
                query_id="q1",
                provider="tavily",
                title="WPS example",
                url="https://example.com/wps",
                snippet="ER50-6 and Ar+CO2 are referenced for GMAW.",
            )
        ]
    )

    result = reason_fields_from_evidence(state, evidence, StaticReasoningClient())

    assert result.success is True
    fields = result.state_patch["fields"]
    assert fields["filler_material"]["value"] == "ER50-6"
    assert fields["filler_material"]["status"] == "candidate"
    assert fields["shielding_gas"]["value"] == "Ar+CO2"
    assert "project_name" not in fields
