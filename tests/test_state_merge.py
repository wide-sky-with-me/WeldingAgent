from pwps_agent.core.contracts import Evidence
from pwps_agent.core.state import PWPSState, create_initial_state
from pwps_agent.core.state_merge import merge_state_patch


def test_merge_preserves_user_field_value_as_candidate_when_patch_has_lower_priority():
    state = create_initial_state("Q355B 12mm GMAW", "auto_draft")
    state.fields["base_material"].value = "Q355B"
    state.fields["base_material"].status = "filled"
    state.fields["base_material"].source = {"type": "user_input"}

    updated = merge_state_patch(
        state,
        {
            "fields": {
                "base_material": {
                    "value": "S355J0",
                    "status": "candidate",
                    "confidence": "medium",
                    "evidence_ids": ["ev_web_1"],
                    "source": {"type": "web"},
                }
            }
        },
    )

    assert updated.fields["base_material"].value == "Q355B"
    assert updated.fields["base_material"].status == "filled"
    assert updated.fields["base_material"].candidates[0]["value"] == "S355J0"
    assert updated.fields["base_material"].candidates[0]["evidence_ids"] == ["ev_web_1"]
    assert updated.fields["base_material"].candidates[0]["created_at"]


def test_merge_deduplicates_query_result_and_evidence_lists():
    state = create_initial_state("Q355B 12mm GMAW", "auto_draft")
    state.knowledge_queries = [{"query_id": "kq_1", "query_text": "old"}]
    state.search_results = [{"result_id": "r1", "snippet": "old"}]
    state.evidence.append(
        Evidence(
            evidence_id="ev_dup",
            source_type="web",
            content="old",
            reliability="medium",
        )
    )

    updated = merge_state_patch(
        state,
        {
            "knowledge_queries": [
                {"query_id": "kq_1", "query_text": "duplicate"},
                {"query_id": "kq_2", "query_text": "new"},
            ],
            "search_results": [
                {"result_id": "r1", "snippet": "duplicate"},
                {"result_id": "r2", "snippet": "new"},
            ],
            "evidence": [
                {"evidence_id": "ev_dup", "source_type": "web", "content": "duplicate"},
                {"evidence_id": "ev_new", "source_type": "web", "content": "new"},
            ],
        },
    )

    assert [query["query_id"] for query in updated.knowledge_queries] == ["kq_1", "kq_2"]
    assert [result["result_id"] for result in updated.search_results] == ["r1", "r2"]
    assert [evidence.evidence_id for evidence in updated.evidence] == [
        "ev_user_input_1",
        "ev_dup",
        "ev_new",
    ]


def test_merge_records_warnings_for_unknown_patch_keys_and_fields():
    state = create_initial_state("Q355B 12mm GMAW", "auto_draft")

    updated = merge_state_patch(
        state,
        {
            "unsupported": {"value": True},
            "fields": {
                "unknown_field": {"value": "ignored", "status": "candidate"},
            },
        },
    )

    warnings = [
        entry for entry in updated.trace if entry["node"] == "state_merge"
    ]
    assert [entry["event_type"] for entry in warnings] == [
        "merge_warning",
        "merge_warning",
    ]
    assert warnings[0]["payload"]["key"] == "unsupported"
    assert warnings[1]["payload"]["field_id"] == "unknown_field"


def test_merge_normalizes_llm_confirmed_status_to_schema_valid_filled():
    state = create_initial_state("Q355B 12mm GMAW", "auto_draft")

    updated = merge_state_patch(
        state,
        {
            "fields": {
                "base_material": {
                    "value": "Q355B",
                    "status": "confirmed",
                    "confidence": "high",
                    "source": {"type": "user_input"},
                    "evidence_ids": ["ev_user_input_1"],
                }
            }
        },
    )

    assert updated.fields["base_material"].status == "filled"
    PWPSState.model_validate_json(updated.model_dump_json())
