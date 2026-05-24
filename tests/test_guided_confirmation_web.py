from pwps_agent.core.contracts import Evidence
from pwps_agent.core.state import create_initial_state
from pwps_agent.graph.checkpoints import save_checkpoint
from pwps_agent.web.guided_confirmation import (
    apply_confirmation_payload,
    apply_resume_payload,
    apply_resume_run_payload,
    render_guided_confirmation_html,
    web_state_payload,
)


def test_web_payload_exposes_confirmation_view() -> None:
    state = create_initial_state("Q355B 12mm plate GMAW", "guided_confirmation")
    state.evidence.append(
        Evidence(
            evidence_id="ev_web_1",
            source_type="web",
            content="ER50-6 reference.",
            related_fields=["filler_material"],
        )
    )
    state.fields["filler_material"].status = "candidate"
    state.fields["filler_material"].value = "ER50-6"
    state.fields["filler_material"].evidence_ids = ["ev_web_1"]

    payload = web_state_payload(state)

    assert payload["run_id"] == "run_local"
    assert payload["confirmation_view"]["groups"]
    assert "confirmations" in payload


def test_web_confirmation_payload_can_batch_confirm_fields() -> None:
    state = create_initial_state("Q355B 12mm plate GMAW", "guided_confirmation")

    updated = apply_confirmation_payload(
        state,
        {
            "fields": {"filler_material": "ER50-6", "shielding_gas": "80% Ar / 20% CO2"},
            "message": "Confirm material choices.",
            "reason": "Matches selected welding procedure.",
            "evidence_ids_shown": ["ev_web_1"],
            "action": "accepted",
        },
    )

    assert updated.fields["filler_material"].status == "user_confirmed"
    assert updated.fields["shielding_gas"].value == "80% Ar / 20% CO2"
    assert updated.confirmations[0].evidence_ids_shown == ["ev_web_1"]


def test_web_html_contains_guided_confirmation_shell() -> None:
    html = render_guided_confirmation_html()

    assert "clarification_questions" in html
    assert "候选" in html
    assert "证据" in html
    assert "风险" in html
    assert "确认选中字段" in html
    assert "编辑" in html
    assert "生成草案" in html


def test_web_resume_payload_persists_artifacts(tmp_path) -> None:
    state = create_initial_state("Q355B 12mm plate GMAW", "guided_confirmation", run_id="web_resume")
    state.status = "need_user_input"
    state.fields["filler_material"].value = "ER50-6"
    state.fields["filler_material"].status = "candidate"

    result = apply_resume_payload(
        state,
        {
            "fields": {"filler_material": "ER50-6"},
            "message": "Confirm from web.",
            "output_dir": str(tmp_path),
        },
    )

    assert result["state"].status == "done"
    assert result["output_dir"] == str(tmp_path / "web_resume")
    assert (tmp_path / "web_resume" / "field_report.json").exists()


def test_web_resume_run_payload_loads_latest_checkpoint(tmp_path) -> None:
    state = create_initial_state(
        "Q355B 12mm plate GMAW",
        "guided_confirmation",
        run_id="web_resume_run",
    )
    state.status = "need_user_input"
    state.fields["filler_material"].value = "ER50-6"
    state.fields["filler_material"].status = "candidate"
    save_checkpoint(state, tmp_path, "ask_user")

    result = apply_resume_run_payload(
        "web_resume_run",
        {
            "fields": {"filler_material": "ER50-6"},
            "message": "Confirm from web checkpoint.",
            "output_dir": str(tmp_path),
        },
    )

    assert result["state"].status == "done"
    assert result["output_dir"] == str(tmp_path / "web_resume_run")
    assert (tmp_path / "web_resume_run" / "pwps_draft.md").exists()
