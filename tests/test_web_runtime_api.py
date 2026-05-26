from pathlib import Path

from pwps_agent.core.interaction import attach_interaction_request, build_initial_info_request
from pwps_agent.core.state import create_initial_state
from pwps_agent.web.runtime_api import (
    apply_run_response,
    build_run_snapshot,
    load_run_state,
    save_run_state,
)


def test_run_snapshot_is_mode_neutral(tmp_path: Path) -> None:
    state = create_initial_state("Need pWPS", "auto_draft", run_id="api_auto")
    state.status = "need_user_input"
    attach_interaction_request(state, build_initial_info_request(state))

    snapshot = build_run_snapshot(state, output_dir=tmp_path / "api_auto")

    assert snapshot["run_id"] == "api_auto"
    assert snapshot["mode"] == "auto_draft"
    assert snapshot["interaction_mode"] == "auto_draft"
    assert snapshot["status"] == "need_user_input"
    assert snapshot["pending_interaction"]["purpose"] == "initial_minimum_context"
    assert "fields" in snapshot
    assert "base_material" in snapshot["fields"]


def test_run_state_round_trip(tmp_path: Path) -> None:
    state = create_initial_state("Need pWPS", "auto_draft", run_id="api_roundtrip")
    save_run_state(tmp_path, state)

    loaded = load_run_state(tmp_path, "api_roundtrip")

    assert loaded.run_id == "api_roundtrip"
    assert loaded.interaction_mode == "auto_draft"


def test_apply_run_response_normalizes_raw_text(monkeypatch, tmp_path: Path) -> None:
    state = create_initial_state("Need pWPS", "auto_draft", run_id="api_response")
    state.status = "need_user_input"
    attach_interaction_request(state, build_initial_info_request(state))
    save_run_state(tmp_path, state)

    def fake_resume_interaction(state, payload, settings):
        updated = state.model_copy(deep=True)
        updated.status = "done"
        updated.pending_interaction = None
        updated.fields["base_material"].value = payload["fields"]["base_material"]
        return type("Result", (), {"state": updated, "output_dir": str(tmp_path / state.run_id)})()

    monkeypatch.setattr("pwps_agent.web.runtime_api.resume_interaction", fake_resume_interaction)

    snapshot = apply_run_response(
        tmp_path,
        "api_response",
        {"message": "base_material=Q355B"},
    )

    assert snapshot["status"] == "done"
    assert snapshot["fields"]["base_material"]["value"] == "Q355B"
    assert load_run_state(tmp_path, "api_response").status == "done"
