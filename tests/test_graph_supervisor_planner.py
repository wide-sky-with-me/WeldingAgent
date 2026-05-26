from pathlib import Path
import inspect

from pwps_agent.config import Settings
from pwps_agent.core.contracts import AgentAction, SearchResult, ToolResult
from pwps_agent.core.state import create_initial_state
from pwps_agent.graph.builder import build_auto_draft_graph
from pwps_agent.graph.policy import GraphPolicy
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


class StaticRequirementTool:
    def __call__(self, state, client):
        return ToolResult(
            tool_name="requirement_understanding",
            success=True,
            state_patch={
                "core_fields": {
                    "base_material": "Q355B",
                    "thickness": "12mm",
                    "welding_process": "GMAW",
                },
                "fields": {
                    "base_material": {"value": "Q355B", "status": "filled"},
                    "thickness": {"value": "12mm", "status": "filled"},
                    "welding_process": {"value": "GMAW", "status": "filled"},
                },
            },
            summary="understood requirement",
        )


class StaticPlanningTool:
    def __call__(self, state, client):
        return ToolResult(
            tool_name="knowledge_planning",
            success=True,
            state_patch={
                "knowledge_queries": [
                    {
                        "query_id": "kq_001",
                        "purpose": "similar_case",
                        "query_text": "Q355B 12mm GMAW WPS shielding gas",
                        "target_fields": ["shielding_gas"],
                        "rationale": "Find similar gas references.",
                        "preferred_sources": ["web"],
                    }
                ]
            },
            summary="planned query",
        )


class StaticSearchProvider:
    def search(self, query: str, query_id: str):
        return [
            SearchResult(
                result_id="r1",
                query_id=query_id,
                provider="tavily",
                title="WPS example",
                url="https://example.test/wps",
                snippet="Ar+CO2 shielding gas appears in a comparable GMAW WPS.",
            )
        ]


