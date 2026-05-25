from __future__ import annotations

from dataclasses import dataclass

from pwps_agent.core.contracts import AgentAction
from pwps_agent.core.interaction import (
    missing_minimum_auto_draft_fields,
    should_interrupt_for_initial_info,
)
from pwps_agent.core.modes import GUIDED_CORE_CONFIRMATION_FIELDS
from pwps_agent.core.state import PWPSState


@dataclass(frozen=True)
class PolicyDecision:
    action: AgentAction
    overridden: bool = False
    reason_code: str | None = None
    summary: str | None = None


class GraphPolicy:
    def __init__(
        self,
        knowledge_sources: list[str] | None = None,
        planner_mode: str = "injected",
    ) -> None:
        self.knowledge_sources = knowledge_sources
        self.planner_mode = planner_mode

    def resolve(self, action: AgentAction, state: PWPSState) -> PolicyDecision:
        replacement = self._replacement(action, state)
        if replacement is None:
            return PolicyDecision(action=action)
        return PolicyDecision(
            action=replacement[0],
            overridden=True,
            reason_code=replacement[1],
            summary=replacement[2],
        )

    def _replacement(
        self,
        action: AgentAction,
        state: PWPSState,
    ) -> tuple[AgentAction, str, str] | None:
        last = _last_node_indexes(state)
        if (
            should_interrupt_for_initial_info(state)
            and (self.planner_mode == "llm" or action.action_type == "ASK_USER")
            and not (
                action.action_type == "CALL_TOOL"
                and action.tool_name == "requirement_understanding"
            )
        ):
            missing = missing_minimum_auto_draft_fields(state)
            return (
                AgentAction(
                    action_type="ASK_USER",
                    rationale_summary=(
                        "Auto-draft requires minimum core information before retrieval starts: "
                        + ", ".join(missing)
                    ),
                    expected_state_change="Pause once for initial missing core information.",
                ),
                "auto_draft_initial_gate",
                "Auto-draft initial information gate requires user input before workflow start.",
            )
        if (
            _node_completed(state, "compose_draft")
            and state.interaction_mode == "guided_confirmation"
            and _has_pending_confirmation_fields(state)
        ):
            if action.action_type != "ASK_USER":
                return (
                    AgentAction(
                        action_type="ASK_USER",
                        rationale_summary="Draft artifacts are composed and fields still need guided confirmation.",
                        expected_state_change="Pause with grouped confirmation view.",
                    ),
                    "guided_confirmation_required",
                    "Guided confirmation still has fields requiring human review.",
                )
            return None
        if _node_completed(state, "compose_draft") and action.action_type != "FINISH":
            return (
                AgentAction(
                    action_type="FINISH",
                    rationale_summary="Draft artifacts are already composed; finish auto-draft run.",
                    expected_state_change="Mark graph run as done.",
                    stop_reason="auto_draft_complete",
                ),
                "completed_action",
                "Draft composition is already complete.",
            )
        if (
            _node_completed(state, "field_reasoning")
            and not _node_completed(state, "draft_verifier")
            and action.action_type in {"COMPOSE_DRAFT", "FINISH"}
        ):
            return (
                AgentAction(
                    action_type="VERIFY_DRAFT",
                    rationale_summary="Verify draft quality before synthesis.",
                    expected_state_change="Attach deterministic quality report to state.",
                ),
                "premature_finish",
                "Planner tried to synthesize before draft verification.",
            )
        if (
            self.planner_mode == "llm"
            and _workflow_started(state)
            and not _node_completed(state, "compose_draft")
            and action.action_type in {"COMPOSE_DRAFT", "FINISH"}
        ):
            safe_next = plan_next_auto_draft_action(state, self.knowledge_sources)
            if action.action_type == "FINISH" or safe_next.action_type != "COMPOSE_DRAFT":
                return (
                    safe_next,
                    "premature_finish",
                    "Planner tried to close before required graph steps completed.",
                )
        if (
            _needs_refinement_planning(state, last)
            and action.action_type in {"COMPOSE_DRAFT", "FINISH"}
        ):
            return (
                plan_next_auto_draft_action(state, self.knowledge_sources),
                "premature_finish",
                "Verifier requested refinement before synthesis.",
            )
        if (
            _needs_guided_confirmation_pause(state)
            and action.action_type in {"COMPOSE_DRAFT", "FINISH"}
        ):
            return (
                AgentAction(
                    action_type="ASK_USER",
                    rationale_summary="Verifier found fields that need guided human review.",
                    expected_state_change="Pause with grouped confirmation view.",
                ),
                "guided_confirmation_required",
                "Verifier found fields requiring human review.",
            )
        if (
            _needs_guided_options(state)
            and action.action_type == "ASK_USER"
            and not _node_completed(state, "guided_options")
        ):
            return (
                _tool_action(
                    "guided_options",
                    "Prepare recommended guided options before asking for confirmation.",
                ),
                "guided_confirmation_required",
                "Guided confirmation needs option recommendations before pausing.",
            )
        if (
            _node_completed(state, "draft_verifier")
            and not _node_completed(state, "compose_draft")
            and action.action_type == "FINISH"
        ):
            return (
                AgentAction(
                    action_type="COMPOSE_DRAFT",
                    rationale_summary="Quality verification is complete; compose draft artifacts.",
                    expected_state_change="Persist draft/report artifacts and attach them to state.",
                ),
                "premature_finish",
                "Planner tried to finish before composing draft artifacts.",
            )
        if state.interaction_mode == "auto_draft" and action.action_type == "ASK_USER":
            return (
                plan_next_auto_draft_action(state, self.knowledge_sources),
                "auto_draft_invalid_interrupt",
                "Auto-draft can only ask at the initial information gate.",
            )
        if action.action_type == "CALL_TOOL" and action.tool_name:
            if _node_completed(state, action.tool_name):
                return (
                    plan_next_auto_draft_action(state, self.knowledge_sources),
                    "completed_action",
                    "Planner requested an already completed tool.",
                )
        if action.action_type == "USE_DOMAIN_SKILL" and action.domain_skill_name:
            if action.domain_skill_name in state.active_domain_skills:
                return (
                    plan_next_auto_draft_action(state, self.knowledge_sources),
                    "completed_action",
                    "Planner requested an already active domain skill.",
                )
        if action.action_type == "UPDATE_STATE":
            if action.tool_args.get("operation") == "supplement_update" and _node_completed(
                state,
                "supplement_update",
            ):
                return (
                    plan_next_auto_draft_action(state, self.knowledge_sources),
                    "completed_action",
                    "Planner requested an already completed supplement update.",
                )
        if action.action_type == "COMPOSE_DRAFT" and _node_completed(state, "compose_draft"):
            return (
                plan_next_auto_draft_action(state, self.knowledge_sources),
                "completed_action",
                "Planner requested an already completed draft composition.",
            )
        if action.action_type == "GENERATE_REPORT" and _node_completed(state, "risk_report"):
            return (
                plan_next_auto_draft_action(state, self.knowledge_sources),
                "completed_action",
                "Planner requested an already completed risk report.",
            )
        if action.action_type == "VERIFY_DRAFT" and _draft_verifier_current(state):
            return (
                plan_next_auto_draft_action(state, self.knowledge_sources),
                "completed_action",
                "Planner requested an already completed draft verification.",
            )
        return None


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
    if _needs_guided_options(state) and not _node_completed(state, "guided_options"):
        return _tool_action(
            "guided_options",
            "Prepare recommended guided options before asking for confirmation.",
        )
    if _needs_guided_confirmation_pause(state) or (
        state.interaction_mode == "guided_confirmation"
        and _has_pending_confirmation_fields(state)
        and _node_completed(state, "guided_options")
    ):
        return AgentAction(
            action_type="ASK_USER",
            rationale_summary="Fields need guided human review.",
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


def is_refinement_planning_action(action: AgentAction) -> bool:
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


def _node_completed(state: PWPSState, node: str) -> bool:
    return any(entry.get("node") == node for entry in state.trace)


def _draft_verifier_current(state: PWPSState) -> bool:
    if not state.quality_report:
        return False
    last = _last_node_indexes(state)
    return last.get("draft_verifier", -1) > last.get("guided_confirmation_resume", -1)


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


def _needs_guided_options(state: PWPSState) -> bool:
    return (
        state.interaction_mode == "guided_confirmation"
        and _has_pending_confirmation_fields(state)
        and not state.confirmations
        and not _node_completed(state, "ask_user")
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
        and _has_pending_confirmation_fields(state)
    )
