from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel

from pwps_agent.config import Settings
from pwps_agent.core.contracts import SearchResult, ToolResult
from pwps_agent.core.state_merge import merge_state_patch
from pwps_agent.core.state import PWPSState, create_initial_state
from pwps_agent.knowledge.local_doc_provider import LocalDocumentProvider
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
from pwps_agent.tools.local_doc_search import search_local_documents
from pwps_agent.tools.requirement_understanding import understand_requirement

LOGGER = logging.getLogger(__name__)


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
    local_doc_provider: SearchProvider | None = None
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

    if deps.local_doc_provider is not None:
        local_result = search_local_documents(state, deps.local_doc_provider)
        state = _merge_state_patch(state, local_result.state_patch)
        state.trace.append(
            {
                "step": len(state.trace) + 1,
                "node": "local_doc_search",
                "event_type": "tool_result",
                "summary": local_result.summary,
                "payload": {"success": local_result.success},
            }
        )

    search_results: list[SearchResult] = []
    for query in _web_queries(state.knowledge_queries):
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


def run_graph_auto_draft(
    requirement: str,
    settings: Settings,
    dependencies: AutoDraftDependencies | None = None,
    run_id: str = "run_local",
) -> AutoDraftResult:
    from pwps_agent.graph.builder import build_auto_draft_graph
    from pwps_agent.graph.state import GraphRuntimeContext
    from pwps_agent.graph.supervisor import LLMSupervisorPlanner

    deps = dependencies or _build_dependencies(settings)
    LOGGER.info(
        "Building graph auto-draft run_id=%s planner=%s output_dir=%s",
        run_id,
        settings.supervisor.planner,
        settings.paths.output_dir,
    )
    supervisor_planner = None
    if settings.supervisor.planner == "llm":
        supervisor_planner = LLMSupervisorPlanner(client=deps.llm_client)
    state = create_initial_state(requirement, "auto_draft", run_id=run_id)
    graph = build_auto_draft_graph()
    result = graph.invoke(
        {
            "pwps_state": state,
            "context": GraphRuntimeContext(
                settings=settings,
                dependencies=deps,
                supervisor_planner=supervisor_planner,
                supervisor_planner_mode=settings.supervisor.planner,
            ),
        }
    )
    final_state = result["pwps_state"]
    LOGGER.info(
        "Graph auto-draft finished run_id=%s status=%s steps=%s",
        final_state.run_id,
        final_state.status,
        final_state.step_count,
    )
    return AutoDraftResult(
        state=final_state,
        output_dir=str(settings.paths.output_dir / final_state.run_id),
    )


def _build_dependencies(settings: Settings) -> AutoDraftDependencies:
    return AutoDraftDependencies(
        llm_client=LangChainStructuredClient(settings.llm),
        search_provider=build_web_search_provider(settings.web_search),
        local_doc_provider=LocalDocumentProvider(
            settings.paths.local_docs_dir,
            max_results=settings.local_docs.max_results,
            snippet_chars=settings.local_docs.snippet_chars,
        ),
    )


def _merge_state_patch(state: PWPSState, patch: dict) -> PWPSState:
    return merge_state_patch(state, patch)


def _web_queries(knowledge_queries: list[dict]) -> list[dict]:
    return [
        query
        for query in knowledge_queries
        if "local_doc" not in (query.get("preferred_sources") or [])
    ]