class StaticReasoningTool:
    def __call__(self, state, evidence, client):
        return ToolResult(
            tool_name="field_reasoning",
            success=True,
            state_patch={
                "fields": {
                    "shielding_gas": {
                        "value": "Ar+CO2",
                        "status": "candidate",
                        "confidence": "medium",
                        "evidence_ids": ["ev_r1"],
                    }
                }
            },
            summary="reasoned field",
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


class PlannerRepeatingCompletedRequirementTool:
    def plan_next_action(self, state):
        return AgentAction(
            action_type="CALL_TOOL",
            tool_name="requirement_understanding",
            rationale_summary="Repeat requirement extraction even after it completed.",
            expected_state_change="This should be guarded by the graph supervisor.",
        )


class PlannerAskingUserAfterCompose:
    def plan_next_action(self, state):
        if "compose_draft" in {entry.get("node") for entry in state.trace}:
            return AgentAction(
                action_type="ASK_USER",
                rationale_summary="Ask user even though auto-draft artifacts already exist.",
                expected_state_change="This should finish instead of pausing auto-draft.",
            )
        return AgentAction(
            action_type="COMPOSE_DRAFT",
            rationale_summary="Compose draft first.",
            expected_state_change="Persist draft artifacts.",
        )


class PlannerAskingUserImmediately:
    def plan_next_action(self, state):
        return AgentAction(
            action_type="ASK_USER",
            rationale_summary="Ask user before gathering evidence.",
            expected_state_change="This should be guarded in auto-draft.",
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


def test_graph_overrides_repeated_completed_llm_tool_action(tmp_path: Path):
    settings = Settings()
    settings.paths.output_dir = tmp_path
    dependencies = AutoDraftDependencies(
        llm_client=object(),
        search_provider=StaticSearchProvider(),
        requirement_tool=StaticRequirementTool(),
        knowledge_planning_tool=StaticPlanningTool(),
        field_reasoning_tool=StaticReasoningTool(),
    )
    state = create_initial_state(
        "Q355B 12mm plate GMAW butt joint flat AWS D1.1 pWPS draft",
        "auto_draft",
        run_id="repeat_tool_guard",
    )

    result = build_auto_draft_graph().invoke(
        {
            "pwps_state": state,
            "context": GraphRuntimeContext(
                settings=settings,
                dependencies=dependencies,
                supervisor_planner=PlannerRepeatingCompletedRequirementTool(),
                supervisor_planner_mode="llm",
            ),
        }
    )

    final_state = result["pwps_state"]
    assert final_state.status == "done"
    assert [entry["node"] for entry in final_state.trace].count("requirement_understanding") == 1
    assert any(
        entry["node"] == "supervisor"
        and entry["event_type"] == "agent_action_overridden"
        and entry["payload"]["reason_code"] == "completed_action"
        and entry["payload"]["requested_tool_name"] == "requirement_understanding"
        for entry in final_state.trace
    )


def test_graph_policy_resolves_completed_action_with_reason_code():
    state = create_initial_state("Q355B 12mm GMAW", "auto_draft")
    state.trace.append({"node": "requirement_understanding", "event_type": "tool_result"})
    action = AgentAction(
        action_type="CALL_TOOL",
        tool_name="requirement_understanding",
        rationale_summary="repeat",
    )

    decision = GraphPolicy(planner_mode="llm").resolve(action, state)

    assert decision.overridden is True
    assert decision.reason_code == "completed_action"
    assert decision.action.tool_name == "knowledge_planning"


def test_graph_policy_resolves_premature_finish_with_reason_code():
    state = create_initial_state("Q355B 12mm GMAW", "auto_draft")
    state.trace.append({"node": "field_reasoning", "event_type": "tool_result"})
    action = AgentAction(action_type="FINISH", rationale_summary="finish")

    decision = GraphPolicy(planner_mode="llm").resolve(action, state)

    assert decision.overridden is True
    assert decision.reason_code == "premature_finish"
    assert decision.action.action_type == "VERIFY_DRAFT"


def test_graph_policy_resolves_auto_draft_initial_gate_with_reason_code():
    state = create_initial_state("Need a pWPS draft", "auto_draft")
    action = AgentAction(action_type="COMPOSE_DRAFT", rationale_summary="compose")

    decision = GraphPolicy(planner_mode="llm").resolve(action, state)

    assert decision.overridden is True
    assert decision.reason_code == "auto_draft_initial_gate"
    assert decision.action.action_type == "ASK_USER"


def test_graph_policy_resolves_guided_confirmation_required_with_reason_code():
    state = create_initial_state("Q355B 12mm GMAW", "guided_confirmation")
    state.quality_report = {
        "quality_level": "partial",
        "recommended_action": "synthesize",
        "field_counts": {},
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
    action = AgentAction(action_type="FINISH", rationale_summary="finish")

    decision = GraphPolicy().resolve(action, state)

    assert decision.overridden is True
    assert decision.reason_code == "guided_confirmation_required"
    assert decision.action.action_type == "ASK_USER"


def test_graph_policy_prevents_empty_guided_confirmation_pause():
    state = create_initial_state("Q355B 12mm GMAW", "guided_confirmation")
    state.trace.append({"node": "requirement_understanding", "event_type": "tool_result"})
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
    action = AgentAction(action_type="ASK_USER", rationale_summary="ask too early")

    decision = GraphPolicy().resolve(action, state)

    assert decision.overridden is True
    assert decision.reason_code == "guided_confirmation_empty"
    assert decision.action.action_type == "CALL_TOOL"
    assert decision.action.tool_name == "knowledge_planning"


def test_graph_policy_prevents_empty_guided_options_tool_call():
    state = create_initial_state("Q355B 12mm GMAW", "guided_confirmation")
    state.trace.append({"node": "requirement_understanding", "event_type": "tool_result"})
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
    action = AgentAction(
        action_type="CALL_TOOL",
        tool_name="guided_options",
        rationale_summary="recommend too early",
    )

    decision = GraphPolicy().resolve(action, state)

    assert decision.overridden is True
    assert decision.reason_code == "guided_confirmation_empty"
    assert decision.action.action_type == "CALL_TOOL"
    assert decision.action.tool_name == "knowledge_planning"


def test_graph_finishes_auto_draft_when_planner_asks_user_after_compose(tmp_path: Path):
    state = create_initial_state(
        "Q355B 12mm plate GMAW butt joint flat AWS D1.1 pWPS draft",
        "auto_draft",
        run_id="ask_after_compose",
    )
    graph = build_auto_draft_graph()

    result = graph.invoke(
        {
            "pwps_state": state,
            "context": _context(tmp_path, planner=PlannerAskingUserAfterCompose()),
        }
    )

    final_state = result["pwps_state"]
    assert final_state.status == "done"
    assert any(entry["node"] == "compose_draft" for entry in final_state.trace)
    assert not any(entry["node"] == "ask_user" for entry in final_state.trace)
    assert any(
        entry["node"] == "supervisor"
        and entry["event_type"] == "agent_action_overridden"
        and entry["payload"]["reason_code"] == "completed_action"
        and entry["payload"]["requested_action_type"] == "ASK_USER"
        and entry["payload"]["replacement_action_type"] == "FINISH"
        for entry in final_state.trace
    )


def test_graph_auto_draft_overrides_planner_asking_user_before_compose(tmp_path: Path):
    state = create_initial_state(
        "Q355B 12mm plate GMAW butt joint flat AWS D1.1 pWPS draft",
        "auto_draft",
        run_id="ask_before_compose",
    )

    result = supervisor_node(
        {
            "pwps_state": state,
            "context": _context(tmp_path, planner=PlannerAskingUserImmediately()),
        }
    )

    next_state = result["pwps_state"]
    assert next_state.pending_action is not None
    assert next_state.pending_action.action_type == "ASK_USER"
    assert next_state.trace[-2]["event_type"] == "agent_action_overridden"
    assert next_state.trace[-2]["payload"]["requested_action_type"] == "ASK_USER"
    assert next_state.trace[-2]["payload"]["reason_code"] == "auto_draft_initial_gate"


def test_graph_guided_mode_asks_user_after_compose_when_candidates_remain(tmp_path: Path):
    state = create_initial_state(
        "Q355B 12mm plate GMAW butt joint flat AWS D1.1 pWPS draft",
        "guided_confirmation",
        run_id="guided_ask_after_compose",
    )
    state.fields["shielding_gas"].value = "CO2"
    state.fields["shielding_gas"].status = "candidate"
    graph = build_auto_draft_graph()

    result = graph.invoke(
        {
            "pwps_state": state,
            "context": _context(tmp_path, planner=PlannerAskingUserAfterCompose()),
        }
    )

    final_state = result["pwps_state"]
    assert final_state.status == "need_user_input"
    assert any(entry["node"] == "compose_draft" for entry in final_state.trace)
    assert final_state.trace[-1]["node"] == "ask_user"


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


def test_llm_supervisor_planner_describes_mode_specific_closure_rules():
    client = CapturingStructuredClient()
    planner = LLMSupervisorPlanner(client=client)
    auto_state = create_initial_state("Q355B 12mm GMAW", "auto_draft", run_id="auto_mode")
    guided_state = create_initial_state(
        "Q355B 12mm GMAW",
        "guided_confirmation",
        run_id="guided_mode",
    )

    planner.plan_next_action(auto_state)
    planner.plan_next_action(guided_state)

    auto_prompt = client.calls[0]["system_prompt"]
    guided_prompt = client.calls[1]["system_prompt"]
    assert "do not ask the user" in auto_prompt
    assert "model fallback" in auto_prompt
    assert "ask the user" in guided_prompt
    assert "options" in guided_prompt
    assert "Domain Skill: pwps_guided_confirmation" in guided_prompt


def test_llm_supervisor_planner_loads_production_prompt_text_from_prompt_files():
    source = inspect.getsource(LLMSupervisorPlanner._system_prompt)

    assert 'load_prompt("supervisor")' in source
    assert "You are the LLM Supervisor" not in source
    assert "Interaction mode is auto_draft" not in source


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
