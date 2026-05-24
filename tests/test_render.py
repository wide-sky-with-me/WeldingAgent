from pwps_agent.core.modes import confirm_fields
from pwps_agent.core.state import create_initial_state
from pwps_agent.render.markdown import render_field_report, render_pwps_draft


def test_render_draft_shows_status_and_missing_fields() -> None:
    state = create_initial_state(
        user_input="Q355B 12mm plate GMAW",
        interaction_mode="auto_draft",
    )
    state.fields["base_material"].value = "Q355B"
    state.fields["base_material"].status = "filled"
    state.fields["filler_material"].value = "ER50-6"
    state.fields["filler_material"].status = "candidate"
    state.fields["preheat_temperature"].status = "need_confirmation"

    markdown = render_pwps_draft(state)

    assert "# pWPS 草案" in markdown
    assert "母材牌号" in markdown
    assert "Q355B" in markdown
    assert "candidate" in markdown
    assert "待确认项与风险提示" in markdown


def test_render_field_report_lists_user_confirmed_fields() -> None:
    state = create_initial_state(
        user_input="Q355B 12mm plate GMAW",
        interaction_mode="guided_confirmation",
    )
    state = confirm_fields(
        state,
        field_values={"filler_material": "ER50-6"},
        user_message="Confirm ER50-6.",
    )

    report = render_field_report(state)

    assert "user_confirmed_fields" in report
    assert "filler_material" in report["user_confirmed_fields"]


def test_render_field_report_lists_retained_candidates_on_filled_fields() -> None:
    state = create_initial_state(
        user_input="Q355B 12mm plate GMAW",
        interaction_mode="auto_draft",
    )
    state.fields["base_material"].value = "Q355B"
    state.fields["base_material"].status = "filled"
    state.fields["base_material"].candidates.append(
        {
            "value": "ASTM A572 Grade 50",
            "status": "candidate",
            "evidence_ids": ["ev_1"],
            "note": "Possible standard mapping from web evidence.",
        }
    )

    report = render_field_report(state)

    assert report["retained_candidates"]["base_material"][0]["value"] == "ASTM A572 Grade 50"
