from __future__ import annotations

import json
from typing import Any, Protocol

from pwps_agent.agent.prompt_loader import load_domain_skill_bundle
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
            self._system_prompt(),
            self._user_prompt(state),
            AgentAction,
        )

    def _system_prompt(self) -> str:
        domain_context = load_domain_skill_bundle(self.domain_skill_names)
        return "\n\n".join(
            [
                "You are the LLM Supervisor for a first-stage pWPS draft system.",
                "Choose exactly one next AgentAction. Do not execute tools yourself.",
                "Preserve uncertainty. Do not invent project metadata. Never claim formal approval or compliance.",
                domain_context,
            ]
        )

    def _user_prompt(self, state: PWPSState) -> str:
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
            "knowledge_query_count": len(state.knowledge_queries),
            "evidence_count": len(state.evidence),
            "trace_nodes": [entry.get("node") for entry in state.trace],
            "available_actions": [
                "CALL_TOOL",
                "COMPOSE_DRAFT",
                "FINISH",
            ],
            "available_tools": AVAILABLE_GRAPH_TOOLS,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def supervisor_node(graph_state: GraphState) -> dict:
    state = graph_state["pwps_state"].model_copy(deep=True)
    context = graph_state["context"]
    planner = context.supervisor_planner or DeterministicAutoDraftPlanner()
    action = planner.plan_next_action(state)
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
            },
        }
    )
    return {"pwps_state": state}


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
