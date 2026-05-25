from __future__ import annotations

import json
from typing import Any, Protocol

from pwps_agent.agent.prompt_loader import load_domain_skill, load_domain_skill_bundle
from pwps_agent.core.contracts import AgentAction
from pwps_agent.core.state import PWPSState
from pwps_agent.graph.state import GraphState
from pwps_agent.llm.structured import complete_structured


DEFAULT_DOMAIN_SKILLS = [
    "pwps_auto_draft",
    "pwps_evidence_handling",
    "pwps_risk_review",
]

AVAILABLE_GRAPH_TOOLS = [
    "requirement_understanding",
    "knowledge_planning",
    "local_doc_search",
    "web_search",
    "field_reasoning",
]


class SupervisorPlanner(Protocol):
    def plan_next_action(self, state: PWPSState) -> AgentAction:
        ...


class DeterministicAutoDraftPlanner:
    def plan_next_action(self, state: PWPSState) -> AgentAction:
        return plan_next_auto_draft_action(state)


class LLMSupervisorPlanner:
    def __init__(
        self,
        client: Any,
        domain_skill_names: list[str] | None = None,
    ) -> None:
        self.client = client
        self.domain_skill_names = domain_skill_names or DEFAULT_DOMAIN_SKILLS

    def plan_next_action(self, state: PWPSState) -> AgentAction:
        return complete_structured(
            self.client,
            self._system_prompt(state),
            self._user_prompt(state),
            AgentAction,
        )

    def _system_prompt(self, state: PWPSState) -> str:
        skill_names = state.active_domain_skills or self.domain_skill_names
        domain_context = load_domain_skill_bundle(skill_names)
        return "\n\n".join(
            [
                "You are the LLM Supervisor for a first-stage pWPS draft system.",
                "Choose exactly one next AgentAction. Do not execute tools yourself.",
                "Preserve uncertainty. Do not invent project metadata. Never claim formal approval or compliance.",
                domain_context,
            ]
        )

    def _user_prompt(self, state: PWPSState) -> str:
        active_domain_skills = state.active_domain_skills or self.domain_skill_names
        payload = {
            "task_goal": state.task_goal,
            "interaction_mode": state.interaction_mode,
            "run_id": state.run_id,
            "user_input": state.user_input,
            "status": state.status,
            "core_fields": state.core_fields,
            "field_statuses": {
                name: field.status for name, field in state.fields.items()
            },
            "pending_action": state.pending_action.model_dump()
            if state.pending_action is not None
            else None,
            "knowledge_query_count": len(state.knowledge_queries),
            "evidence_count": len(state.evidence),
            "confirmation_count": len(state.confirmations),
            "recent_trace": state.trace[-5:],
            "risks": state.risks[-10:],
            "field_report": state.field_report,
            "active_domain_skills": active_domain_skills,
            "domain_skill_history": state.domain_skill_history[-10:],
            "available_actions": [
                "USE_DOMAIN_SKILL",
                "CALL_TOOL",
                "ASK_USER",
                "COMPOSE_DRAFT",
                "GENERATE_REPORT",
                "FINISH",
            ],
            "available_tools": AVAILABLE_GRAPH_TOOLS,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def supervisor_node(graph_state: GraphState) -> dict:
    state = graph_state["pwps_state"].model_copy(deep=True)
    context = graph_state["context"]
    planner = context.supervisor_planner or DeterministicAutoDraftPlanner()
    planner_mode = context.supervisor_planner_mode
    if planner_mode is None:
        planner_mode = "injected" if context.supervisor_planner is not None else "deterministic"
    action = planner.plan_next_action(state)
    validation_error = _validate_action(action)
    if validation_error is not None:
        invalid_action = action
        state.status = "failed"
        action = AgentAction(
            action_type="FINISH",
            rationale_summary=f"Invalid supervisor action: {validation_error}",
            expected_state_change="Finish failed graph run.",
            stop_reason="invalid_supervisor_action",
        )
        state.pending_action = action
        state.actions.append(action)
        state.trace.append(
            {
                "step": len(state.trace) + 1,
                "node": "supervisor",
                "event_type": "agent_action_invalid",
                "summary": validation_error,
                "payload": {
                    "planner": planner_mode,
                    "invalid_action": invalid_action.model_dump(),
                },
            }
        )
        return {"pwps_state": state}
    state.pending_action = action
    state.actions.append(action)
    state.trace.append(
        {
            "step": len(state.trace) + 1,
            "node": "supervisor",
            "event_type": "agent_action",
            "summary": action.rationale_summary,
            "payload": {
                "action_type": action.action_type,
                "tool_name": action.tool_name,
                "action_index": len(state.actions),
                "planner": planner_mode,
            },
        }
    )
    return {"pwps_state": state}


def _validate_action(action: AgentAction) -> str | None:
    if action.action_type == "USE_DOMAIN_SKILL":
        if not action.domain_skill_name:
            return "USE_DOMAIN_SKILL requires domain_skill_name"
        try:
            load_domain_skill(action.domain_skill_name)
        except FileNotFoundError:
            return f"Unsupported domain skill: {action.domain_skill_name}"
    if action.action_type == "CALL_TOOL":
        if action.tool_name not in AVAILABLE_GRAPH_TOOLS:
            return f"Unsupported tool action: {action.tool_name}"
    if action.action_type == "UPDATE_STATE":
        operation = action.tool_args.get("operation")
        if operation != "supplement_update":
            return f"Unsupported state update operation: {operation}"
    if action.action_type not in {
        "USE_DOMAIN_SKILL",
        "CALL_TOOL",
        "UPDATE_STATE",
        "ASK_USER",
        "COMPOSE_DRAFT",
        "GENERATE_REPORT",
        "FINISH",
    }:
        return f"Unsupported graph action: {action.action_type}"
    return None


def plan_next_auto_draft_action(state: PWPSState) -> AgentAction:
    completed_nodes = {entry.get("node") for entry in state.trace}
    if "requirement_understanding" not in completed_nodes:
        return _tool_action(
            "requirement_understanding",
            "Extract core pWPS fields from the user requirement.",
        )
    if "knowledge_planning" not in completed_nodes:
        return _tool_action(
            "knowledge_planning",
            "Plan targeted evidence queries for missing or risky fields.",
        )
    if "local_doc_search" not in completed_nodes and _has_local_doc_queries(state):
        return _tool_action(
            "local_doc_search",
            "Search local documents for planned evidence references.",
        )
    if "web_search" not in completed_nodes:
        return _tool_action(
            "web_search",
            "Run planned web searches and convert results into evidence.",
        )
    if "field_reasoning" not in completed_nodes:
        return _tool_action(
            "field_reasoning",
            "Reason traceable candidate fields from collected evidence.",
        )
    if "compose_draft" not in completed_nodes:
        return AgentAction(
            action_type="COMPOSE_DRAFT",
            rationale_summary="Render draft and field report from current state.",
            expected_state_change="Persist draft/report artifacts and attach them to state.",
        )
    return AgentAction(
        action_type="FINISH",
        rationale_summary="The auto-draft graph has produced the required artifacts.",
        expected_state_change="Mark graph run as done.",
        stop_reason="auto_draft_complete",
    )


def _tool_action(tool_name: str, rationale: str) -> AgentAction:
    return AgentAction(
        action_type="CALL_TOOL",
        tool_name=tool_name,
        rationale_summary=rationale,
        expected_state_change=f"Run {tool_name} and merge its state patch.",
    )


def _has_local_doc_queries(state: PWPSState) -> bool:
    return any(
        "local_doc" in (query.get("preferred_sources") or [])
        for query in state.knowledge_queries
    )
