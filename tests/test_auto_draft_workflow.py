import json
from pathlib import Path

from pwps_agent.config import Settings
from pwps_agent.core.contracts import SearchResult
from pwps_agent.workflows.auto_draft import AutoDraftDependencies, run_auto_draft


class StaticRequirementTool:
    def __call__(self, state, client):
        from pwps_agent.core.contracts import ToolResult

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
            summary="ok",
        )


class StaticSearchProvider:
    def __init__(self) -> None:
        self.queries: list[tuple[str, str]] = []

    def search(self, query: str, query_id: str):
        self.queries.append((query_id, query))
        return [
            SearchResult(
                result_id="r1",
                query_id=query_id,
                provider="tavily",
                title="WPS example",
                url="https://example.com/wps",
                snippet="ER50-6 is a candidate filler material.",
            )
        ]


class StaticReasoningTool:
    def __call__(self, state, evidence, client):
        from pwps_agent.core.contracts import ToolResult

        return ToolResult(
            tool_name="field_reasoning",
            success=True,
            state_patch={
                "fields": {
                    "base_material": {
                        "value": "S355 J0",
                        "status": "need_confirmation",
                        "confidence": "medium",
                        "evidence_ids": ["ev_r1"],
                        "confirmation": {"required": True, "confirmed": False},
                    },
                    "shielding_gas": {
                        "value": "Ar+CO2",
                        "status": "candidate",
                        "confidence": "medium",
                        "evidence_ids": ["ev_r1"],
                        "confirmation": {"required": True, "confirmed": False},
                    }
                }
            },
            summary="reasoned candidates",
        )


class StaticPlanningTool:
    def __call__(self, state, client):
        from pwps_agent.core.contracts import ToolResult

        return ToolResult(
            tool_name="knowledge_planning",
            success=True,
            state_patch={
                "knowledge_queries": [
                    {
                        "query_id": "kq_position_1",
                        "purpose": "similar_case",
                        "query_text": "Q355B GMAW plate common welding positions WPS",
                        "target_fields": ["welding_position"],
                        "rationale": "Need common welding positions.",
                        "preferred_sources": ["web"],
                    }
                ]
            },
            summary="planned queries",
        )


def test_run_auto_draft_persists_expected_artifacts(tmp_path: Path) -> None:
    settings = Settings()
    settings.paths.output_dir = tmp_path
    search_provider = StaticSearchProvider()
    deps = AutoDraftDependencies(
        llm_client=object(),
        search_provider=search_provider,
        requirement_tool=StaticRequirementTool(),
        knowledge_planning_tool=StaticPlanningTool(),
        field_reasoning_tool=StaticReasoningTool(),
    )

    result = run_auto_draft(
        "Q355B 12mm GMAW pWPS",
        settings=settings,
        dependencies=deps,
        run_id="run_test",
    )

    run_dir = tmp_path / "run_test"
    assert search_provider.queries == [
        ("kq_position_1", "Q355B GMAW plate common welding positions WPS")
    ]
    assert result.state.fields["base_material"].value == "Q355B"
    assert result.state.fields["base_material"].status == "filled"
    assert result.state.fields["base_material"].candidates[0]["value"] == "S355 J0"
    assert result.state.fields["shielding_gas"].value == "Ar+CO2"
    assert (run_dir / "pwps.json").exists()
    assert (run_dir / "pwps_draft.md").exists()
    assert (run_dir / "field_report.json").exists()
    assert (run_dir / "trace.json").exists()
    evidence_index = json.loads((run_dir / "evidence_index.json").read_text(encoding="utf-8"))
    assert evidence_index["search_context"]["queries"][0]["query_id"] == "kq_position_1"
    assert evidence_index["evidence_to_fields"]["ev_r1"] == ["base_material", "shielding_gas"]
    assert evidence_index["field_to_evidence"]["shielding_gas"] == ["ev_r1"]
    assert json.loads((run_dir / "field_report.json").read_text(encoding="utf-8"))[
        "candidate_fields"
    ] == ["shielding_gas"]
