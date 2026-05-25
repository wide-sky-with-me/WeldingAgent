from __future__ import annotations

from pwps_agent.graph.state import GraphState


def route_action(graph_state: GraphState) -> str:
    if graph_state["pwps_state"].status == "interrupted":
        return "finish"
    action = graph_state["pwps_state"].pending_action
    if action is None:
        return "finish"
    if action.action_type == "USE_DOMAIN_SKILL":
        return "use_domain_skill"
    if action.action_type == "UPDATE_STATE":
        return "update_state"
    if action.action_type == "CALL_TOOL":
        return "call_tool"
    if action.action_type == "ASK_USER":
        return "ask_user"
    if action.action_type == "GENERATE_REPORT":
        return "generate_report"
    if action.action_type == "COMPOSE_DRAFT":
        return "compose_draft"
    if action.action_type == "FINISH":
        return "finish"
    return "finish"


def route_after_tool(graph_state: GraphState) -> str:
    state = graph_state["pwps_state"]
    if state.status == "interrupted":
        return "finish"
    if state.status == "failed":
        last_event = _last_tool_event(state.trace)
        if last_event and last_event.get("payload", {}).get("retryable") is True:
            return "call_tool"
        return "finish"
    return "supervisor"


def _last_tool_event(trace: list[dict]) -> dict | None:
    for entry in reversed(trace):
        if entry.get("event_type") in {"tool_result", "tool_error"}:
            return entry
    return None
