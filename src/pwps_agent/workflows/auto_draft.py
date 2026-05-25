from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel

from pwps_agent.config import Settings
from pwps_agent.core.contracts import SearchResult, ToolResult
from pwps_agent.core.state import PWPSState, create_initial_state
from pwps_agent.knowledge.local_doc_provider import LocalDocumentProvider
from pwps_agent.knowledge.web_search_provider import build_web_search_provider
from pwps_agent.llm.langchain_client import LangChainStructuredClient
from pwps_agent.tools.field_reasoning import reason_fields_from_evidence
from pwps_agent.tools.knowledge_planning import plan_knowledge_queries
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


def run_graph_auto_draft(
    requirement: str,
    settings: Settings,
    dependencies: AutoDraftDependencies | None = None,
    run_id: str = "run_local",
) -> AutoDraftResult:
    return run_graph_draft(
        requirement,
        settings=settings,
        dependencies=dependencies,
        run_id=run_id,
        interaction_mode="auto_draft",
    )


def run_graph_guided_draft(
    requirement: str,
    settings: Settings,
    dependencies: AutoDraftDependencies | None = None,
    run_id: str = "run_local",
) -> AutoDraftResult:
    return run_graph_draft(
        requirement,
        settings=settings,
        dependencies=dependencies,
        run_id=run_id,
        interaction_mode="guided_confirmation",
    )


def run_graph_draft(
    requirement: str,
    settings: Settings,
    dependencies: AutoDraftDependencies | None = None,
    run_id: str = "run_local",
    interaction_mode: str = "auto_draft",
) -> AutoDraftResult:
    from pwps_agent.graph.builder import build_auto_draft_graph
    from pwps_agent.graph.state import GraphRuntimeContext
    from pwps_agent.graph.supervisor import LLMSupervisorPlanner

    deps = dependencies or _build_dependencies(settings)
    LOGGER.info(
        "Building graph draft run_id=%s mode=%s planner=llm output_dir=%s",
        run_id,
        interaction_mode,
        settings.paths.output_dir,
    )
    supervisor_planner = LLMSupervisorPlanner(client=deps.llm_client)
    state = create_initial_state(requirement, interaction_mode, run_id=run_id)
    graph = build_auto_draft_graph()
    result = graph.invoke(
        {
            "pwps_state": state,
            "context": GraphRuntimeContext(
                settings=settings,
                dependencies=deps,
                supervisor_planner=supervisor_planner,
                supervisor_planner_mode="llm",
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
