from pwps_agent.core.interaction import build_initial_info_request
from pwps_agent.core.state import create_initial_state
from pwps_agent.config import Settings
from pwps_agent.workflows.auto_draft import AutoDraftDependencies
from pwps_agent.workflows.interaction_resume import (
    apply_interaction_payload,
    resume_interaction,
)


def test_initial_info_resume_preserves_auto_draft_mode_and_fills_fields():
    state = create_initial_state("Need a pWPS draft", "auto_draft")
    state.status = "need_user_input"
    state.pending_interaction = build_initial_info_request(state).model_dump()

    updated = apply_interaction_payload(
        state,
        {
            "fields": {
                "base_material": "Q355B",
                "thickness": "12mm",
                "workpiece_type": "plate",
                "welding_process": "GMAW",
                "joint_type": "butt joint",
                "welding_position": "flat",
            },
            "message": "Initial welding context supplied by user.",
        },
    )

    assert updated.interaction_mode == "auto_draft"
    assert updated.status == "running"
    assert updated.pending_interaction is None
    assert updated.fields["base_material"].value == "Q355B"
    assert updated.fields["base_material"].status == "filled"
    assert updated.fields["base_material"].source["type"] == "user_input"
    assert updated.trace[-1]["node"] == "interaction_resume"
    assert updated.trace[-1]["payload"]["purpose"] == "initial_minimum_context"


def test_resume_interaction_builds_real_dependencies_when_not_injected(monkeypatch):
    state = create_initial_state("Need a pWPS draft", "auto_draft", run_id="resume_deps")
    state.status = "need_user_input"
    state.pending_interaction = build_initial_info_request(state).model_dump()
    sentinel_dependencies = AutoDraftDependencies(
        llm_client=object(),
        search_provider=object(),
    )
    captured = {}

    class FakeGraph:
        def invoke(self, graph_state):
            captured["dependencies"] = graph_state["context"].dependencies
            return {"pwps_state": graph_state["pwps_state"]}

    monkeypatch.setattr(
        "pwps_agent.workflows.interaction_resume._build_dependencies",
        lambda settings: sentinel_dependencies,
    )
    monkeypatch.setattr(
        "pwps_agent.workflows.interaction_resume.build_auto_draft_graph",
        lambda: FakeGraph(),
    )

    resume_interaction(
        state,
        {
            "fields": {
                "base_material": "Q355B",
                "thickness": "12mm",
                "workpiece_type": "plate",
                "welding_process": "GMAW",
                "joint_type": "butt joint",
                "welding_position": "flat",
            }
        },
        settings=Settings(),
    )

    assert captured["dependencies"] is sentinel_dependencies
