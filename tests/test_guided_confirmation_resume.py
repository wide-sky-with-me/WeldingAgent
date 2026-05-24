from pathlib import Path

from pwps_agent.config import Settings
from pwps_agent.core.state import create_initial_state
from pwps_agent.workflows.guided_confirmation import resume_guided_confirmation


def test_resume_guided_confirmation_applies_payload_and_persists_artifacts(tmp_path: Path) -> None:
    settings = Settings()
    settings.paths.output_dir = tmp_path
    state = create_initial_state(
        "Q355B 12mm plate GMAW",
        "guided_confirmation",
        run_id="guided_resume",
    )
    state.status = "need_user_input"
    state.fields["filler_material"].value = "ER50-6"
    state.fields["filler_material"].status = "candidate"

    result = resume_guided_confirmation(
        state,
        {
            "fields": {"filler_material": "ER50-6"},
            "message": "Confirm ER50-6.",
            "reason": "Accepted for this draft.",
            "evidence_ids_shown": ["ev_web_1"],
            "action": "accepted",
        },
        settings=settings,
    )

    run_dir = tmp_path / "guided_resume"
    assert result.state.status == "done"
    assert result.state.fields["filler_material"].status == "user_confirmed"
    assert result.state.confirmations[-1].action == "accepted"
    assert result.output_dir == str(run_dir)
    assert (run_dir / "pwps.json").exists()
    assert (run_dir / "pwps_draft.md").exists()
    assert any(entry["node"] == "guided_confirmation_resume" for entry in result.state.trace)
    assert any(entry["node"] == "compose_draft" for entry in result.state.trace)


def test_resume_guided_confirmation_can_only_resume_user_input_state(tmp_path: Path) -> None:
    settings = Settings()
    settings.paths.output_dir = tmp_path
    state = create_initial_state("Q355B 12mm plate GMAW", "guided_confirmation")

    try:
        resume_guided_confirmation(
            state,
            {"fields": {"filler_material": "ER50-6"}},
            settings=settings,
        )
    except ValueError as exc:
        assert "need_user_input" in str(exc)
    else:
        raise AssertionError("resume should reject non-paused states")
