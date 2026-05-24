from pathlib import Path

from pwps_agent.config import Settings
from pwps_agent.core.contracts import AgentAction
from pwps_agent.core.state import create_initial_state
from pwps_agent.graph.builder import build_auto_draft_graph
from pwps_agent.graph.state import GraphRuntimeContext
from pwps_agent.graph.nodes import use_domain_skill_node
from pwps_agent.graph.supervisor import LLMSupervisorPlanner, supervisor_node
from pwps_agent.workflows.auto_draft import AutoDraftDependencies


class PlannerReturningCompose:
    def plan_next_action(self, state):
        return AgentAction(
            action_type="COMPOSE_DRAFT",
            rationale_summary="Injected planner selected draft composition.",
            expected_state_change="Render artifacts.",
        )


class PlannerReturningUnsupportedTool:
    def plan_next_action(self, state):
        return AgentAction(
            action_type="CALL_TOOL",
            tool_name="unimplemented_tool",
            rationale_summary="Try an unsupported tool.",
            expected_state_change="Should be rejected.",
        )


class PlannerReturningUnsupportedSkill:
    def plan_next_action(self, state):
        return AgentAction(
            action_type="USE_DOMAIN_SKILL",
            domain_skill_name="missing_skill",
            rationale_summary="Try an unsupported domain skill.",
            expected_state_change="Should be rejected.",
        )


class PlannerSelectingSkillThenFinish:
    def plan_next_action(self, state):
        if "pwps_risk_review" not in state.active_domain_skills:
            return AgentAction(
                action_type="USE_DOMAIN_SKILL",
                domain_skill_name="pwps_risk_review",
                rationale_summary="Activate risk review guidance.",
                expected_state_change="Record active risk skill.",
            )
        return AgentAction(
            action_type="FINISH",
            rationale_summary="Skill selection was recorded.",
            expected_state_change="Finish skill route test.",
            stop_reason="skill_route_test_complete",
        )


