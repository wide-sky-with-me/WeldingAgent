from pathlib import Path

from pwps_agent.config import Settings
from pwps_agent.core.state import create_initial_state
from pwps_agent.graph.checkpoints import save_checkpoint
from pwps_agent.workflows.guided_confirmation import (
    resume_guided_confirmation,
    resume_guided_confirmation_from_checkpoint,
)


def _fill_minimum_core_fields(state) -> None:
    for field_id, value in {
        "applicable_standard": "AWS D1.1",
        "base_material": "Q355B",
        "thickness": "12mm",
        "workpiece_type": "plate",
        "welding_process": "GMAW",
        "joint_type": "butt joint",
        "welding_position": "flat",
    }.items():
        state.fields[field_id].value = value
        state.fields[field_id].status = "filled"


def test_resume_guided_confirmation_applies_payload_and_persists_artifacts(tmp_path: Path) -> None:
    settings = Settings()
    settings.paths.output_dir = tmp_path
    state = create_initial_state(
        "Q355B 12mm plate GMAW",
        "guided_confirmation",
        run_id="guided_resume",
    )
    state.status = "need_user_input"
    _fill_minimum_core_fields(state)
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


def test_resume_guided_confirmation_pauses_again_when_candidates_remain(tmp_path: Path) -> None:
    settings = Settings()
    settings.paths.output_dir = tmp_path
    state = create_initial_state(
        "Q355B 12mm plate GMAW",
        "guided_confirmation",
        run_id="guided_multi_turn",
    )
    state.status = "need_user_input"
    _fill_minimum_core_fields(state)
    state.fields["filler_material"].value = "ER50-6"
    state.fields["filler_material"].status = "candidate"
    state.fields["shielding_gas"].value = "80% Ar / 20% CO2"
    state.fields["shielding_gas"].status = "candidate"

    result = resume_guided_confirmation(
        state,
        {
            "fields": {"filler_material": "ER50-6"},
            "message": "Confirm filler.",
            "action": "accepted",
        },
        settings=settings,
    )

    assert result.state.status == "need_user_input"
    assert result.state.fields["filler_material"].status == "user_confirmed"
    assert result.state.fields["shielding_gas"].status == "candidate"
    assert result.state.trace[-1]["node"] == "ask_user"
    assert (tmp_path / "guided_multi_turn" / "checkpoints" / "latest.json").exists()


def test_resume_guided_confirmation_reverifies_after_final_confirmation(
    tmp_path: Path,
) -> None:
    settings = Settings()
    settings.paths.output_dir = tmp_path
    state = create_initial_state(
        "Q355B 12mm plate GMAW",
        "guided_confirmation",
        run_id="guided_reverify",
    )
    state.status = "need_user_input"
    _fill_minimum_core_fields(state)
    state.fields["shielding_gas"].value = "80% Ar / 20% CO2"
    state.fields["shielding_gas"].status = "candidate"
    state.quality_report = {
        "quality_level": "partial",
        "recommended_action": "synthesize",
        "field_counts": {"candidate": 1},
        "critical_missing_fields": [],
        "weak_evidence_fields": ["shielding_gas"],
        "low_quality_sources": [],
        "blocked_inference_violations": [],
        "refinement_focus_fields": [],
        "human_review_fields": ["shielding_gas"],
        "mode_guidance": "ask_user_for_confirmation",
        "target_field_coverage": [],
        "evidence_quality": {
            "evidence_count": 0,
            "by_source_tier": {},
            "by_source_type": {},
            "low_quality_sources": [],
        },
        "notes": [],
    }
    state.trace.append({"node": "draft_verifier", "event_type": "tool_result"})

    result = resume_guided_confirmation(
        state,
        {
            "fields": {"shielding_gas": "80% Ar / 20% CO2"},
            "message": "Confirm gas.",
            "action": "accepted",
        },
        settings=settings,
    )

    assert result.state.status == "done"
    assert result.state.quality_report["field_counts"]["user_confirmed"] == 1
    resume_index = max(
        index
        for index, entry in enumerate(result.state.trace)
        if entry["node"] == "guided_confirmation_resume"
    )
    assert any(
        entry["node"] == "draft_verifier"
        for entry in result.state.trace[resume_index + 1 :]
    )


def test_resume_guided_confirmation_pauses_again_for_suggested_conflict_or_candidate_options(
    tmp_path: Path,
) -> None:
    settings = Settings()
    settings.paths.output_dir = tmp_path
    state = create_initial_state(
        "Q355B 12mm plate GMAW",
        "guided_confirmation",
        run_id="guided_multi_status",
    )
    state.status = "need_user_input"
    _fill_minimum_core_fields(state)
    state.fields["filler_material"].value = "ER50-6"
    state.fields["filler_material"].status = "candidate"
    state.fields["shielding_gas"].value = "80% Ar / 20% CO2"
    state.fields["shielding_gas"].status = "suggested"
    state.fields["preheat_temperature"].value = "not required"
    state.fields["preheat_temperature"].status = "conflict"
    state.fields["pwht"].candidates.append(
        {"value": "not required", "confidence": "low", "evidence_ids": []}
    )

    result = resume_guided_confirmation(
        state,
        {
            "fields": {"filler_material": "ER50-6"},
            "message": "Confirm filler.",
            "action": "accepted",
        },
        settings=settings,
    )

    assert result.state.status == "need_user_input"
    assert result.state.trace[-1]["node"] == "ask_user"
    view = result.state.trace[-1]["payload"]["confirmation_view"]
    field_ids = {
        field["field_id"]
        for group in view["groups"]
        for field in group["fields"]
    }
    assert {"shielding_gas", "preheat_temperature", "pwht"} <= field_ids


def test_resume_guided_confirmation_from_checkpoint_uses_run_id(tmp_path: Path) -> None:
    settings = Settings()
    settings.paths.output_dir = tmp_path
    state = create_initial_state(
        "Q355B 12mm plate GMAW",
        "guided_confirmation",
        run_id="guided_checkpoint",
    )
    state.status = "need_user_input"
    _fill_minimum_core_fields(state)
    state.fields["filler_material"].value = "ER50-6"
    state.fields["filler_material"].status = "candidate"
    save_checkpoint(state, tmp_path, "ask_user")

    result = resume_guided_confirmation_from_checkpoint(
        run_id="guided_checkpoint",
        payload={
            "fields": {"filler_material": "ER50-6"},
            "message": "Confirm from checkpoint.",
            "action": "accepted",
        },
        settings=settings,
    )

    assert result.state.status == "done"
    assert result.state.fields["filler_material"].status == "user_confirmed"
    assert result.output_dir == str(tmp_path / "guided_checkpoint")
    assert (tmp_path / "guided_checkpoint" / "pwps.json").exists()


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
