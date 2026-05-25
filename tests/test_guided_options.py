from pwps_agent.core.contracts import ToolResult
from pwps_agent.core.state import create_initial_state
from pwps_agent.tools.guided_options import (
    GuidedOption,
    GuidedOptionSet,
    build_guided_options,
    merge_guided_option_set,
)


def test_guided_options_include_recommendation_and_confirmation_requirement():
    option_set = GuidedOptionSet(
        field_id="welding_process",
        question="Confirm welding process.",
        options=[
            GuidedOption(
                value="GMAW",
                suitability="Good for productivity on plate joints.",
                risk_note="Confirm shielding gas and transfer mode.",
                recommended=True,
            ),
            GuidedOption(
                value="SMAW",
                suitability="Useful for repair or site welding.",
                risk_note="Lower productivity.",
                recommended=False,
            ),
        ],
        requires_user_confirmation=True,
    )
    result = ToolResult(
        tool_name="guided_options",
        success=True,
        state_patch=merge_guided_option_set(option_set),
        summary="ok",
    )

    assert result.state_patch["fields"]["welding_process"]["status"] == "need_confirmation"
    assert result.state_patch["fields"]["welding_process"]["candidates"][0]["recommended"] is True


def test_build_guided_options_keeps_key_field_needing_confirmation():
    state = create_initial_state("Q355B GMAW", "guided_confirmation")
    state.fields["welding_process"].value = "GMAW"
    state.fields["welding_process"].status = "candidate"

    result = build_guided_options(state)

    patch = result.state_patch["fields"]["welding_process"]
    assert patch["status"] == "need_confirmation"
    assert patch["confirmation"]["required"] is True
    assert patch["candidates"][0]["recommended"] is True
