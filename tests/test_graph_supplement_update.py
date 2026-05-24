from pathlib import Path

from pwps_agent.config import Settings
from pwps_agent.core.contracts import AgentAction
from pwps_agent.core.state import create_initial_state
from pwps_agent.graph.builder import build_auto_draft_graph
from pwps_agent.graph.state import GraphRuntimeContext
from pwps_agent.workflows.auto_draft import AutoDraftDependencies
from pwps_agent.workflows.supplement_update import resume_supplement_update


class PlannerApplyingSupplementThenFinish:
    def plan_next_action(self, state):
        if not any(entry.get("node") == "supplement_update" for entry in state.trace):
            return AgentAction(
                action_type="UPDATE_STATE",
                tool_args={
                    "operation": "supplement_update",
                    "supplement": "Base material is Q355B.",
                    "fields": {"base_material": "Q355B"},
                },
                rationale_summary="Apply user supplemental base material.",
                expected_state_change="Merge supplement into field state.",
            )
        if not any(entry.get("node") == "compose_draft" for entry in state.trace):
            return AgentAction(
                action_type="COMPOSE_DRAFT",
                rationale_summary="Re-compose after supplement.",
                expected_state_change="Persist updated artifacts.",
            )
        return AgentAction(
            action_type="FINISH",
            rationale_summary="Supplement update complete.",
            expected_state_change="Mark run done.",
            stop_reason="supplement_update_complete",
        )


def _context(tmp_path: Path, planner):
    settings = Settings()
    settings.paths.output_dir = tmp_path
    dependencies = AutoDraftDependencies(llm_client=object(), search_provider=object())
    return GraphRuntimeContext(
        settings=settings,
        dependencies=dependencies,
        supervisor_planner=planner,
        checkpoint_enabled=True,
    )


def test_graph_update_state_action_applies_supplement_and_recomposes(tmp_path: Path) -> None:
    state = create_initial_state("Generate pWPS draft.", "auto_draft", run_id="graph_supplement")
    graph = build_auto_draft_graph()

    result = graph.invoke(
        {
            "pwps_state": state,
            "context": _context(tmp_path, PlannerApplyingSupplementThenFinish()),
        }
    )

    final_state = result["pwps_state"]
    assert final_state.status == "done"
    assert final_state.interaction_mode == "supplement_update"
    assert final_state.fields["base_material"].value == "Q355B"
    assert final_state.fields["base_material"].status == "filled"
    assert any(entry["node"] == "supplement_update" for entry in final_state.trace)
    assert (tmp_path / "graph_supplement" / "pwps_draft.md").exists()
    assert (tmp_path / "graph_supplement" / "checkpoints" / "latest.json").exists()


def test_resume_supplement_update_applies_payload_to_done_state(tmp_path: Path) -> None:
    settings = Settings()
    settings.paths.output_dir = tmp_path
    state = create_initial_state("Generate pWPS draft.", "auto_draft", run_id="workflow_supplement")
    state.status = "done"

    result = resume_supplement_update(
        state,
        {
            "supplement": "Base material is Q355B.",
            "fields": {"base_material": "Q355B"},
        },
        settings=settings,
    )

    assert result.state.status == "done"
    assert result.state.interaction_mode == "supplement_update"
    assert result.state.fields["base_material"].value == "Q355B"
    assert result.output_dir == str(tmp_path / "workflow_supplement")
    assert (tmp_path / "workflow_supplement" / "field_report.json").exists()


def test_resume_supplement_update_can_update_need_user_input_state(tmp_path: Path) -> None:
    settings = Settings()
    settings.paths.output_dir = tmp_path
    state = create_initial_state(
        "Generate pWPS draft.",
        "guided_confirmation",
        run_id="supplement_need_user",
    )
    state.status = "need_user_input"
    state.fields["filler_material"].value = "ER50-6"
    state.fields["filler_material"].status = "candidate"

    result = resume_supplement_update(
        state,
        {
            "supplement": "Shielding gas is 80% Ar / 20% CO2.",
            "fields": {"shielding_gas": "80% Ar / 20% CO2"},
        },
        settings=settings,
    )

    assert result.state.status == "done"
    assert result.state.fields["filler_material"].status == "candidate"
    assert result.state.fields["shielding_gas"].value == "80% Ar / 20% CO2"
    assert result.state.interaction_mode == "supplement_update"
