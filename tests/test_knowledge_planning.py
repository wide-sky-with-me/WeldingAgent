from pwps_agent.core.state import create_initial_state
from pwps_agent.tools.knowledge_planning import _user_prompt, plan_knowledge_queries


class StaticPlanningClient:
    def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        assert "known_fields" in user_prompt
        assert "missing_fields" in user_prompt
        return {
            "queries": [
                {
                    "query_id": "kq_position_1",
                    "purpose": "similar_case",
                    "query_text": "Q355B GMAW plate common welding positions WPS AWS D1.1",
                    "target_fields": ["welding_position"],
                    "rationale": "Known material and process can guide position lookup.",
                },
                {
                    "query_id": "kq_filler_1",
                    "purpose": "filler_reference",
                    "query_text": "Q355B 12mm GMAW butt joint filler wire shielding gas WPS",
                    "target_fields": ["filler_material", "shielding_gas"],
                    "rationale": "Find filler and gas references after core scope is available.",
                },
            ]
        }


def test_plan_knowledge_queries_uses_model_to_target_missing_fields() -> None:
    state = create_initial_state("Q355B 12mm GMAW plate", "auto_draft")
    state.core_fields.update(
        {
            "base_material": "Q355B",
            "thickness": "12mm",
            "welding_process": "GMAW",
            "workpiece_type": "plate",
        }
    )
    for field_id, value in state.core_fields.items():
        if field_id in state.fields:
            state.fields[field_id].value = value
            state.fields[field_id].status = "filled"

    result = plan_knowledge_queries(state, StaticPlanningClient())

    assert result.success is True
    queries = result.state_patch["knowledge_queries"]
    assert queries[0]["query_id"] == "kq_position_1"
    assert queries[0]["target_fields"] == ["welding_position"]
    assert "common welding positions" in queries[0]["query_text"]
    assert queries[1]["target_fields"] == ["filler_material", "shielding_gas"]


class EmptyPlanningClient:
    def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        return {"queries": []}


class FailingPlanningClient:
    def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        raise ValueError("structured output parser failed")


def test_plan_knowledge_queries_has_targeted_fallback_when_model_returns_empty() -> None:
    state = create_initial_state("Q355B GMAW plate", "auto_draft")
    state.core_fields.update(
        {
            "base_material": "Q355B",
            "welding_process": "GMAW",
            "workpiece_type": "plate",
        }
    )

    result = plan_knowledge_queries(state, EmptyPlanningClient())

    queries = result.state_patch["knowledge_queries"]
    assert queries[0]["purpose"] == "similar_case"
    assert "Q355B" in queries[0]["query_text"]
    assert "GMAW" in queries[0]["query_text"]
    assert queries[0]["target_fields"]


def test_plan_knowledge_queries_falls_back_when_structured_output_fails() -> None:
    state = create_initial_state("Q355B 12mm plate GMAW", "auto_draft")
    state.core_fields.update(
        {
            "base_material": "Q355B",
            "thickness": "12mm",
            "welding_process": "GMAW",
            "workpiece_type": "plate",
        }
    )

    result = plan_knowledge_queries(state, FailingPlanningClient())

    assert result.success is True
    assert result.state_patch["knowledge_queries"][0]["context"]["fallback"] is True
    assert result.errors == ["structured output parser failed"]


def test_knowledge_planning_prompt_includes_quality_refinement_context() -> None:
    state = create_initial_state("Q355B GMAW plate", "auto_draft")
    state.quality_report = {
        "quality_level": "partial",
        "recommended_action": "refine_search",
        "field_counts": {},
        "critical_missing_fields": ["filler_material"],
        "weak_evidence_fields": ["current_range"],
        "low_quality_sources": [],
        "blocked_inference_violations": [],
        "refinement_focus_fields": ["filler_material", "current_range"],
        "human_review_fields": [],
        "target_field_coverage": [],
        "evidence_quality": {"evidence_count": 1},
    }
    state.knowledge_queries = [
        {
            "query_id": "kq_001",
            "query_text": "old filler query",
            "target_fields": ["filler_material"],
        }
    ]

    prompt = _user_prompt(state)

    assert "quality_refinement_focus_fields" in prompt
    assert "filler_material" in prompt
    assert "quality_weak_evidence_fields" in prompt
    assert "current_range" in prompt
    assert "previous_query_texts" in prompt
    assert "old filler query" in prompt
