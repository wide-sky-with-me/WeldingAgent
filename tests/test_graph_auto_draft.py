import json
from pathlib import Path

from pwps_agent.config import Settings
from pwps_agent.core.contracts import AgentAction, SearchResult, ToolResult
from pwps_agent.core.state import create_initial_state
from pwps_agent.graph.builder import build_auto_draft_graph
from pwps_agent.graph.state import GraphRuntimeContext
from pwps_agent.knowledge.local_doc_provider import LocalDocumentProvider
from pwps_agent.workflows.auto_draft import AutoDraftDependencies, run_graph_auto_draft


class StaticRequirementTool:
    def __call__(self, state, client):
        return ToolResult(
            tool_name="requirement_understanding",
            success=True,
            state_patch={
                "core_fields": {
                    "base_material": "Q355B",
                    "thickness": "12mm",
                    "welding_process": "GMAW",
                },
                "fields": {
                    "base_material": {"value": "Q355B", "status": "filled"},
                    "thickness": {"value": "12mm", "status": "filled"},
                    "welding_process": {"value": "GMAW", "status": "filled"},
                },
            },
            summary="understood requirement",
        )


class StaticPlanningTool:
    def __call__(self, state, client):
        return ToolResult(
            tool_name="knowledge_planning",
            success=True,
            state_patch={
                "knowledge_queries": [
                    {
                        "query_id": "kq_001",
                        "purpose": "similar_case",
                        "query_text": "Q355B 12mm GMAW WPS shielding gas",
                        "target_fields": ["shielding_gas"],
                        "rationale": "Find similar gas references.",
                        "preferred_sources": ["web"],
                    }
                ]
            },
            summary="planned query",
        )


class StaticSearchProvider:
    def search(self, query: str, query_id: str):
        return [
            SearchResult(
                result_id="r1",
                query_id=query_id,
                provider="tavily",
                title="WPS example",
                url="https://example.test/wps",
                snippet="Ar+CO2 shielding gas appears in a comparable GMAW WPS.",
            )
        ]


class StaticReasoningTool:
    def __call__(self, state, evidence, client):
        return ToolResult(
            tool_name="field_reasoning",
            success=True,
            state_patch={
                "fields": {
                    "shielding_gas": {
                        "value": "Ar+CO2",
                        "status": "candidate",
                        "confidence": "medium",
                        "evidence_ids": ["ev_r1"],
                        "source": {"type": "web", "evidence_ids": ["ev_r1"]},
                        "confirmation": {"required": True, "confirmed": False},
                    }
                }
            },
            summary="reasoned field",
        )


class PlanningClient:
    def __init__(self):
        self.calls = []
        self.actions = [
            AgentAction(
                action_type="CALL_TOOL",
                tool_name="requirement_understanding",
                rationale_summary="LLM selected requirement extraction.",
                expected_state_change="Extract core fields.",
            ),
            AgentAction(
                action_type="CALL_TOOL",
                tool_name="knowledge_planning",
                rationale_summary="LLM selected knowledge planning.",
                expected_state_change="Plan evidence queries.",
            ),
            AgentAction(
                action_type="CALL_TOOL",
                tool_name="web_search",
                rationale_summary="LLM selected web search.",
                expected_state_change="Retrieve evidence.",
            ),
            AgentAction(
                action_type="CALL_TOOL",
                tool_name="field_reasoning",
                rationale_summary="LLM selected field reasoning.",
                expected_state_change="Create field candidates.",
            ),
            AgentAction(
                action_type="COMPOSE_DRAFT",
                rationale_summary="LLM selected draft composition.",
                expected_state_change="Persist draft artifacts.",
            ),
            AgentAction(
                action_type="FINISH",
                rationale_summary="LLM selected finish.",
                expected_state_change="Mark run done.",
                stop_reason="llm_planner_test_complete",
            ),
        ]

    def complete_structured(self, system_prompt, user_prompt, schema):
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "schema": schema,
            }
        )
        return self.actions.pop(0)


def test_auto_draft_graph_executes_tool_sequence_and_persists_artifacts(tmp_path: Path):
    settings = Settings()
    settings.paths.output_dir = tmp_path
    dependencies = AutoDraftDependencies(
        llm_client=object(),
        search_provider=StaticSearchProvider(),
        requirement_tool=StaticRequirementTool(),
        knowledge_planning_tool=StaticPlanningTool(),
        field_reasoning_tool=StaticReasoningTool(),
    )
    context = GraphRuntimeContext(settings=settings, dependencies=dependencies)
    state = create_initial_state(
        "Q355B 12mm plate GMAW butt joint flat AWS D1.1 pWPS draft",
        "auto_draft",
        run_id="graph_test",
    )

    graph = build_auto_draft_graph()
    result = graph.invoke({"pwps_state": state, "context": context})

    final_state = result["pwps_state"]
    run_dir = tmp_path / "graph_test"
    assert final_state.status == "done"
    assert final_state.fields["base_material"].value == "Q355B"
    assert final_state.fields["shielding_gas"].value == "Ar+CO2"
    assert (run_dir / "pwps.json").exists()
    assert (run_dir / "pwps_draft.md").exists()
    assert (run_dir / "field_report.json").exists()
    assert (run_dir / "trace.json").exists()
    assert [
        entry["node"]
        for entry in final_state.trace
        if entry["node"] != "web_search_query"
    ] == [
        "supervisor",
        "requirement_understanding",
        "supervisor",
        "knowledge_planning",
        "supervisor",
        "web_search",
        "supervisor",
        "field_reasoning",
        "supervisor",
        "compose_draft",
        "supervisor",
        "finish",
    ]
    assert any(entry["node"] == "web_search_query" for entry in final_state.trace)
    assert json.loads((run_dir / "field_report.json").read_text(encoding="utf-8"))[
        "candidate_fields"
    ] == ["shielding_gas"]


