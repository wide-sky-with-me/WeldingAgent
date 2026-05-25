from pwps_agent.core.publishability import publishability_for_field
from pwps_agent.core.state import create_initial_state
from pwps_agent.core.state_merge import merge_state_patch


def test_user_confirmed_field_is_publishable_draft_value():
    state = create_initial_state("Q355B GMAW", "guided_confirmation")
    field = state.fields["welding_process"]
    field.value = "GMAW"
    field.status = "user_confirmed"
    field.source = {"type": "user_confirmation"}

    assert publishability_for_field(field) == "draft_publishable"


def test_web_candidate_is_reference_only_until_confirmed():
    state = create_initial_state("Q355B GMAW", "auto_draft")
    field = state.fields["shielding_gas"]
    field.value = "80% Ar / 20% CO2"
    field.status = "candidate"
    field.source = {"type": "web"}
    field.confidence = "medium"

    assert publishability_for_field(field) == "reference_only"


def test_merge_assigns_publishability_metadata():
    state = create_initial_state("Q355B GMAW", "auto_draft")

    updated = merge_state_patch(
        state,
        {
            "fields": {
                "shielding_gas": {
                    "value": "80% Ar / 20% CO2",
                    "status": "candidate",
                    "source": {"type": "web"},
                }
            }
        },
    )

    assert updated.fields["shielding_gas"].publishability == "reference_only"
