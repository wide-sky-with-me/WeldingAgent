from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from pwps_agent.graph.nodes import (
    ask_user_node,
    call_tool_node,
    compose_draft_node,
    finish_node,
    generate_report_node,
    update_state_node,
    use_domain_skill_node,
)
from pwps_agent.graph.router import route_action, route_after_tool
from pwps_agent.graph.state import GraphState
from pwps_agent.graph.supervisor import supervisor_node


def build_auto_draft_graph():
    graph = StateGraph(GraphState)
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("call_tool", call_tool_node)
    graph.add_node("use_domain_skill", use_domain_skill_node)
    graph.add_node("update_state", update_state_node)
    graph.add_node("ask_user", ask_user_node)
    graph.add_node("compose_draft", compose_draft_node)
    graph.add_node("generate_report", generate_report_node)
    graph.add_node("finish", finish_node)

    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges(
        "supervisor",
        route_action,
        {
            "use_domain_skill": "use_domain_skill",
            "update_state": "update_state",
            "call_tool": "call_tool",
            "ask_user": "ask_user",
            "compose_draft": "compose_draft",
            "generate_report": "generate_report",
            "finish": "finish",
        },
    )
    graph.add_conditional_edges(
        "call_tool",
        route_after_tool,
        {
            "call_tool": "call_tool",
            "supervisor": "supervisor",
            "finish": "finish",
        },
    )
    graph.add_edge("ask_user", END)
    graph.add_edge("use_domain_skill", "supervisor")
    graph.add_edge("update_state", "supervisor")
    graph.add_edge("generate_report", "supervisor")
    graph.add_edge("compose_draft", "supervisor")
    graph.add_edge("finish", END)
    return graph.compile()
