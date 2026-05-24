from pwps_agent.core.contracts import Evidence
from pwps_agent.core.modes import (
    build_confirmation_view,
    confirm_fields,
    edit_confirmation,
    rollback_confirmation,
)
from pwps_agent.core.state import create_initial_state


def test_confirmation_view_groups_fields_with_candidates_evidence_and_risks() -> None:
    state = create_initial_state(
        user_input="Q355B 12mm plate GMAW",
        interaction_mode="guided_confirmation",
    )
    state.clarification_questions.append(
        {"question_id": "q1", "field_id": "filler_material", "question": "Confirm filler?"}
    )
    state.evidence.append(
        Evidence(
            evidence_id="ev_web_1",
            source_type="web",
            source_ref="https://example.test/wps",
            content="Example WPS uses ER50-6 for Q355B GMAW.",
            related_fields=["filler_material"],
            reliability="medium",
        )
    )
    state.fields["filler_material"].status = "candidate"
    state.fields["filler_material"].value = "ER50-6"
    state.fields["filler_material"].evidence_ids = ["ev_web_1"]
    state.fields["filler_material"].candidates.append(
        {
            "value": "ER50-6",
            "confidence": "medium",
            "evidence_ids": ["ev_web_1"],
            "note": "Web reference candidate.",
        }
    )
    state.risks.append(
        {
            "risk_id": "risk_1",
            "field_ids": ["filler_material"],
            "message": "Web evidence needs user confirmation.",
        }
    )

    view = build_confirmation_view(state)

    assert view["clarification_questions"][0]["question_id"] == "q1"
    group = next(group for group in view["groups"] if group["section"] == "C")
    field = group["fields"][0]
    assert field["field_id"] == "filler_material"
    assert field["candidates"][0]["value"] == "ER50-6"
    assert field["evidence"][0]["evidence_id"] == "ev_web_1"
    assert field["risks"][0]["risk_id"] == "risk_1"


def test_confirmation_rollback_restores_previous_field_state() -> None:
    state = create_initial_state("Q355B 12mm plate GMAW", "guided_confirmation")
    state.fields["filler_material"].value = "ER50-6"
    state.fields["filler_material"].status = "candidate"
    state.fields["filler_material"].confidence = "medium"

    confirmed = confirm_fields(
        state,
        field_values={"filler_material": "ER50-6"},
        user_message="Accept candidate.",
        user_rationale="Matches shop preference.",
        evidence_ids_shown=["ev_web_1"],
        action="accepted",
    )

    rolled_back = rollback_confirmation(
        confirmed,
        confirmation_id="confirm_1",
        user_message="Undo this confirmation.",
        reason="Need to compare another filler.",
    )

    field = rolled_back.fields["filler_material"]
    assert field.value == "ER50-6"
    assert field.status == "candidate"
    assert field.confidence == "medium"
    assert rolled_back.confirmations[-1].action == "rolled_back"
    assert rolled_back.confirmations[-1].rolled_back_confirmation_id == "confirm_1"


def test_edit_confirmation_updates_fields_and_links_history() -> None:
    state = create_initial_state("Q355B 12mm plate GMAW", "guided_confirmation")
    confirmed = confirm_fields(
        state,
        field_values={"filler_material": "ER50-6"},
        user_message="Accept ER50-6.",
        evidence_ids_shown=["ev_web_1"],
        action="accepted",
    )

    edited = edit_confirmation(
        confirmed,
        confirmation_id="confirm_1",
        field_values={"filler_material": "ER49-1"},
        user_message="Use project-specified filler instead.",
        user_rationale="Client welding spec lists ER49-1.",
        evidence_ids_shown=["ev_user_2"],
    )

    assert edited.fields["filler_material"].value == "ER49-1"
    assert edited.confirmations[-1].action == "edited"
    assert edited.confirmations[-1].supersedes_confirmation_id == "confirm_1"
    assert edited.confirmations[-1].user_rationale == "Client welding spec lists ER49-1."
