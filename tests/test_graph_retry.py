from pathlib import Path
import time

from pwps_agent.config import Settings
from pwps_agent.core.contracts import AgentAction, ToolResult
from pwps_agent.core.state import create_initial_state
from pwps_agent.graph.builder import build_auto_draft_graph
from pwps_agent.graph.state import GraphRuntimeContext
from pwps_agent.workflows.auto_draft import AutoDraftDependencies


class RequirementThenFinishPlanner:
    def plan_next_action(self, state):
        completed = {entry["node"] for entry in state.trace}
        if "requirement_understanding" not in completed:
            return AgentAction(
                action_type="CALL_TOOL",
                tool_name="requirement_understanding",
                rationale_summary="Extract requirement.",
                expected_state_change="Add core fields.",
            )
        return AgentAction(
            action_type="FINISH",
            rationale_summary="Stop after requirement extraction.",
            expected_state_change="Finish test graph.",
        )


class FlakyRequirementTool:
    def __init__(self):
        self.calls = 0

    def __call__(self, state, client):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("temporary model timeout")
        return ToolResult(
            tool_name="requirement_understanding",
            success=True,
            state_patch={
                "core_fields": {"base_material": "Q355B"},
                "fields": {"base_material": {"value": "Q355B", "status": "filled"}},
            },
            summary="requirement extracted",
        )


class AlwaysFailingRequirementTool:
    def __init__(self):
        self.calls = 0

    def __call__(self, state, client):
        self.calls += 1
        return ToolResult(
            tool_name="requirement_understanding",
            success=False,
            errors=["bad structured output"],
            summary="requirement failed",
        )


class NoopSearchProvider:
    def search(self, query: str, query_id: str):
        return []


class WebSearchThenFinishPlanner:
    def plan_next_action(self, state):
        completed = {entry["node"] for entry in state.trace}
        if "web_search" not in completed:
            return AgentAction(
                action_type="CALL_TOOL",
                tool_name="web_search",
                rationale_summary="Search planned evidence queries.",
                expected_state_change="Add search evidence.",
            )
        return AgentAction(
            action_type="FINISH",
            rationale_summary="Stop after web search.",
            expected_state_change="Finish test graph.",
        )


class SlowAndFastSearchProvider:
    def search(self, query: str, query_id: str):
        if query_id == "slow":
            time.sleep(0.05)
            return []
        from pwps_agent.core.contracts import SearchResult

        return [
            SearchResult(
                result_id="fast_result",
                query_id=query_id,
                provider="fake",
                snippet="fast evidence",
            )
        ]


def _context(tmp_path: Path, requirement_tool, max_tool_retries=1):
    settings = Settings()
    settings.paths.output_dir = tmp_path
    dependencies = AutoDraftDependencies(
        llm_client=object(),
        search_provider=NoopSearchProvider(),
        requirement_tool=requirement_tool,
    )
    return GraphRuntimeContext(
        settings=settings,
        dependencies=dependencies,
        supervisor_planner=RequirementThenFinishPlanner(),
        max_tool_retries=max_tool_retries,
    )


def _web_context(tmp_path: Path, search_provider):
    settings = Settings()
    settings.paths.output_dir = tmp_path
    dependencies = AutoDraftDependencies(
        llm_client=object(),
        search_provider=search_provider,
    )
    return GraphRuntimeContext(
        settings=settings,
        dependencies=dependencies,
        supervisor_planner=WebSearchThenFinishPlanner(),
        query_timeout_seconds=0.01,
        max_parallel_queries=2,
    )


def test_graph_retries_retryable_tool_error_and_continues(tmp_path: Path):
    tool = FlakyRequirementTool()
    state = create_initial_state("Q355B 12mm GMAW", "auto_draft", run_id="retry_ok")

    result = build_auto_draft_graph().invoke(
        {"pwps_state": state, "context": _context(tmp_path, tool, max_tool_retries=1)}
    )

    final_state = result["pwps_state"]
    assert tool.calls == 2
    assert final_state.status == "done"
    assert final_state.fields["base_material"].value == "Q355B"
    retry_events = [
        entry
        for entry in final_state.trace
        if entry["node"] == "requirement_understanding"
        and entry["event_type"] == "tool_error"
    ]
    assert retry_events[0]["payload"]["attempt"] == 1
    assert retry_events[0]["payload"]["retryable"] is True


def test_graph_marks_state_failed_after_retry_exhaustion(tmp_path: Path):
    tool = AlwaysFailingRequirementTool()
    state = create_initial_state("Q355B 12mm GMAW", "auto_draft", run_id="retry_fail")

    result = build_auto_draft_graph().invoke(
        {"pwps_state": state, "context": _context(tmp_path, tool, max_tool_retries=1)}
    )

    final_state = result["pwps_state"]
    assert tool.calls == 2
    assert final_state.status == "failed"
    failures = [
        entry
        for entry in final_state.trace
        if entry["node"] == "requirement_understanding"
        and entry["event_type"] == "tool_result"
        and entry["payload"]["success"] is False
    ]
    assert failures[-1]["payload"]["attempt"] == 2
    assert failures[-1]["payload"]["retryable"] is False


def test_web_search_records_per_query_timeout_and_partial_success(tmp_path: Path):
    state = create_initial_state("Q355B 12mm GMAW", "auto_draft", run_id="search_timeout")
    state.knowledge_queries = [
        {"query_id": "slow", "query_text": "slow query"},
        {"query_id": "fast", "query_text": "fast query"},
    ]

    result = build_auto_draft_graph().invoke(
        {
            "pwps_state": state,
            "context": _web_context(tmp_path, SlowAndFastSearchProvider()),
        }
    )

    final_state = result["pwps_state"]
    assert final_state.status == "done"
    assert [search_result["result_id"] for search_result in final_state.search_results] == [
        "fast_result"
    ]
    query_events = [
        entry
        for entry in final_state.trace
        if entry["node"] == "web_search_query"
    ]
    assert {entry["payload"]["query_id"] for entry in query_events} == {"slow", "fast"}
    assert any(entry["event_type"] == "tool_timeout" for entry in query_events)
