from pathlib import Path

from pwps_agent.config import Settings
from pwps_agent.core.contracts import AgentAction
from pwps_agent.core.state import create_initial_state
from pwps_agent.graph.builder import build_auto_draft_graph
from pwps_agent.graph.nodes import ask_user_node
from pwps_agent.graph.router import route_action
from pwps_agent.graph.state import GraphRuntimeContext
from pwps_agent.workflows.auto_draft import AutoDraftDependencies


class PlannerReturningAskUser:
    def plan_next_action(self, state):
        return AgentAction(
            action_type="ASK_USER",
            rationale_summary="Need user confirmation for candidate fields.",
            expected_state_change="Pause with grouped confirmation view.",
        )


def _context(tmp_path: Path, planner=None):
    settings = Settings()
    settings.paths.output_dir = tmp_path
    dependencies = AutoDraftDependencies(
        llm_client=object(),
        search_provider=object(),
    )
    return GraphRuntimeContext(
        settings=settings,
        dependencies=dependencies,
        supervisor_planner=planner,
    )


def test_route_action_sends_ask_user_to_interaction_node(tmp_path: Path) -> None:
    state = create_initial_state("Q355B 12mm GMAW", "guided_confirmation")
    state.pending_action = AgentAction(
        action_type="ASK_USER",
        rationale_summary="Confirm candidate fields.",
    )

    assert route_action({"pwps_state": state, "context": _context(tmp_path)}) == "ask_user"


def test_ask_user_node_pauses_with_confirmation_view(tmp_path: Path) -> None:
    state = create_initial_state("Q355B 12mm GMAW", "guided_confirmation")
    state.fields["filler_material"].value = "ER50-6"
    state.fields["filler_material"].status = "candidate"

    result = ask_user_node({"pwps_state": state, "context": _context(tmp_path)})

    next_state = result["pwps_state"]
    assert next_state.status == "need_user_input"
    assert next_state.trace[-1]["node"] == "ask_user"
    assert next_state.trace[-1]["payload"]["confirmation_view"]["groups"]


def test_graph_can_pause_on_injected_ask_user_action(tmp_path: Path) -> None:
    state = create_initial_state(
        "Q355B 12mm GMAW",
        "guided_confirmation",
        run_id="guided_graph",
    )
    state.fields["filler_material"].value = "ER50-6"
    state.fields["filler_material"].status = "candidate"

    graph = build_auto_draft_graph()
    result = graph.invoke(
        {
            "pwps_state": state,
            "context": _context(tmp_path, planner=PlannerReturningAskUser()),
        }
    )

    final_state = result["pwps_state"]
    assert final_state.status == "need_user_input"
    assert final_state.trace[-1]["node"] == "ask_user"