class CapturingStructuredClient:
    def __init__(self):
        self.calls = []

    def complete_structured(self, system_prompt, user_prompt, schema):
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "schema": schema,
            }
        )
        return AgentAction(
            action_type="CALL_TOOL",
            tool_name="knowledge_planning",
            rationale_summary="Plan evidence queries from available fields.",
            expected_state_change="Add planned knowledge queries.",
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


def test_supervisor_node_uses_injected_planner(tmp_path: Path):
    state = create_initial_state(
        "Q355B 12mm plate GMAW butt joint flat AWS D1.1 pWPS draft",
        "auto_draft",
        run_id="planner_injection",
    )

    result = supervisor_node(
        {
            "pwps_state": state,
            "context": _context(tmp_path, planner=PlannerReturningCompose()),
        }
    )

    next_state = result["pwps_state"]
    assert next_state.pending_action is not None
    assert next_state.pending_action.action_type == "COMPOSE_DRAFT"
    assert next_state.actions[-1].rationale_summary == (
        "Injected planner selected draft composition."
    )
    supervisor_event = next_state.trace[-1]
    assert supervisor_event["node"] == "supervisor"
    assert supervisor_event["payload"]["action_type"] == "COMPOSE_DRAFT"
    assert supervisor_event["payload"]["action_index"] == 1
    assert supervisor_event["payload"]["planner"] == "injected"


def test_supervisor_node_rejects_unsupported_tool_action(tmp_path: Path):
    state = create_initial_state(
        "Q355B 12mm plate GMAW butt joint flat AWS D1.1 pWPS draft",
        "auto_draft",
        run_id="planner_validation",
    )

    result = supervisor_node(
        {
            "pwps_state": state,
            "context": _context(tmp_path, planner=PlannerReturningUnsupportedTool()),
        }
    )

    next_state = result["pwps_state"]
    assert next_state.status == "failed"
    assert next_state.pending_action is not None
    assert next_state.pending_action.action_type == "FINISH"
    assert next_state.pending_action.stop_reason == "invalid_supervisor_action"
    invalid_event = next_state.trace[-1]
    assert invalid_event["event_type"] == "agent_action_invalid"
    assert "Unsupported tool" in invalid_event["summary"]


def test_use_domain_skill_node_records_active_skill_and_trace(tmp_path: Path):
    state = create_initial_state(
        "Q355B 12mm plate GMAW butt joint flat AWS D1.1 pWPS draft",
        "auto_draft",
        run_id="skill_selection",
    )
    state.pending_action = AgentAction(
        action_type="USE_DOMAIN_SKILL",
        domain_skill_name="pwps_evidence_handling",
        rationale_summary="Use evidence handling guidance before reading web evidence.",
        expected_state_change="Record active evidence skill context.",
    )

    result = use_domain_skill_node(
        {
            "pwps_state": state,
            "context": _context(tmp_path),
        }
    )

    next_state = result["pwps_state"]
    assert next_state.active_domain_skills == ["pwps_evidence_handling"]
    assert next_state.domain_skill_history[-1]["skill_name"] == "pwps_evidence_handling"
    assert next_state.domain_skill_history[-1]["context_id"] == "domain_skill:pwps_evidence_handling"
    skill_event = next_state.trace[-1]
    assert skill_event["node"] == "use_domain_skill"
    assert skill_event["payload"]["skill_name"] == "pwps_evidence_handling"
    assert skill_event["payload"]["context_id"] == "domain_skill:pwps_evidence_handling"


def test_graph_routes_use_domain_skill_back_to_supervisor(tmp_path: Path):
    state = create_initial_state(
        "Q355B 12mm plate GMAW butt joint flat AWS D1.1 pWPS draft",
        "auto_draft",
        run_id="skill_route",
    )
    graph = build_auto_draft_graph()

    result = graph.invoke(
        {
            "pwps_state": state,
            "context": _context(tmp_path, planner=PlannerSelectingSkillThenFinish()),
        }
    )

    final_state = result["pwps_state"]
    assert final_state.status == "done"
    assert final_state.active_domain_skills == ["pwps_risk_review"]
    assert [entry["node"] for entry in final_state.trace] == [
        "supervisor",
        "use_domain_skill",
        "supervisor",
        "finish",
    ]


def test_supervisor_node_rejects_unknown_domain_skill(tmp_path: Path):
    state = create_initial_state(
        "Q355B 12mm plate GMAW butt joint flat AWS D1.1 pWPS draft",
        "auto_draft",
        run_id="skill_validation",
    )

    result = supervisor_node(
        {
            "pwps_state": state,
            "context": _context(tmp_path, planner=PlannerReturningUnsupportedSkill()),
        }
    )

    next_state = result["pwps_state"]
    assert next_state.status == "failed"
    assert next_state.pending_action is not None
    assert next_state.pending_action.action_type == "FINISH"
    assert next_state.pending_action.stop_reason == "invalid_supervisor_action"
    invalid_event = next_state.trace[-1]
    assert invalid_event["event_type"] == "agent_action_invalid"
    assert "Unsupported domain skill" in invalid_event["summary"]


def test_llm_supervisor_planner_requests_structured_agent_action():
    client = CapturingStructuredClient()
    planner = LLMSupervisorPlanner(client=client)
    state = create_initial_state(
        "Q355B 12mm plate GMAW butt joint flat AWS D1.1 pWPS draft",
        "auto_draft",
        run_id="llm_planner",
    )
    state.core_fields = {
        "base_material": "Q355B",
        "thickness": "12mm",
        "welding_process": "GMAW",
    }
    state.pending_action = AgentAction(
        action_type="CALL_TOOL",
        tool_name="requirement_understanding",
        rationale_summary="Previous pending action.",
        expected_state_change="Extract fields.",
    )
    state.risks.append({"field_id": "pwht", "severity": "medium", "message": "PWHT unknown."})
    state.field_report = {"missing_fields": ["shielding_gas"]}
    state.trace.append(
        {
            "step": 1,
            "node": "requirement_understanding",
            "event_type": "tool_result",
            "summary": "Extracted core fields.",
            "payload": {"success": True},
        }
    )

    action = planner.plan_next_action(state)

    assert action.action_type == "CALL_TOOL"
    assert action.tool_name == "knowledge_planning"
    assert client.calls[0]["schema"] is AgentAction
    assert "Domain Skill: pwps_auto_draft" in client.calls[0]["system_prompt"]
    assert "available_tools" in client.calls[0]["user_prompt"]
    assert "pending_action" in client.calls[0]["user_prompt"]
    assert "recent_trace" in client.calls[0]["user_prompt"]
    assert "risks" in client.calls[0]["user_prompt"]
    assert "field_report" in client.calls[0]["user_prompt"]
    assert "Q355B" in client.calls[0]["user_prompt"]


def test_llm_supervisor_planner_uses_active_domain_skill_context():
    client = CapturingStructuredClient()
    planner = LLMSupervisorPlanner(client=client)
    state = create_initial_state(
        "Q355B 12mm plate GMAW butt joint flat AWS D1.1 pWPS draft",
        "auto_draft",
        run_id="llm_active_skill",
    )
    state.active_domain_skills = ["pwps_guided_confirmation"]

    planner.plan_next_action(state)

    assert "Domain Skill: pwps_guided_confirmation" in client.calls[0]["system_prompt"]
    assert "Domain Skill: pwps_auto_draft" not in client.calls[0]["system_prompt"]
    assert "active_domain_skills" in client.calls[0]["user_prompt"]
