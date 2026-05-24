from pwps_agent.core.modes import apply_supplement, confirm_fields
from pwps_agent.core.state import create_initial_state


def test_auto_draft_initial_state_marks_mode_and_core_fields() -> None:
    state = create_initial_state(
        user_input="Q355B 12mm plate GMAW butt joint flat position AWS D1.1",
        interaction_mode="auto_draft",
    )

    assert state.interaction_mode == "auto_draft"
    assert state.status == "running"
    assert state.fields["base_material"].status == "missing"


def test_guided_confirmation_promotes_fields_to_user_confirmed() -> None:
    state = create_initial_state(
        user_input="Q355B 12mm plate GMAW",
        interaction_mode="guided_confirmation",
    )

    updated = confirm_fields(
        state,
        field_values={"filler_material": "ER50-6"},
        user_message="Confirm ER50-6.",
        rationale_shown="Recommended for the low-alloy steel GMAW draft.",
        evidence_ids_shown=["ev_1"],
    )

    field = updated.fields["filler_material"]
    assert field.value == "ER50-6"
    assert field.status == "user_confirmed"
    assert field.confirmation["confirmed"] is True
    assert updated.confirmations[0].field_ids == ["filler_material"]


def test_supplement_update_records_user_input_and_updates_existing_fields() -> None:
    state = create_initial_state(
        user_input="Generate pWPS draft.",
        interaction_mode="auto_draft",
    )

    updated = apply_supplement(
        state,
        supplement="Base material is Q355B.",
        field_values={"base_material": "Q355B"},
    )

    assert updated.interaction_mode == "supplement_update"
    assert updated.fields["base_material"].value == "Q355B"
    assert updated.fields["base_material"].status == "filled"
    assert updated.evidence[-1].source_type == "user_input"
