import json
from pathlib import Path

from pwps_agent.config import Settings
from pwps_agent.core.contracts import AgentAction, SearchResult, ToolResult
from pwps_agent.core.state import PWPSState, create_initial_state
from pwps_agent.graph.builder import build_auto_draft_graph
from pwps_agent.graph.nodes import _mark_model_fallback_fields
from pwps_agent.graph.state import GraphRuntimeContext
from pwps_agent.graph.supervisor import plan_next_auto_draft_action
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


class MixedSourcePlanningTool:
    def __call__(self, state, client):
        return ToolResult(
            tool_name="knowledge_planning",
            success=True,
            state_patch={
                "knowledge_queries": [
                    {
                        "query_id": "kq_mixed_001",
                        "purpose": "similar_case",
                        "query_text": "Q355B 12mm GMAW WPS shielding gas",
                        "target_fields": ["shielding_gas"],
                        "rationale": "Find local first, then web.",
                        "preferred_sources": ["local_doc", "web"],
                    }
                ]
            },
            summary="planned mixed query",
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


class EmptySearchProvider:
    def search(self, query: str, query_id: str):
        return []


class FillerSearchProvider:
    def search(self, query: str, query_id: str):
        return [
            SearchResult(
                result_id="filler",
                query_id=query_id,
                provider="tavily",
                title="WPS example",
                url="https://example.test/filler",
                snippet="ER50-6 is a candidate filler material for a comparable GMAW WPS.",
            )
        ]


class StaticModelFallbackReasoningTool:
    def __call__(self, state, evidence, client):
        return ToolResult(
            tool_name="field_reasoning",
            success=True,
            state_patch={
                "fields": {
                    "shielding_gas": {
                        "value": "80% Ar / 20% CO2",
                        "status": "candidate",
                        "confidence": "low",
                        "evidence_ids": [],
                        "source": {"type": "web", "evidence_ids": []},
                    }
                }
            },
            summary="reasoned model fallback field",
        )


class StatusWordReasoningTool:
    def __call__(self, state, evidence, client):
        return ToolResult(
            tool_name="field_reasoning",
            success=True,
            state_patch={
                "fields": {
                    "shielding_gas": {
                        "value": "need_confirmation",
                        "status": "need_confirmation",
                        "confidence": "low",
                        "evidence_ids": ["ev_r1"],
                    }
                }
            },
            summary="reasoned placeholder status word",
        )


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


def test_model_fallback_marks_fields_as_suggested_low_confidence() -> None:
    fields = {
        "polarity": {
            "value": "DCEP",
            "status": "candidate",
            "confidence": "medium",
            "evidence_ids": [],
        }
    }

    marked = _mark_model_fallback_fields(fields)

    assert marked["polarity"]["status"] == "suggested"
    assert marked["polarity"]["confidence"] == "low"
    assert marked["polarity"]["source"]["type"] == "model_fallback"
    assert marked["polarity"]["confirmation"]["required"] is True


def test_model_fallback_drops_blocked_metadata_fields() -> None:
    fields = {
        "project_name": {"value": "Bridge Project", "status": "candidate"},
        "polarity": {"value": "DCEP", "status": "candidate"},
    }

    marked = _mark_model_fallback_fields(fields)

    assert "project_name" not in marked
    assert "polarity" in marked


class EmptyReasoningTool:
    def __call__(self, state, evidence, client):
        return ToolResult(
            tool_name="field_reasoning",
            success=True,
            state_patch={"fields": {}},
            summary="reasoned no fields",
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
                rationale_summary="LLM selected premature finish.",
                expected_state_change="Mark run done.",
                stop_reason="llm_planner_test_complete",
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
        if not self.actions:
            return AgentAction(
                action_type="FINISH",
                rationale_summary="LLM selected finish after planned actions.",
                expected_state_change="Mark run done.",
                stop_reason="llm_planner_test_complete",
            )
        return self.actions.pop(0)


class ProgressPlanner:
    def __init__(self, settings: Settings):
        self.settings = settings

    def plan_next_action(self, state):
        return plan_next_auto_draft_action(state, self.settings.knowledge.sources)


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
    context = GraphRuntimeContext(
        settings=settings,
        dependencies=dependencies,
        supervisor_planner=ProgressPlanner(settings),
    )
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
    assert (run_dir / "quality_report.json").exists()
    assert (run_dir / "trace.json").exists()
    persisted_state = PWPSState.model_validate_json(
        (run_dir / "pwps.json").read_text(encoding="utf-8")
    )
    assert persisted_state.status == "done"
    nodes = [
        entry["node"]
        for entry in final_state.trace
        if entry["node"] != "web_search_query"
    ]
    assert nodes.index("draft_verifier") < nodes.index("compose_draft")
    assert nodes[-2:] == ["supervisor", "finish"]
    assert {"requirement_understanding", "knowledge_planning", "web_search", "field_reasoning"}.issubset(nodes)
    assert any(entry["node"] == "web_search_query" for entry in final_state.trace)
    assert json.loads((run_dir / "field_report.json").read_text(encoding="utf-8"))[
        "candidate_fields"
    ] == ["shielding_gas"]


def test_graph_runs_verifier_before_composing_draft(tmp_path: Path):
    settings = Settings()
    settings.paths.output_dir = tmp_path
    dependencies = AutoDraftDependencies(
        llm_client=object(),
        search_provider=StaticSearchProvider(),
        requirement_tool=StaticRequirementTool(),
        knowledge_planning_tool=StaticPlanningTool(),
        field_reasoning_tool=EmptyReasoningTool(),
    )
    context = GraphRuntimeContext(
        settings=settings,
        dependencies=dependencies,
        supervisor_planner=ProgressPlanner(settings),
    )
    state = create_initial_state(
        "Q355B 12mm plate GMAW butt joint flat position AWS D1.1 pWPS draft",
        "auto_draft",
        run_id="verify_before_compose",
    )

    result = build_auto_draft_graph().invoke({"pwps_state": state, "context": context})

    final_state = result["pwps_state"]
    nodes = [entry["node"] for entry in final_state.trace]
    assert "draft_verifier" in nodes
    assert nodes.index("draft_verifier") < nodes.index("compose_draft")
    assert final_state.quality_report is not None
    assert final_state.quality_report["recommended_action"] in {
        "refine_search",
        "synthesize_with_limitations",
    }


def test_graph_does_not_create_hardcoded_candidates_when_reasoning_returns_empty(
    tmp_path: Path,
):
    settings = Settings()
    settings.paths.output_dir = tmp_path
    dependencies = AutoDraftDependencies(
        llm_client=object(),
        search_provider=FillerSearchProvider(),
        requirement_tool=StaticRequirementTool(),
        knowledge_planning_tool=StaticPlanningTool(),
        field_reasoning_tool=EmptyReasoningTool(),
    )
    context = GraphRuntimeContext(
        settings=settings,
        dependencies=dependencies,
        supervisor_planner=ProgressPlanner(settings),
    )
    state = create_initial_state(
        "Q355B 12mm plate GMAW butt joint flat position AWS D1.1 pWPS draft",
        "auto_draft",
        run_id="no_hardcoded_candidate",
    )

    result = build_auto_draft_graph().invoke({"pwps_state": state, "context": context})

    final_state = result["pwps_state"]
    field = final_state.fields["filler_material"]
    assert final_state.status == "done"
    assert field.value is None
    assert field.status == "missing"
    assert any(
        entry["node"] == "field_reasoning"
        and entry["summary"] == "Field reasoning returned no field candidates."
        for entry in final_state.trace
    )


def test_graph_refines_when_verifier_finds_critical_missing_fields(tmp_path: Path):
    settings = Settings()
    settings.paths.output_dir = tmp_path
    dependencies = AutoDraftDependencies(
        llm_client=object(),
        search_provider=StaticSearchProvider(),
        requirement_tool=StaticRequirementTool(),
        knowledge_planning_tool=StaticPlanningTool(),
        field_reasoning_tool=EmptyReasoningTool(),
    )
    context = GraphRuntimeContext(
        settings=settings,
        dependencies=dependencies,
        supervisor_planner=ProgressPlanner(settings),
    )
    state = create_initial_state(
        "Q355B 12mm plate GMAW butt joint flat position AWS D1.1 pWPS draft",
        "auto_draft",
        run_id="refine_once",
    )
    state.max_refinement_attempts = 1

    result = build_auto_draft_graph().invoke({"pwps_state": state, "context": context})

    final_state = result["pwps_state"]
    assert final_state.refinement_attempts == 1
    assert final_state.quality_report["recommended_action"] == "synthesize_with_limitations"
    assert final_state.status == "done"
    assert [entry["node"] for entry in final_state.trace].count("knowledge_planning") == 2
    assert any(
        entry["node"] == "supervisor"
        and entry["event_type"] == "agent_action"
        and "refinement" in (entry.get("summary") or "").lower()
        for entry in final_state.trace
    )


def test_run_graph_auto_draft_service_invokes_graph_and_persists_artifacts(tmp_path: Path):
    settings = Settings()
    settings.paths.output_dir = tmp_path
    dependencies = AutoDraftDependencies(
        llm_client=PlanningClient(),
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
    assert (run_dir / "quality_report.json").exists()
    assert (run_dir / "trace.json").exists()
    assert (run_dir / "evidence_index.json").exists()
    assert any(
        entry["node"] == "supervisor" and entry["event_type"] == "agent_action"
        for entry in result.state.trace
    )
    assert any(entry["node"] == "section_generation" for entry in result.state.trace)
    assert any(entry["node"] == "risk_report" for entry in result.state.trace)
    assert result.state.sections
    assert result.state.field_report["summary"]["risk_count"] >= 0


def test_run_graph_auto_draft_can_use_llm_supervisor_planner_from_settings(tmp_path: Path):
    settings = Settings()
    settings.paths.output_dir = tmp_path
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
    assert len(planning_client.calls) >= 7
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
    context = GraphRuntimeContext(
        settings=settings,
        dependencies=dependencies,
        supervisor_planner=ProgressPlanner(settings),
    )
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


def test_graph_runs_web_for_mixed_source_queries(tmp_path: Path):
    settings = Settings()
    settings.paths.output_dir = tmp_path
    dependencies = AutoDraftDependencies(
        llm_client=object(),
        search_provider=StaticSearchProvider(),
        local_doc_provider=LocalDocumentProvider(Path("tests/fixtures/local_docs")),
        requirement_tool=StaticRequirementTool(),
        knowledge_planning_tool=MixedSourcePlanningTool(),
        field_reasoning_tool=StaticReasoningTool(),
    )
    context = GraphRuntimeContext(
        settings=settings,
        dependencies=dependencies,
        supervisor_planner=ProgressPlanner(settings),
    )
    state = create_initial_state(
        "Q355B 12mm plate GMAW butt joint flat AWS D1.1 pWPS draft",
        "auto_draft",
        run_id="graph_mixed_source_test",
    )

    result = build_auto_draft_graph().invoke({"pwps_state": state, "context": context})

    final_state = result["pwps_state"]
    assert final_state.status == "done"
    assert any(entry["node"] == "local_doc_search" for entry in final_state.trace)
    assert any(entry["node"] == "web_search" for entry in final_state.trace)
    assert any(item.source_type == "web" for item in final_state.evidence)


def test_graph_skips_local_doc_when_knowledge_sources_disable_it(tmp_path: Path):
    settings = Settings()
    settings.paths.output_dir = tmp_path
    settings.knowledge.sources = ["web", "model"]
    dependencies = AutoDraftDependencies(
        llm_client=object(),
        search_provider=StaticSearchProvider(),
        requirement_tool=StaticRequirementTool(),
        knowledge_planning_tool=MixedSourcePlanningTool(),
        field_reasoning_tool=StaticReasoningTool(),
    )
    context = GraphRuntimeContext(
        settings=settings,
        dependencies=dependencies,
        supervisor_planner=ProgressPlanner(settings),
    )
    state = create_initial_state(
        "Q355B 12mm plate GMAW butt joint flat AWS D1.1 pWPS draft",
        "auto_draft",
        run_id="graph_web_only_test",
    )

    result = build_auto_draft_graph().invoke({"pwps_state": state, "context": context})

    final_state = result["pwps_state"]
    assert final_state.status == "done"
    assert not any(entry["node"] == "local_doc_search" for entry in final_state.trace)
    assert any(entry["node"] == "web_search" for entry in final_state.trace)


def test_graph_marks_model_fallback_fields_as_suggested_without_external_evidence(
    tmp_path: Path,
):
    settings = Settings()
    settings.paths.output_dir = tmp_path
    settings.knowledge.sources = ["web", "model"]
    dependencies = AutoDraftDependencies(
        llm_client=object(),
        search_provider=EmptySearchProvider(),
        requirement_tool=StaticRequirementTool(),
        knowledge_planning_tool=StaticPlanningTool(),
        field_reasoning_tool=StaticModelFallbackReasoningTool(),
    )
    context = GraphRuntimeContext(
        settings=settings,
        dependencies=dependencies,
        supervisor_planner=ProgressPlanner(settings),
    )
    state = create_initial_state(
        "Q355B 12mm plate GMAW butt joint flat AWS D1.1 pWPS draft",
        "auto_draft",
        run_id="graph_model_fallback_test",
    )

    result = build_auto_draft_graph().invoke({"pwps_state": state, "context": context})

    final_state = result["pwps_state"]
    field = final_state.fields["shielding_gas"]
    assert final_state.status == "done"
    assert field.status == "suggested"
    assert field.source["type"] == "model_fallback"
    assert field.source["evidence_ids"] == []
    assert field.confirmation == {"required": True, "confirmed": False}
    assert any(
        entry["node"] == "web_search" and entry["event_type"] == "tool_result"
        for entry in final_state.trace
    )


def test_graph_does_not_write_status_words_as_field_values(tmp_path: Path):
    settings = Settings()
    settings.paths.output_dir = tmp_path
    dependencies = AutoDraftDependencies(
        llm_client=object(),
        search_provider=StaticSearchProvider(),
        requirement_tool=StaticRequirementTool(),
        knowledge_planning_tool=StaticPlanningTool(),
        field_reasoning_tool=StatusWordReasoningTool(),
    )
    context = GraphRuntimeContext(
        settings=settings,
        dependencies=dependencies,
        supervisor_planner=ProgressPlanner(settings),
    )
    state = create_initial_state(
        "Q355B 12mm plate GMAW butt joint flat AWS D1.1 pWPS draft",
        "auto_draft",
        run_id="graph_status_word_test",
    )

    result = build_auto_draft_graph().invoke({"pwps_state": state, "context": context})

    field = result["pwps_state"].fields["shielding_gas"]
    assert field.value is None
    assert field.status == "missing"
