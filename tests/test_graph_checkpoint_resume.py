import json
from pathlib import Path

from pwps_agent.config import Settings
from pwps_agent.core.contracts import SearchResult, ToolResult
from pwps_agent.core.state import create_initial_state
from pwps_agent.graph.builder import build_auto_draft_graph
from pwps_agent.graph.checkpoints import load_latest_checkpoint
from pwps_agent.graph.state import GraphRuntimeContext
from pwps_agent.workflows.auto_draft import AutoDraftDependencies


class StaticRequirementTool:
    def __call__(self, state, client):
        return ToolResult(
            tool_name="requirement_understanding",
            success=True,
            state_patch={
                "core_fields": {"base_material": "Q355B"},
                "fields": {"base_material": {"value": "Q355B", "status": "filled"}},
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
                        "query_id": "kq_1",
                        "purpose": "similar_case",
                        "query_text": "Q355B GMAW WPS",
                        "target_fields": ["shielding_gas"],
                        "rationale": "Find shielding gas evidence.",
                        "preferred_sources": ["web"],
                    }
                ]
            },
            summary="planned queries",
        )


class StaticSearchProvider:
    def search(self, query: str, query_id: str):
        return [
            SearchResult(
                result_id="r1",
                query_id=query_id,
                provider="fake",
                snippet="Ar+CO2 shielding gas.",
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
                        "evidence_ids": ["ev_r1"],
                    }
                }
            },
            summary="reasoned fields",
        )


def _context(tmp_path: Path, interrupt_after_steps=None):
    settings = Settings()
    settings.paths.output_dir = tmp_path
    dependencies = AutoDraftDependencies(
        llm_client=object(),
        search_provider=StaticSearchProvider(),
        requirement_tool=StaticRequirementTool(),
        knowledge_planning_tool=StaticPlanningTool(),
        field_reasoning_tool=StaticReasoningTool(),
    )
    return GraphRuntimeContext(
        settings=settings,
        dependencies=dependencies,
        checkpoint_enabled=True,
        interrupt_after_steps=interrupt_after_steps,
    )


def test_graph_persists_latest_checkpoint_after_runtime_nodes(tmp_path: Path):
    state = create_initial_state("Q355B 12mm GMAW", "auto_draft", run_id="checkpoint_full")

    result = build_auto_draft_graph().invoke(
        {"pwps_state": state, "context": _context(tmp_path)}
    )

    final_state = result["pwps_state"]
    checkpoint_dir = tmp_path / "checkpoint_full" / "checkpoints"
    latest = json.loads((checkpoint_dir / "latest.json").read_text(encoding="utf-8"))
    checkpoint_files = sorted(path.name for path in checkpoint_dir.glob("*.json"))
    assert final_state.status == "done"
    assert latest["state"]["status"] == "done"
    assert "0001-requirement_understanding.json" in checkpoint_files
    assert "latest.json" in checkpoint_files


def test_graph_can_interrupt_and_resume_from_latest_checkpoint(tmp_path: Path):
    state = create_initial_state("Q355B 12mm GMAW", "auto_draft", run_id="resume_run")

    interrupted = build_auto_draft_graph().invoke(
        {"pwps_state": state, "context": _context(tmp_path, interrupt_after_steps=1)}
    )["pwps_state"]

    assert interrupted.status == "interrupted"
    assert interrupted.fields["base_material"].value == "Q355B"
    assert any(entry["event_type"] == "interrupt" for entry in interrupted.trace)

    resumed_state = load_latest_checkpoint(tmp_path, "resume_run", resume=True)
    resumed = build_auto_draft_graph().invoke(
        {"pwps_state": resumed_state, "context": _context(tmp_path)}
    )["pwps_state"]

    assert resumed.status == "done"
    assert resumed.fields["base_material"].value == "Q355B"
    assert resumed.fields["shielding_gas"].value == "Ar+CO2"
