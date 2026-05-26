from pathlib import Path

from pwps_agent.config import Settings
from pwps_agent.core.contracts import AgentAction, ToolResult
from pwps_agent.core.state import create_initial_state
from pwps_agent.graph.builder import build_auto_draft_graph
from pwps_agent.graph.nodes import ask_user_node
from pwps_agent.graph.router import route_action
from pwps_agent.graph.state import GraphRuntimeContext
from pwps_agent.graph.supervisor import plan_next_auto_draft_action
from pwps_agent.workflows.auto_draft import AutoDraftDependencies


class PlannerReturningAskUser:
    def plan_next_action(self, state):
        return AgentAction(
            action_type="ASK_USER",
            rationale_summary="Need user confirmation for candidate fields.",
            expected_state_change="Pause with grouped confirmation view.",
        )


class ProgressPlanner:
    def __init__(self, settings: Settings):
        self.settings = settings

    def plan_next_action(self, state):
        return plan_next_auto_draft_action(state, self.settings.knowledge.sources)


class GuidedRequirementTool:
    def __call__(self, state, client):
        return ToolResult(
            tool_name="requirement_understanding",
            success=True,
            state_patch={
                "fields": {
                    "base_material": {"value": "Q355B", "status": "filled"},
                    "thickness": {"value": "12mm", "status": "filled"},
                    "workpiece_type": {"value": "plate", "status": "filled"},
                    "welding_process": {"value": "GMAW", "status": "filled"},
                    "joint_type": {"value": "butt joint", "status": "filled"},
                    "welding_position": {"value": "flat", "status": "filled"},
                }
            },
            summary="understood guided requirement",
        )


class GuidedPlanningTool:
    def __call__(self, state, client):
        return ToolResult(
            tool_name="knowledge_planning",
            success=True,
            state_patch={
                "knowledge_queries": [
                    {
                        "query_id": "kq_guided_001",
                        "purpose": "filler_reference",
                        "query_text": "Q355B GMAW ER50-6",
                        "target_fields": ["filler_material"],
                        "rationale": "Find filler candidate.",
                        "preferred_sources": ["web"],
                    }
                ]
            },
            summary="planned guided query",
        )


class GuidedSearchProvider:
    def search(self, query: str, query_id: str):
        return []


class GuidedReasoningTool:
    def __call__(self, state, evidence, client):
        return ToolResult(
            tool_name="field_reasoning",
            success=True,
            state_patch={
                "fields": {
                    "filler_material": {
                        "value": "ER50-6",
                        "status": "candidate",
                        "confidence": "medium",
                        "evidence_ids": [],
                        "source": {"type": "llm", "evidence_ids": []},
                    }
                }
            },
            summary="reasoned guided candidate",
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
    state.fields["filler_material"].candidates = [
        {
            "value": "ER50-6",
            "suitability": "Common GMAW filler candidate from current evidence.",
            "risk_note": "Confirm project filler classification before promotion.",
            "recommended": True,
        }
    ]

    result = ask_user_node({"pwps_state": state, "context": _context(tmp_path)})

    next_state = result["pwps_state"]
    assert next_state.status == "need_user_input"
    assert next_state.trace[-1]["node"] == "ask_user"
    assert next_state.trace[-1]["payload"]["confirmation_view"]["groups"]
    interaction_request = next_state.trace[-1]["payload"]["interaction_request"]
    assert interaction_request["purpose"] == "guided_field_confirmation"
    assert interaction_request["transport_neutral"] is True
    assert any(
        option["recommended"]
        for question in interaction_request["questions"]
        for option in question["options"]
    )


def test_ask_user_node_pauses_auto_draft_for_initial_context(tmp_path: Path) -> None:
    state = create_initial_state("Need a pWPS draft", "auto_draft")

    result = ask_user_node({"pwps_state": state, "context": _context(tmp_path)})

    next_state = result["pwps_state"]
    interaction_request = next_state.pending_interaction
    assert next_state.status == "need_user_input"
    assert interaction_request["purpose"] == "initial_minimum_context"
    assert interaction_request["questions"][0]["field_ids"] == [
        "base_material",
        "thickness",
        "workpiece_type",
        "welding_process",
        "joint_type",
        "welding_position",
    ]


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


def test_guided_mode_surfaces_verifier_findings_to_user(tmp_path: Path) -> None:
    settings = Settings()
    settings.paths.output_dir = tmp_path
    settings.knowledge.sources = ["web", "model"]
    dependencies = AutoDraftDependencies(
        llm_client=object(),
        search_provider=GuidedSearchProvider(),
        requirement_tool=GuidedRequirementTool(),
        knowledge_planning_tool=GuidedPlanningTool(),
        field_reasoning_tool=GuidedReasoningTool(),
    )
    state = create_initial_state(
        "Q355B 12mm plate GMAW",
        "guided_confirmation",
        run_id="guided_quality_review",
    )

    result = build_auto_draft_graph().invoke(
        {
            "pwps_state": state,
            "context": GraphRuntimeContext(
                settings=settings,
                dependencies=dependencies,
                supervisor_planner=ProgressPlanner(settings),
            ),
        }
    )

    final_state = result["pwps_state"]
    assert final_state.status == "need_user_input"
    assert final_state.quality_report["human_review_fields"]
    assert any(entry["node"] == "draft_verifier" for entry in final_state.trace)
    assert any(entry["node"] == "ask_user" for entry in final_state.trace)
