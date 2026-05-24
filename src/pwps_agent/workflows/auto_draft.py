from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel

from pwps_agent.config import Settings
from pwps_agent.core.contracts import SearchResult, ToolResult
from pwps_agent.core.state_merge import merge_state_patch
from pwps_agent.core.state import PWPSState, create_initial_state
from pwps_agent.knowledge.web_search_provider import WebSearchProvider, build_web_search_provider
from pwps_agent.llm.langchain_client import LangChainStructuredClient
from pwps_agent.render.markdown import render_field_report, render_pwps_draft
from pwps_agent.storage.persist import persist_run_artifacts
from pwps_agent.tools.evidence import search_results_to_evidence
from pwps_agent.tools.field_reasoning import (
    apply_field_candidates,
    infer_candidates_from_evidence,
    reason_fields_from_evidence,
)
from pwps_agent.tools.knowledge_planning import plan_knowledge_queries
from pwps_agent.tools.requirement_understanding import understand_requirement


class RequirementTool(Protocol):
    def __call__(self, state: PWPSState, client: object) -> ToolResult:
        ...


class SearchProvider(Protocol):
    def search(self, query: str, query_id: str) -> list[SearchResult]:
        ...


class KnowledgePlanningTool(Protocol):
    def __call__(self, state: PWPSState, client: object) -> ToolResult:
        ...


class FieldReasoningTool(Protocol):
    def __call__(self, state: PWPSState, evidence: list, client: object) -> ToolResult:
        ...


@dataclass
class AutoDraftDependencies:
    llm_client: object
    search_provider: SearchProvider
    requirement_tool: RequirementTool = understand_requirement
    knowledge_planning_tool: KnowledgePlanningTool = plan_knowledge_queries
    field_reasoning_tool: FieldReasoningTool = reason_fields_from_evidence


class AutoDraftResult(BaseModel):
    state: PWPSState
    output_dir: str


def run_auto_draft(
    requirement: str,
    settings: Settings,
    dependencies: AutoDraftDependencies | None = None,
    run_id: str = "run_local",
) -> AutoDraftResult:
    deps = dependencies or _build_dependencies(settings)
    state = create_initial_state(requirement, "auto_draft", run_id=run_id)

    requirement_result = deps.requirement_tool(state, deps.llm_client)
    state = _merge_state_patch(state, requirement_result.state_patch)
    state.trace.append(
        {
            "step": len(state.trace) + 1,
            "node": "requirement_understanding",
            "event_type": "tool_result",
            "summary": requirement_result.summary,
            "payload": {"success": requirement_result.success},
        }
    )

    planning_result = deps.knowledge_planning_tool(state, deps.llm_client)
    state = _merge_state_patch(state, planning_result.state_patch)
    state.trace.append(
        {
            "step": len(state.trace) + 1,
            "node": "knowledge_planning",
            "event_type": "tool_result",
            "summary": planning_result.summary,
            "payload": {"success": planning_result.success},
        }
    )

    search_results: list[SearchResult] = []
    for query in state.knowledge_queries:
        query_text = str(query["query_text"])
        query_id = str(query["query_id"])
        search_results.extend(deps.search_provider.search(query_text, query_id))
    state.search_results = [result.model_dump() for result in search_results]
    evidence = search_results_to_evidence(search_results)
    state.evidence.extend(evidence)
    state.trace.append(
        {
            "step": len(state.trace) + 1,
            "node": "web_search",
            "event_type": "tool_result",
            "summary": f"Retrieved {len(search_results)} web results.",
            "payload": {"queries": state.knowledge_queries},
        }
    )

    reasoning_result = deps.field_reasoning_tool(state, evidence, deps.llm_client)
    if reasoning_result.success and reasoning_result.state_patch.get("fields"):
        state = _merge_state_patch(state, reasoning_result.state_patch)
        state.trace.append(
            {
                "step": len(state.trace) + 1,
                "node": "field_reasoning",
                "event_type": "tool_result",
                "summary": reasoning_result.summary,
                "payload": {"success": True},
            }
        )
    else:
        candidates = infer_candidates_from_evidence(evidence)
        state = apply_field_candidates(state, candidates)
        state.trace.append(
            {
                "step": len(state.trace) + 1,
                "node": "field_reasoning",
                "event_type": "tool_result",
                "summary": "Used deterministic evidence fallback.",
                "payload": {"success": True},
            }
        )

    draft = render_pwps_draft(state)
    report = render_field_report(state)
    state.draft_markdown = draft
    state.field_report = report
    output_dir = persist_run_artifacts(state, draft, report, settings.paths.output_dir)
    return AutoDraftResult(state=state, output_dir=str(output_dir))


def _build_dependencies(settings: Settings) -> AutoDraftDependencies:
    return AutoDraftDependencies(
        llm_client=LangChainStructuredClient(settings.llm),
        search_provider=build_web_search_provider(settings.web_search),
    )


def _merge_state_patch(state: PWPSState, patch: dict) -> PWPSState:
    return merge_state_patch(state, patch)
