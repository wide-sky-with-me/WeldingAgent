from pwps_agent.core.contracts import AgentAction, ConfirmationRecord, ToolResult
from pwps_agent.core.fields import initialize_fields


def test_agent_action_separates_domain_skill_from_runtime_tool() -> None:
    action = AgentAction(
        action_type="CALL_TOOL",
        tool_name="web_search",
        tool_args={"query": "Q355B GMAW WPS"},
        rationale_summary="Need web evidence for candidate parameters.",
    )

    assert action.tool_name == "web_search"
    assert action.domain_skill_name is None


def test_agent_action_defaults_missing_rationale_for_llm_resilience() -> None:
    action = AgentAction(action_type="CALL_TOOL", tool_name="web_search")

    assert action.rationale_summary
    assert "without a rationale" in action.rationale_summary


def test_tool_result_returns_state_patch_without_mutating_state() -> None:
    result = ToolResult(
        tool_name="field_merge",
        success=True,
        state_patch={"fields": {"base_material": {"value": "Q355B"}}},
        summary="Merged base material.",
    )

    assert result.state_patch["fields"]["base_material"]["value"] == "Q355B"


def test_initialize_fields_contains_all_core_sections_with_missing_status() -> None:
    fields = initialize_fields()

    assert fields["applicable_standard"].section == "A"
    assert fields["base_material"].section == "B"
    assert fields["filler_material"].section == "C"
    assert fields["current_range"].section == "D"
    assert fields["preheat_temperature"].section == "E"
    assert all(field.status == "missing" for field in fields.values())


def test_confirmation_record_captures_user_choice() -> None:
    record = ConfirmationRecord(
        confirmation_id="confirm_1",
        field_ids=["filler_material"],
        action="modified",
        values={"filler_material": "ER50-6"},
        user_message="Use ER50-6.",
    )

    assert record.action == "modified"
    assert record.values["filler_material"] == "ER50-6"
