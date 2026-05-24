from pwps_agent.core.contracts import SearchResult
from pwps_agent.core.state import create_initial_state
from pwps_agent.tools.evidence import search_results_to_evidence
from pwps_agent.tools.field_reasoning import apply_field_candidates, reason_fields_from_evidence


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


def test_apply_field_candidates_marks_values_as_candidate_with_evidence() -> None:
    state = create_initial_state("Q355B GMAW", "auto_draft")

    updated = apply_field_candidates(
        state,
        candidates={
            "filler_material": {
                "value": "ER50-6",
                "evidence_ids": ["ev_r1"],
                "note": "Candidate from web reference.",
            }
        },
    )

    field = updated.fields["filler_material"]
    assert field.value == "ER50-6"
    assert field.status == "candidate"
    assert field.confidence == "medium"
    assert field.evidence_ids == ["ev_r1"]
    assert field.confirmation["required"] is True


def test_apply_field_candidates_does_not_overwrite_user_filled_field() -> None:
    state = create_initial_state("Q355B GMAW", "auto_draft")
    state.fields["base_material"].value = "Q355B"
    state.fields["base_material"].status = "filled"
    state.fields["base_material"].source = {"type": "user_input", "ref": "ev_user_input_1"}

    updated = apply_field_candidates(
        state,
        candidates={
            "base_material": {
                "value": "S355 J0",
                "evidence_ids": ["ev_r1"],
                "note": "Possible equivalent from web evidence.",
            }
        },
    )

    field = updated.fields["base_material"]
    assert field.value == "Q355B"
    assert field.status == "filled"
    assert field.candidates[0]["value"] == "S355 J0"
    assert field.candidates[0]["status"] == "candidate"


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
