import json
from pathlib import Path

from pwps_agent.config import Settings
from pwps_agent.core.contracts import SearchResult, ToolResult
from pwps_agent.core.state import create_initial_state
from pwps_agent.graph.builder import build_auto_draft_graph
from pwps_agent.graph.state import GraphRuntimeContext
from pwps_agent.workflows.auto_draft import AutoDraftDependencies


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
