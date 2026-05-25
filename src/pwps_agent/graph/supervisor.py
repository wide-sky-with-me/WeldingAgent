from __future__ import annotations

import json
import logging
from typing import Any, Protocol

from pwps_agent.agent.prompt_loader import load_domain_skill, load_domain_skill_bundle
from pwps_agent.core.contracts import AgentAction
from pwps_agent.core.state import PWPSState
from pwps_agent.graph.policy import (
    GraphPolicy,
    is_refinement_planning_action,
    plan_next_auto_draft_action,
)
from pwps_agent.graph.state import GraphState
from pwps_agent.llm.structured import complete_structured


DEFAULT_DOMAIN_SKILLS = [
    "pwps_auto_draft",
    "pwps_evidence_handling",
    "pwps_risk_review",
]

GUIDED_CONFIRMATION_DOMAIN_SKILLS = [
    "pwps_guided_confirmation",
    "pwps_evidence_handling",
    "pwps_risk_review",
]

AVAILABLE_GRAPH_TOOLS = [
    "requirement_understanding",
    "knowledge_planning",
    "local_doc_search",
    "web_search",
    "field_reasoning",
    "guided_options",
]

LOGGER = logging.getLogger(__name__)


class SupervisorPlanner(Protocol):
    def plan_next_action(self, state: PWPSState) -> AgentAction:
        ...


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
        skill_names = state.active_domain_skills or self._default_skill_names(state)
        domain_context = load_domain_skill_bundle(skill_names)
        return "\n\n".join(
            [
                "You are the LLM Supervisor for a first-stage pWPS draft system.",
                "Choose exactly one next AgentAction. Do not execute tools yourself.",
                "Preserve uncertainty. Do not invent project metadata. Never claim formal approval or compliance.",
                self._mode_instruction(state),
                domain_context,
            ]
        )

    def _user_prompt(self, state: PWPSState) -> str:
        active_domain_skills = state.active_domain_skills or self._default_skill_names(state)
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
                "VERIFY_DRAFT",
                "COMPOSE_DRAFT",
                "GENERATE_REPORT",
                "FINISH",
            ],
            "available_tools": AVAILABLE_GRAPH_TOOLS,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    def _default_skill_names(self, state: PWPSState) -> list[str]:
        if self.domain_skill_names != DEFAULT_DOMAIN_SKILLS:
            return self.domain_skill_names
        if state.interaction_mode == "guided_confirmation":
            return GUIDED_CONFIRMATION_DOMAIN_SKILLS
        return self.domain_skill_names

    def _mode_instruction(self, state: PWPSState) -> str:
        if state.interaction_mode == "guided_confirmation":
            return (
                "Interaction mode is guided_confirmation: ask the user when critical "
                "information is missing or fields need confirmation. Present concise "
                "options, explain the tradeoff/evidence for each option, and keep "
                "iterating until no candidate, suggested, conflict, or explicit "
                "candidate-option fields remain."
            )
        if state.interaction_mode == "auto_draft":
            return (
                "Interaction mode is auto_draft: do not ask the user. Act as the "
                "autonomous drafter, use configured local/web knowledge sources, use "
                "model fallback only as suggested low-confidence values, and complete "
                "the draft with uncertainty clearly marked."
            )
        return (
            "Interaction mode is supplement_update: apply the supplemental user "
            "information, regenerate affected draft/report artifacts, and preserve "
            "source and confirmation status."
        )


def supervisor_node(graph_state: GraphState) -> dict:
    state = graph_state["pwps_state"].model_copy(deep=True)
    context = graph_state["context"]
    planner = context.supervisor_planner or LLMSupervisorPlanner(
        client=context.dependencies.llm_client
    )
    planner_mode = context.supervisor_planner_mode
    if planner_mode is None:
        planner_mode = "injected" if context.supervisor_planner is not None else "llm"
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
    policy_decision = GraphPolicy(
        knowledge_sources=context.settings.knowledge.sources,
        planner_mode=planner_mode,
    ).resolve(action, state)
    if policy_decision.overridden:
        override_action = policy_decision.action
        state.trace.append(
            {
                "step": len(state.trace) + 1,
                "node": "supervisor",
                "event_type": "agent_action_overridden",
                "summary": policy_decision.summary
                or "Planner action was overridden by graph policy.",
                "payload": {
                    "planner": planner_mode,
                    "reason_code": policy_decision.reason_code,
                    "requested_action_type": action.action_type,
                    "requested_tool_name": action.tool_name,
                    "requested_domain_skill_name": action.domain_skill_name,
                    "replacement_action_type": override_action.action_type,
                    "replacement_tool_name": override_action.tool_name,
                },
            }
        )
        LOGGER.warning(
            "Overrode repeated completed planner action planner=%s requested=%s tool=%s replacement=%s tool=%s",
            planner_mode,
            action.action_type,
            action.tool_name,
            override_action.action_type,
            override_action.tool_name,
        )
        action = override_action
    if is_refinement_planning_action(action):
        state.refinement_attempts += 1
    state.pending_action = action
    state.actions.append(action)
    LOGGER.info(
        "Supervisor selected action=%s tool=%s skill=%s planner=%s run_id=%s",
        action.action_type,
        action.tool_name,
        action.domain_skill_name,
        planner_mode,
        state.run_id,
    )
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
                "refinement_attempts": state.refinement_attempts,
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
        "VERIFY_DRAFT",
        "COMPOSE_DRAFT",
        "GENERATE_REPORT",
        "FINISH",
    }:
        return f"Unsupported graph action: {action.action_type}"
    return None
