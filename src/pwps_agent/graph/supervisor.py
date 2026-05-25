from __future__ import annotations

import json
import logging
from typing import Any, Protocol

from pwps_agent.agent.prompt_loader import load_domain_skill, load_domain_skill_bundle
from pwps_agent.core.contracts import AgentAction
from pwps_agent.core.modes import GUIDED_CORE_CONFIRMATION_FIELDS
from pwps_agent.core.state import PWPSState
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
    override_action = _override_repeated_completed_action(
        state,
        action,
        context.settings.knowledge.sources,
        planner_mode=planner_mode,
    )
    if override_action is not None:
        state.trace.append(
            {
                "step": len(state.trace) + 1,
                "node": "supervisor",
                "event_type": "agent_action_overridden",
                "summary": "Planner requested an already completed action; using safe next action.",
                "payload": {
                    "planner": planner_mode,
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
    if _is_refinement_planning_action(action):
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


def _override_repeated_completed_action(
    state: PWPSState,
    action: AgentAction,
    knowledge_sources: list[str] | None = None,
    planner_mode: str = "injected",
) -> AgentAction | None:
    last = _last_node_indexes(state)
    if (
        _node_completed(state, "compose_draft")
        and state.interaction_mode == "guided_confirmation"
        and _has_pending_confirmation_fields(state)
    ):
        if action.action_type != "ASK_USER":
            return AgentAction(
                action_type="ASK_USER",
                rationale_summary="Draft artifacts are composed and fields still need guided confirmation.",
                expected_state_change="Pause with grouped confirmation view.",
            )
        return None
    if _node_completed(state, "compose_draft") and action.action_type != "FINISH":
        return AgentAction(
            action_type="FINISH",
            rationale_summary="Draft artifacts are already composed; finish auto-draft run.",
            expected_state_change="Mark graph run as done.",
            stop_reason="auto_draft_complete",
        )
    if (
        _node_completed(state, "field_reasoning")
        and not _node_completed(state, "draft_verifier")
        and action.action_type in {"COMPOSE_DRAFT", "FINISH"}
    ):
        return AgentAction(
            action_type="VERIFY_DRAFT",
            rationale_summary="Verify draft quality before synthesis.",
            expected_state_change="Attach deterministic quality report to state.",
        )
    if (
        planner_mode == "llm"
        and _workflow_started(state)
        and not _node_completed(state, "compose_draft")
        and action.action_type in {"COMPOSE_DRAFT", "FINISH"}
    ):
        safe_next = plan_next_auto_draft_action(state, knowledge_sources)
        if action.action_type == "FINISH" or safe_next.action_type != "COMPOSE_DRAFT":
            return safe_next
    if (
        _needs_refinement_planning(state, last)
        and action.action_type in {"COMPOSE_DRAFT", "FINISH"}
    ):
        return plan_next_auto_draft_action(state, knowledge_sources)
    if (
        _needs_guided_confirmation_pause(state)
        and action.action_type in {"COMPOSE_DRAFT", "FINISH"}
    ):
        return AgentAction(
            action_type="ASK_USER",
            rationale_summary="Verifier found fields that need guided human review.",
            expected_state_change="Pause with grouped confirmation view.",
        )
    if (
        _node_completed(state, "draft_verifier")
        and not _node_completed(state, "compose_draft")
        and action.action_type == "FINISH"
    ):
        return AgentAction(
            action_type="COMPOSE_DRAFT",
            rationale_summary="Quality verification is complete; compose draft artifacts.",
            expected_state_change="Persist draft/report artifacts and attach them to state.",
        )
    if state.interaction_mode == "auto_draft" and action.action_type == "ASK_USER":
        return plan_next_auto_draft_action(state, knowledge_sources)
    if action.action_type == "CALL_TOOL" and action.tool_name:
        if _node_completed(state, action.tool_name):
            return plan_next_auto_draft_action(state, knowledge_sources)
    if action.action_type == "USE_DOMAIN_SKILL" and action.domain_skill_name:
        if action.domain_skill_name in state.active_domain_skills:
            return plan_next_auto_draft_action(state, knowledge_sources)
    if action.action_type == "UPDATE_STATE":
        if action.tool_args.get("operation") == "supplement_update" and _node_completed(
            state,
            "supplement_update",
        ):
            return plan_next_auto_draft_action(state, knowledge_sources)
    if action.action_type == "COMPOSE_DRAFT" and _node_completed(state, "compose_draft"):
        return plan_next_auto_draft_action(state, knowledge_sources)
    if action.action_type == "GENERATE_REPORT" and _node_completed(state, "risk_report"):
        return plan_next_auto_draft_action(state, knowledge_sources)
    if action.action_type == "VERIFY_DRAFT" and _node_completed(state, "draft_verifier"):
        return plan_next_auto_draft_action(state, knowledge_sources)
    return None


def _node_completed(state: PWPSState, node: str) -> bool:
    return any(entry.get("node") == node for entry in state.trace)


def _workflow_started(state: PWPSState) -> bool:
    workflow_nodes = {
        "requirement_understanding",
        "knowledge_planning",
        "local_doc_search",
        "web_search",
        "field_reasoning",
        "draft_verifier",
    }
    return any(entry.get("node") in workflow_nodes for entry in state.trace)


def _has_pending_confirmation_fields(state: PWPSState) -> bool:
    return any(
        field.status in {"candidate", "suggested", "need_confirmation", "conflict"}
        or (field.status != "user_confirmed" and bool(field.candidates))
        or (
            state.interaction_mode == "guided_confirmation"
            and field.field_id in GUIDED_CORE_CONFIRMATION_FIELDS
            and field.status == "missing"
        )
        for field in state.fields.values()
    )


def plan_next_auto_draft_action(
    state: PWPSState,
    knowledge_sources: list[str] | None = None,
) -> AgentAction:
    sources = knowledge_sources or ["local_doc", "web"]
    completed_nodes = {entry.get("node") for entry in state.trace}
    last = _last_node_indexes(state)
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
    if _needs_refinement_planning(state, last):
        return AgentAction(
            action_type="CALL_TOOL",
            tool_name="knowledge_planning",
            tool_args={"operation": "refinement"},
            rationale_summary=(
                "Verifier found critical gaps; plan refinement queries before synthesis."
            ),
            expected_state_change="Add refinement knowledge queries for uncovered fields.",
        )
    if (
        "local_doc" in sources
        and _node_needs_refresh(last, "local_doc_search", "knowledge_planning")
        and _has_local_doc_queries(state)
    ):
        return _tool_action(
            "local_doc_search",
            "Search local documents for planned evidence references.",
        )
    if (
        "web" in sources
        and _node_needs_refresh(last, "web_search", "knowledge_planning")
        and _has_web_queries(state)
    ):
        return _tool_action(
            "web_search",
            "Run planned web searches and convert results into evidence.",
        )
    if _node_needs_refresh_after_any(
        last,
        "field_reasoning",
        ["web_search", "local_doc_search", "knowledge_planning"],
    ):
        return _tool_action(
            "field_reasoning",
            "Reason traceable candidate fields from collected evidence.",
        )
    if _node_needs_refresh(last, "draft_verifier", "field_reasoning"):
        return AgentAction(
            action_type="VERIFY_DRAFT",
            rationale_summary="Verify draft quality before synthesis.",
            expected_state_change="Attach deterministic quality report to state.",
        )
    if _needs_guided_confirmation_pause(state):
        return AgentAction(
            action_type="ASK_USER",
            rationale_summary="Verifier found fields that need guided human review.",
            expected_state_change="Pause with grouped confirmation view.",
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


def _is_refinement_planning_action(action: AgentAction) -> bool:
    return (
        action.action_type == "CALL_TOOL"
        and action.tool_name == "knowledge_planning"
        and action.tool_args.get("operation") == "refinement"
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


def _has_web_queries(state: PWPSState) -> bool:
    return any(
        "web" in (query.get("preferred_sources") or ["web"])
        for query in state.knowledge_queries
    )


def _last_node_indexes(state: PWPSState) -> dict[str, int]:
    indexes: dict[str, int] = {}
    for index, entry in enumerate(state.trace):
        node = entry.get("node")
        if isinstance(node, str):
            indexes[node] = index
    return indexes


def _node_needs_refresh(last: dict[str, int], node: str, dependency: str) -> bool:
    return last.get(node, -1) < last.get(dependency, -1)


def _node_needs_refresh_after_any(
    last: dict[str, int],
    node: str,
    dependencies: list[str],
) -> bool:
    return last.get(node, -1) < max((last.get(dep, -1) for dep in dependencies), default=-1)


def _needs_refinement_planning(state: PWPSState, last: dict[str, int]) -> bool:
    report = state.quality_report or {}
    return (
        state.interaction_mode == "auto_draft"
        and report.get("recommended_action") == "refine_search"
        and state.refinement_attempts < state.max_refinement_attempts
        and last.get("draft_verifier", -1) > last.get("knowledge_planning", -1)
    )


def _needs_guided_confirmation_pause(state: PWPSState) -> bool:
    report = state.quality_report or {}
    return (
        state.interaction_mode == "guided_confirmation"
        and report.get("mode_guidance") == "ask_user_for_confirmation"
        and bool(report.get("human_review_fields"))
    )
