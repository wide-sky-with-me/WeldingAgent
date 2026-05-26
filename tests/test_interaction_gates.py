from pwps_agent.core.interaction import (
    build_initial_info_request,
    missing_minimum_auto_draft_fields,
    should_interrupt_for_initial_info,
)
from pwps_agent.core.state import create_initial_state


def test_auto_draft_interrupts_only_before_workflow_starts_when_core_fields_missing():
    state = create_initial_state("Need a pWPS draft", "auto_draft")

    assert missing_minimum_auto_draft_fields(state) == [
        "base_material",
        "thickness",
        "workpiece_type",
        "welding_process",
        "joint_type",
        "welding_position",
    ]
    assert should_interrupt_for_initial_info(state) is True


def test_auto_draft_does_not_interrupt_after_retrieval_started():
    state = create_initial_state("Need a pWPS draft", "auto_draft")
    state.trace.append({"node": "knowledge_planning", "event_type": "tool_result"})

    assert should_interrupt_for_initial_info(state) is False


def test_auto_draft_still_interrupts_after_understanding_when_core_fields_missing():
    state = create_initial_state("Need a pWPS draft", "auto_draft")
    state.trace.append({"node": "requirement_understanding", "event_type": "tool_result"})

    assert should_interrupt_for_initial_info(state) is True


def test_initial_gate_is_satisfied_by_filled_core_fields():
    state = create_initial_state("Q355B 12mm GMAW", "auto_draft")
    for field_id, value in {
        "base_material": "Q355B",
        "thickness": "12mm",
        "workpiece_type": "plate",
        "welding_process": "GMAW",
        "joint_type": "butt joint",
        "welding_position": "flat",
    }.items():
        state.fields[field_id].value = value
        state.fields[field_id].status = "filled"

    assert missing_minimum_auto_draft_fields(state) == []
    assert should_interrupt_for_initial_info(state) is False


def test_initial_info_request_is_transport_neutral_runtime_payload():
    state = create_initial_state("Need a pWPS draft", "auto_draft")

    request = build_initial_info_request(state)

    assert request.purpose == "initial_minimum_context"
    assert request.interaction_mode == "auto_draft"
    assert request.transport_neutral is True
    assert request.questions[0].required is True
    assert request.questions[0].field_ids == [
        "base_material",
        "thickness",
        "workpiece_type",
        "welding_process",
        "joint_type",
        "welding_position",
    ]