def test_run_graph_auto_draft_service_invokes_graph_and_persists_artifacts(tmp_path: Path):
    settings = Settings()
    settings.paths.output_dir = tmp_path
    dependencies = AutoDraftDependencies(
        llm_client=object(),
        search_provider=StaticSearchProvider(),
        requirement_tool=StaticRequirementTool(),
        knowledge_planning_tool=StaticPlanningTool(),
        field_reasoning_tool=StaticReasoningTool(),
    )

    result = run_graph_auto_draft(
        "Q355B 12mm plate GMAW butt joint flat AWS D1.1 pWPS draft",
        settings=settings,
        dependencies=dependencies,
        run_id="graph_service_test",
    )

    run_dir = tmp_path / "graph_service_test"
    assert result.state.status == "done"
    assert result.output_dir == str(run_dir)
    assert (run_dir / "pwps.json").exists()
    assert (run_dir / "pwps_draft.md").exists()
    assert (run_dir / "field_report.json").exists()
    assert (run_dir / "trace.json").exists()
    assert (run_dir / "evidence_index.json").exists()
    assert any(
        entry["node"] == "supervisor" and entry["event_type"] == "agent_action"
        for entry in result.state.trace
    )


def test_run_graph_auto_draft_can_use_llm_supervisor_planner_from_settings(tmp_path: Path):
    settings = Settings()
    settings.paths.output_dir = tmp_path
    settings.supervisor.planner = "llm"
    planning_client = PlanningClient()
    dependencies = AutoDraftDependencies(
        llm_client=planning_client,
        search_provider=StaticSearchProvider(),
        requirement_tool=StaticRequirementTool(),
        knowledge_planning_tool=StaticPlanningTool(),
        field_reasoning_tool=StaticReasoningTool(),
    )

    result = run_graph_auto_draft(
        "Q355B 12mm plate GMAW butt joint flat AWS D1.1 pWPS draft",
        settings=settings,
        dependencies=dependencies,
        run_id="llm_graph_service_test",
    )

    assert result.state.status == "done"
    assert len(planning_client.calls) == 6
    assert all(call["schema"] is AgentAction for call in planning_client.calls)
    supervisor_events = [
        entry for entry in result.state.trace if entry["node"] == "supervisor"
    ]
    assert supervisor_events[0]["payload"]["planner"] == "llm"
    assert supervisor_events[0]["payload"]["tool_name"] == "requirement_understanding"


class LocalDocPlanningTool:
    def __call__(self, state, client):
        return ToolResult(
            tool_name="knowledge_planning",
            success=True,
            state_patch={
                "knowledge_queries": [
                    {
                        "query_id": "kq_local_001",
                        "purpose": "similar_case",
                        "query_text": "Q355B GMAW ER50-6 shielding gas",
                        "target_fields": ["filler_material", "shielding_gas"],
                        "rationale": "Find local reference snippets.",
                        "preferred_sources": ["local_doc"],
                    }
                ]
            },
            summary="planned local query",
        )


def test_graph_auto_draft_collects_local_doc_evidence_and_persists_index(tmp_path: Path):
    settings = Settings()
    settings.paths.output_dir = tmp_path
    settings.paths.local_docs_dir = Path("tests/fixtures/local_docs")
    dependencies = AutoDraftDependencies(
        llm_client=object(),
        search_provider=StaticSearchProvider(),
        local_doc_provider=LocalDocumentProvider(settings.paths.local_docs_dir),
        requirement_tool=StaticRequirementTool(),
        knowledge_planning_tool=LocalDocPlanningTool(),
        field_reasoning_tool=StaticReasoningTool(),
    )
    context = GraphRuntimeContext(settings=settings, dependencies=dependencies)
    state = create_initial_state(
        "Q355B 12mm plate GMAW butt joint flat AWS D1.1 pWPS draft",
        "auto_draft",
        run_id="graph_local_doc_test",
    )

    result = build_auto_draft_graph().invoke({"pwps_state": state, "context": context})

    final_state = result["pwps_state"]
    run_dir = tmp_path / "graph_local_doc_test"
    assert any(item.source_type == "local_doc" for item in final_state.evidence)
    assert any(entry["node"] == "local_doc_search" for entry in final_state.trace)
    evidence_index = json.loads((run_dir / "evidence_index.json").read_text(encoding="utf-8"))
    assert any(item["source_type"] == "local_doc" for item in evidence_index["evidence"])
