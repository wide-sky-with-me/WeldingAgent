# Auto Draft Quality Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the draft workflow from a single-pass pipeline into a planner-executor-verifier-synthesis loop that improves evidence quality, field coverage, and final pWPS draft usefulness while preserving uncertainty, stage-one safety boundaries, and the repository's two interaction modes.

**Architecture:** Add deterministic quality-verification contracts and a graph verifier node before synthesis. The same loop supports both modes: in `auto_draft`, an LLM takes the role that a human reviewer would otherwise play by using verifier feedback to refine searches, produce cautious suggestions, and synthesize a draft; in `guided_confirmation`, verifier feedback becomes the structured review checklist shown to the human for confirmation or correction. Do not introduce a welding rule engine; model fallback remains `suggested`, low-confidence, and confirmation-required.

**Tech Stack:** Python, Pydantic, LangGraph, LangChain structured output, existing `PWPSState`, `ToolResult`, `Evidence`, `FieldState`, pytest, uv.

---

## Context

The current `auto_draft` graph can run end to end, but the live smoke command:

```bash
uv run pwps-agent auto-draft \
  "Q355B 12mm plate GMAW butt joint flat position AWS D1.1 pWPS draft" \
  --output-dir outputs/pwps-agent-demo \
  --run-id demo_auto
```

produced a technically valid but weak draft: 41 fields total, 7 `filled`, 2 `candidate`, 2 `suggested`, 30 `missing`, and 42 risks. The trace showed a single pass through `requirement_understanding -> knowledge_planning -> web_search -> field_reasoning -> compose_draft`. Evidence was mostly web snippets, with `TAVILY_SEARCH_DEPTH=basic` and `TAVILY_INCLUDE_RAW_CONTENT=false`, so `field_reasoning` generated only four candidate/suggested fields.

This plan addresses the root workflow issue: the system currently has no explicit self-review gate and no bounded refinement loop when planned target fields remain uncovered.

## Execution Method

The user selected subagent-driven implementation for this work. Implementation should use `superpowers:subagent-driven-development`: dispatch a fresh implementer per task, then run a spec-compliance review and code-quality review before marking that task complete.

Before each implementation task, the implementer must read the applicable technical specifications and project guidance:

- `AGENTS.md`, especially Core Design Principles and Agent Working Rules.
- This plan file and the specific task being executed.
- Relevant Domain Skills under `src/pwps_agent/domain_skills/`.
- Relevant centralized prompts under `configs/prompts/`.
- Official framework/library documentation when changing framework behavior, especially LangGraph, Pydantic, LangChain structured output, or CLI behavior.

The current uncommitted prompt/domain-skill/roadmap changes are allowed to be modified when they are part of the new target behavior. Existing code paths, tests, prompts, and compatibility layers may be changed or deleted if they conflict with this quality-loop architecture. Do not preserve obsolete logic for its own sake; remove it deliberately, update tests/docs, and verify the replacement behavior.

## Interaction Mode Semantics

The quality loop is shared, but the actor responsible for correction differs by mode.

```text
auto_draft
  planner: LLM Supervisor plans evidence and field coverage.
  executor: runtime tools search, extract, reason, merge, and render.
  verifier: deterministic quality tool checks coverage, evidence, risks, and forbidden inference.
  synthesis: LLM/tool synthesis acts as the human reviewer substitute, using verifier feedback to refine or produce low-confidence suggestions.

guided_confirmation
  planner: LLM Supervisor plans evidence and field groups.
  executor: runtime tools prepare candidates, evidence, and grouped confirmation views.
  verifier: deterministic quality tool produces the review checklist and flags what needs human judgment.
  synthesis: human confirmation/correction drives promotion; the graph should use `ASK_USER` rather than silently replacing the human with model fallback.
```

Mode-specific rule:

- `auto_draft` may run bounded `refine_search` loops and controlled `model_fallback` suggestions because the model is standing in for the reviewer.
- `guided_confirmation` must not silently convert unresolved verifier findings into final-looking suggestions. It should surface verifier findings in confirmation views, pause with `ASK_USER`, and only promote user-confirmed fields.
- Both modes use the same quality contracts and trace vocabulary so artifacts remain comparable.

## File Map

- Create `src/pwps_agent/core/quality.py`: Pydantic contracts for draft coverage, evidence quality, refinement recommendations, and synthesis readiness.
- Create `src/pwps_agent/tools/draft_verifier.py`: deterministic verifier that inspects `PWPSState` and returns a `ToolResult` containing a `DraftQualityReport`.
- Modify `src/pwps_agent/core/state.py`: add serializable quality report and refinement bookkeeping fields to `PWPSState`.
- Modify `src/pwps_agent/core/state_merge.py`: allow quality report and refinement bookkeeping patches.
- Modify `src/pwps_agent/agent/action_schema.py`: add explicit `VERIFY_DRAFT` action type if the current enum/schema requires action whitelisting.
- Modify `src/pwps_agent/graph/nodes.py`: add verifier node execution and trace records.
- Modify `src/pwps_agent/graph/router.py`: route `VERIFY_DRAFT` to the verifier node or route existing `CALL_TOOL(draft_verifier)` if that better matches the current action schema.
- Modify `src/pwps_agent/graph/builder.py`: wire the verifier node into the graph.
- Modify `src/pwps_agent/graph/supervisor.py`: make deterministic safe progression use `planner -> executor -> verifier -> refine-or-synthesis`, with a bounded refinement loop.
- Modify `src/pwps_agent/core/modes.py` and `src/pwps_agent/workflows/guided_confirmation.py` only if needed to surface verifier findings in guided confirmation views without changing confirmation semantics.
- Modify `src/pwps_agent/tools/knowledge_planning.py`: accept verifier feedback as planning context for supplemental/refinement queries.
- Modify `src/pwps_agent/tools/field_reasoning.py`: include field schema, missing fields, target fields, current status, and blocked/fallback rules in the prompt input.
- Modify `configs/prompts/field_reasoning.md`: align prompt with richer structured context while keeping output shape in Pydantic schema.
- Modify `src/pwps_agent/tools/evidence.py`: add source quality helpers or reuse existing source-tier logic for verifier scoring.
- Modify `src/pwps_agent/knowledge/web_search_provider.py`: preserve raw content when enabled and support safer quality-oriented provider configuration.
- Modify `src/pwps_agent/config.py`: document and test quality-oriented search defaults without breaking existing env overrides.
- Modify `src/pwps_agent/render/markdown.py` or current render module: add concise quality summary and reduce missing-field noise in the main draft.
- Modify `src/pwps_agent/storage/persist.py`: persist quality reports in `pwps.json` and optionally `quality_report.json`.
- Modify `tests/test_draft_quality.py`: unit tests for quality contracts and verifier behavior.
- Modify `tests/test_graph_auto_draft.py`: graph tests for verifier routing, bounded refinement, and synthesis gating.
- Modify `tests/test_graph_guided_confirmation.py` and `tests/test_guided_confirmation.py`: regression tests proving verifier findings in guided mode produce human-facing confirmation needs instead of silent model fallback.
- Modify `tests/test_knowledge_planning.py`: tests for refinement context in planned queries.
- Modify `tests/test_evidence_reasoning.py`: tests for richer field-reasoning prompt context and fallback status handling.
- Modify `tests/test_render.py`: tests for quality summary and missing-field noise reduction.
- Modify `tests/test_config.py` and `tests/test_web_search_provider.py`: tests for raw-content/search-depth behavior.
- Modify `docs/superpowers/plans/2026-05-25-auto-draft-quality-loop.md`: mark tasks complete with verification evidence as implementation progresses.
- Modify `AGENTS.md`: update Current Implementation Progress only after implementation and verification actually pass.

## Quality Loop Contract

The target loop is:

```text
planner
  -> executor
  -> verifier
  -> synthesis, when quality is acceptable
  -> auto_draft refine planner, when critical planned fields remain uncovered and attempts remain
  -> guided_confirmation ASK_USER, when human confirmation/correction is required
  -> synthesis with explicit low-quality statement, when auto_draft attempts are exhausted
```

The first implementation should use deterministic verifier rules. LLM-based self-critique can be added later, but this plan does not require it.

Minimum verifier outputs:

- `field_counts`: count by `filled`, `candidate`, `suggested`, `missing`, `need_confirmation`, `conflict`, `user_confirmed`.
- `critical_missing_fields`: missing fields that block a useful pWPS draft, excluding project metadata that must not be invented.
- `target_field_coverage`: per planned query, which target fields received values or candidates.
- `weak_evidence_fields`: candidate/suggested fields supported only by low-tier web evidence or no evidence.
- `low_quality_sources`: source refs from social, forum, paywall, or generic low-quality pages.
- `blocked_inference_violations`: any project metadata or prohibited field filled by model/web inference.
- `recommended_action`: `synthesize`, `refine_search`, or `synthesize_with_limitations`.
- `refinement_focus_fields`: fields to target in the next planning round.
- `human_review_fields`: fields that should be displayed for guided confirmation.
- `mode_guidance`: short machine-readable guidance such as `auto_refine`, `auto_suggest_with_limitations`, or `ask_user_for_confirmation`.

## Task 1: Quality Contracts

**Files:**
- Create: `src/pwps_agent/core/quality.py`
- Modify: `src/pwps_agent/core/state.py`
- Modify: `src/pwps_agent/core/state_merge.py`
- Test: `tests/test_draft_quality.py`

- [x] **Step 1: Write failing tests for quality models and merge support**

Add tests that create a `DraftQualityReport`, attach it to `PWPSState`, and merge it through the existing state patch engine.

```python
from pwps_agent.core.quality import DraftQualityReport, FieldCoverageReport
from pwps_agent.core.state import create_initial_state
from pwps_agent.core.state_merge import merge_state_patch


def test_quality_report_is_serializable_on_state() -> None:
    state = create_initial_state(
        user_input="Q355B 12mm plate GMAW butt joint flat position AWS D1.1 pWPS draft",
        run_id="quality_contract",
    )
    report = DraftQualityReport(
        quality_level="partial",
        recommended_action="refine_search",
        field_counts={"filled": 7, "candidate": 2, "suggested": 2, "missing": 30},
        critical_missing_fields=["filler_material", "polarity", "preheat_temperature"],
        weak_evidence_fields=["current_range"],
        low_quality_sources=["https://www.facebook.com/example"],
        blocked_inference_violations=[],
        refinement_focus_fields=["filler_material", "polarity"],
        human_review_fields=["filler_material", "polarity", "preheat_temperature"],
        mode_guidance="auto_refine",
        target_field_coverage=[
            FieldCoverageReport(
                query_id="kq_002",
                target_fields=["filler_material", "filler_diameter"],
                covered_fields=[],
                missing_target_fields=["filler_material", "filler_diameter"],
            )
        ],
    )

    updated = merge_state_patch(state, {"quality_report": report.model_dump()})

    assert updated.quality_report is not None
    assert updated.quality_report["recommended_action"] == "refine_search"
    assert updated.quality_report["human_review_fields"] == [
        "filler_material",
        "polarity",
        "preheat_temperature",
    ]
    assert updated.model_dump()["quality_report"]["quality_level"] == "partial"
```

- [x] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_draft_quality.py::test_quality_report_is_serializable_on_state -q
```

Expected: fail because `pwps_agent.core.quality` or `PWPSState.quality_report` does not exist.

- [x] **Step 3: Implement quality contracts**

Create `src/pwps_agent/core/quality.py` with Pydantic models using only serializable fields.

```python
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


QualityLevel = Literal["good", "partial", "low"]
RecommendedAction = Literal["synthesize", "refine_search", "synthesize_with_limitations"]


class FieldCoverageReport(BaseModel):
    query_id: str | None = None
    target_fields: list[str] = Field(default_factory=list)
    covered_fields: list[str] = Field(default_factory=list)
    missing_target_fields: list[str] = Field(default_factory=list)


class EvidenceQualityReport(BaseModel):
    evidence_count: int = 0
    by_source_tier: dict[str, int] = Field(default_factory=dict)
    by_source_type: dict[str, int] = Field(default_factory=dict)
    low_quality_sources: list[str] = Field(default_factory=list)


class DraftQualityReport(BaseModel):
    quality_level: QualityLevel
    recommended_action: RecommendedAction
    field_counts: dict[str, int] = Field(default_factory=dict)
    critical_missing_fields: list[str] = Field(default_factory=list)
    weak_evidence_fields: list[str] = Field(default_factory=list)
    low_quality_sources: list[str] = Field(default_factory=list)
    blocked_inference_violations: list[str] = Field(default_factory=list)
    refinement_focus_fields: list[str] = Field(default_factory=list)
    human_review_fields: list[str] = Field(default_factory=list)
    mode_guidance: str | None = None
    target_field_coverage: list[FieldCoverageReport] = Field(default_factory=list)
    evidence_quality: EvidenceQualityReport = Field(default_factory=EvidenceQualityReport)
    notes: list[str] = Field(default_factory=list)
```

Modify `PWPSState` to include:

```python
quality_report: dict[str, Any] | None = None
refinement_attempts: int = 0
max_refinement_attempts: int = 2
```

Modify `state_merge.py` allowed patch keys to include:

```python
"quality_report",
"refinement_attempts",
"max_refinement_attempts",
```

- [x] **Step 4: Run quality contract test**

Run:

```bash
uv run pytest tests/test_draft_quality.py::test_quality_report_is_serializable_on_state -q
```

Expected: pass.

**Task 1 Status:** Completed. Implementation added quality Pydantic contracts, state fields, merge support, contract validation at state/merge boundaries, and guarded refinement counter patches. Spec-compliance and code-quality subagent reviews both approved.

**Task 1 Verification:**

```text
uv run pytest tests/test_draft_quality.py tests/test_state_merge.py -q
12 passed in 0.07s

uv run python -m compileall -q src tests
passed with no output (worker verification)
```

## Task 2: Deterministic Draft Verifier Tool

**Files:**
- Create: `src/pwps_agent/tools/draft_verifier.py`
- Test: `tests/test_draft_quality.py`

- [x] **Step 1: Write failing verifier tests**

Add tests for missing critical fields, weak evidence, low-quality sources, and blocked metadata inference.

```python
from pwps_agent.core.state import create_initial_state
from pwps_agent.tools.draft_verifier import verify_draft_quality


def test_verifier_recommends_refinement_for_uncovered_critical_fields() -> None:
    state = create_initial_state(
        user_input="Q355B 12mm plate GMAW butt joint flat position AWS D1.1 pWPS draft",
        run_id="quality_refine",
    )
    state.knowledge_queries = [
        {
            "query_id": "kq_002",
            "target_fields": ["filler_material", "polarity", "preheat_temperature"],
        }
    ]
    state.fields["applicable_standard"].value = "AWS D1.1"
    state.fields["applicable_standard"].status = "filled"
    state.fields["base_material"].value = "Q355B"
    state.fields["base_material"].status = "filled"

    result = verify_draft_quality(state)

    report = result.state_patch["quality_report"]
    assert result.success is True
    assert report["recommended_action"] == "refine_search"
    assert "filler_material" in report["critical_missing_fields"]
    assert report["target_field_coverage"][0]["missing_target_fields"] == [
        "filler_material",
        "polarity",
        "preheat_temperature",
    ]
```

```python
def test_verifier_detects_blocked_metadata_inference() -> None:
    state = create_initial_state(user_input="Q355B GMAW", run_id="blocked_metadata")
    state.fields["project_name"].value = "Bridge Project"
    state.fields["project_name"].status = "suggested"
    state.fields["project_name"].source = {"type": "model_fallback"}

    result = verify_draft_quality(state)

    report = result.state_patch["quality_report"]
    assert "project_name" in report["blocked_inference_violations"]
    assert report["recommended_action"] == "synthesize_with_limitations"
```

- [x] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_draft_quality.py -q
```

Expected: fail because `draft_verifier` is missing.

- [x] **Step 3: Implement verifier**

Implement deterministic checks in `src/pwps_agent/tools/draft_verifier.py`.

Core constants:

```python
CRITICAL_DRAFT_FIELDS = {
    "applicable_standard",
    "base_material",
    "thickness",
    "workpiece_type",
    "welding_process",
    "joint_type",
    "welding_position",
    "filler_material",
    "shielding_gas",
    "polarity",
    "current_range",
    "voltage_range",
    "preheat_temperature",
    "interpass_temperature",
}

BLOCKED_INFERRED_FIELDS = {
    "pwps_no",
    "revision_no",
    "date",
    "company",
    "project_name",
    "client",
    "contract_no",
}

LOW_QUALITY_SOURCE_MARKERS = (
    "facebook.com",
    "instagram.com",
    "scribd.com",
    "forum",
    "myshopify.com",
)
```

Implementation behavior:

- Count field statuses.
- Treat `filled`, `candidate`, `suggested`, `user_confirmed`, and `need_confirmation` as covered for coverage reporting.
- Mark missing critical fields, excluding pipe-only `diameter` for plate workpieces.
- Mark weak fields when status is `candidate` or `suggested` and all linked evidence is `webpage`, `low`, missing, or empty.
- Mark low-quality sources by URL markers.
- Mark blocked inference violations when blocked metadata fields are not missing and their source is not `user_input` or `user_confirmation`.
- Recommend:
  - `refine_search` when there are critical missing fields and `refinement_attempts < max_refinement_attempts`.
  - `synthesize_with_limitations` when blocked inference exists or attempts are exhausted.
  - `synthesize` when there are no critical missing fields and no blocked inference violations.

- [x] **Step 4: Run verifier tests**

Run:

```bash
uv run pytest tests/test_draft_quality.py -q
```

Expected: pass.

**Task 2 Status:** Completed. Implementation added deterministic `verify_draft_quality()`, quality report generation, stable field counts, target-field coverage, weak evidence detection, low-quality source detection, blocked metadata inference detection, conditional pipe/tube `diameter` criticality, and mode-specific guidance/human review fields. Spec review passed after guided-mode review fields were expanded; code-quality findings for pipe/tube diameter and clean guided-mode guidance were fixed and locally re-reviewed.

**Task 2 Verification:**

```text
uv run pytest tests/test_draft_quality.py tests/test_state_merge.py -q
20 passed in 0.08s

uv run python -m compileall -q src tests
passed with no output

git diff --check -- src/pwps_agent/tools/draft_verifier.py tests/test_draft_quality.py src/pwps_agent/core/state.py src/pwps_agent/core/state_merge.py src/pwps_agent/core/quality.py docs/superpowers/plans/2026-05-25-auto-draft-quality-loop.md AGENTS.md
passed with no output
```

## Task 3: Graph Verification Node

**Files:**
- Modify: `src/pwps_agent/agent/action_schema.py`
- Modify: `src/pwps_agent/graph/nodes.py`
- Modify: `src/pwps_agent/graph/router.py`
- Modify: `src/pwps_agent/graph/builder.py`
- Test: `tests/test_graph_auto_draft.py`

- [x] **Step 1: Write graph verifier test**

Add a graph test with static tools where field reasoning leaves critical fields missing. Assert that the verifier runs before compose and records a trace event.

```python
def test_graph_runs_verifier_before_composing_draft() -> None:
    result = run_graph_auto_draft(
        "Q355B 12mm plate GMAW butt joint flat position AWS D1.1 pWPS draft",
        AutoDraftDependencies(
            requirement_tool=StaticRequirementTool(),
            knowledge_planning_tool=StaticKnowledgePlanningTool(),
            search_provider=StaticSearchProvider(),
            field_reasoning_tool=StaticReasoningTool(fields={}),
            llm_client=StaticStructuredClient(),
        ),
        output_dir=tmp_path,
        run_id="verify_before_compose",
    )

    nodes = [entry["node"] for entry in result.state.trace]
    assert "draft_verifier" in nodes
    assert nodes.index("draft_verifier") < nodes.index("compose_draft")
    assert result.state.quality_report["recommended_action"] in {
        "refine_search",
        "synthesize_with_limitations",
    }
```

Adjust helper names to match existing test fixtures in `tests/test_graph_auto_draft.py`.

- [x] **Step 2: Run graph test**

Run:

```bash
uv run pytest tests/test_graph_auto_draft.py::test_graph_runs_verifier_before_composing_draft -q
```

Expected: pass after local implementation because the verifier node was wired before this specific focused run.

- [x] **Step 3: Wire verifier node**

Add a node in `graph/nodes.py`:

```python
def verify_draft_node(graph_state: GraphState) -> dict:
    state = graph_state["pwps_state"].model_copy(deep=True)
    result = verify_draft_quality(state)
    state = _merge_state_patch(state, result.state_patch)
    _append_trace(
        state,
        "draft_verifier",
        "tool_result",
        result.summary,
        {"success": result.success, "quality_report": result.state_patch.get("quality_report")},
    )
    _finalize_runtime_node(state, graph_state["context"], "draft_verifier")
    return {"pwps_state": state}
```

Wire it in `builder.py` and `router.py`. Prefer an explicit `VERIFY_DRAFT` action if action schema already uses enumerated action types. If action schema is easier to preserve with `CALL_TOOL` then route `CALL_TOOL` plus `tool_name="draft_verifier"` to this node.

- [x] **Step 4: Run graph verifier test**

Run:

```bash
uv run pytest tests/test_graph_auto_draft.py::test_graph_runs_verifier_before_composing_draft -q
```

Expected: pass.

**Task 3 Status:** Completed locally after subagent review became unavailable due usage limits. Implementation added `VERIFY_DRAFT` to `AgentAction`, wired `verify_draft_node` into the graph, routed verifier actions, and added safe Supervisor overrides so premature `COMPOSE_DRAFT`/`FINISH` actions cannot bypass draft verification.

**Task 3 Verification:**

```text
uv run pytest tests/test_graph_auto_draft.py::test_graph_runs_verifier_before_composing_draft -q
1 passed in 0.30s

uv run pytest tests/test_graph_auto_draft.py -q
9 passed in 0.52s

uv run pytest tests/test_graph_supervisor_planner.py tests/test_graph_auto_draft.py tests/test_draft_quality.py -q
37 passed in 0.67s

uv run python -m compileall -q src tests
passed with no output

git diff --check -- src/pwps_agent/core/contracts.py src/pwps_agent/graph/nodes.py src/pwps_agent/graph/router.py src/pwps_agent/graph/builder.py src/pwps_agent/graph/supervisor.py tests/test_graph_auto_draft.py
passed with no output
```

## Task 4: Safe Progression and Bounded Refinement Loop

**Files:**
- Modify: `src/pwps_agent/graph/supervisor.py`
- Modify: `src/pwps_agent/graph/nodes.py`
- Modify: `src/pwps_agent/tools/knowledge_planning.py`
- Test: `tests/test_graph_auto_draft.py`
- Test: `tests/test_graph_guided_confirmation.py`
- Test: `tests/test_knowledge_planning.py`

- [x] **Step 1: Write failing tests for refine-or-synthesis routing**

Add tests for both branches:

```python
def test_graph_refines_when_verifier_finds_critical_missing_fields() -> None:
    result = run_graph_auto_draft(
        "Q355B 12mm plate GMAW butt joint flat position AWS D1.1 pWPS draft",
        dependencies_with_reasoning_fields({}),
        output_dir=tmp_path,
        run_id="refine_once",
    )

    state = result.state
    assert state.refinement_attempts == 1
    assert any(
        entry["node"] == "supervisor"
        and entry["event_type"] == "agent_action"
        and "refine" in (entry.get("summary") or "").lower()
        for entry in state.trace
    )
```

```python
def test_graph_synthesizes_with_limitations_after_refinement_limit() -> None:
    result = run_graph_auto_draft(
        "Q355B 12mm plate GMAW butt joint flat position AWS D1.1 pWPS draft",
        dependencies_with_reasoning_fields({}),
        output_dir=tmp_path,
        run_id="refine_limited",
        max_refinement_attempts=1,
    )

    state = result.state
    assert state.quality_report["recommended_action"] == "synthesize_with_limitations"
    assert state.status == "done"
    assert state.draft_markdown
```

Use existing dependency injection patterns rather than adding a broad new public API if `max_refinement_attempts` can be passed through settings/context.

- [x] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_graph_auto_draft.py::test_graph_refines_when_verifier_finds_critical_missing_fields tests/test_graph_auto_draft.py::test_graph_synthesizes_with_limitations_after_refinement_limit -q
```

Expected: fail because refinement loop is not implemented.

- [x] **Step 3: Implement routing rules**

Update safe progression in `graph/supervisor.py`:

- After `field_reasoning`, route to `draft_verifier`.
- If `interaction_mode == "auto_draft"` and `quality_report.recommended_action == "refine_search"` and attempts remain, route to `knowledge_planning` in refinement mode. In this mode, the LLM is the reviewer substitute and may use verifier findings to refine evidence or produce controlled suggestions.
- If `interaction_mode == "guided_confirmation"` and verifier finds critical missing, weak evidence, candidate, suggested, conflict, or `human_review_fields`, route to `ASK_USER` or the existing guided confirmation pause path. In this mode, verifier findings must be shown to the human; they must not be silently resolved by model fallback.
- Increment `refinement_attempts` before the refinement planning pass.
- Do not rerun `requirement_understanding` for refinement.
- Allow repeated `knowledge_planning`, `web_search`, and `field_reasoning` only when the active reason is refinement; preserve existing repeated-action override protection for accidental loops.
- Route to compose when report says `synthesize` or `synthesize_with_limitations`.

Update trace summaries to clearly show:

```text
Verifier requested refinement for: filler_material, polarity, preheat_temperature
Refinement attempt 1/2
```

- [x] **Step 4: Add refinement context to knowledge planning**

Modify `knowledge_planning` input prompt/context to include:

- `quality_report.refinement_focus_fields`
- `quality_report.critical_missing_fields`
- `quality_report.weak_evidence_fields`
- previous query texts to avoid exact duplicates

Add a unit test that the generated user prompt contains the refinement fields. If the tool hides prompt construction, extract a small helper such as `_knowledge_planning_user_prompt(state)` and test it directly.

- [x] **Step 5: Run graph refinement tests**

Run:

```bash
uv run pytest tests/test_graph_auto_draft.py tests/test_knowledge_planning.py -q
```

Expected: pass.

- [x] **Step 6: Add guided-mode routing regression**

Add a test proving guided mode pauses for human review instead of using auto fallback:

```python
def test_guided_mode_surfaces_verifier_findings_to_user() -> None:
    result = run_graph_guided_confirmation(
        "Q355B 12mm plate GMAW butt joint flat position AWS D1.1 pWPS draft",
        dependencies_with_reasoning_fields({}),
        output_dir=tmp_path,
        run_id="guided_quality_review",
    )

    state = result.state
    assert state.status == "need_user_input"
    assert state.quality_report["human_review_fields"]
    assert any(entry["node"] == "draft_verifier" for entry in state.trace)
    assert any(entry["node"] == "ask_user" for entry in state.trace)
```

Use the actual guided graph helper names already present in `tests/test_graph_guided_confirmation.py`.

Run:

```bash
uv run pytest tests/test_graph_guided_confirmation.py -q
```

Expected: pass.

**Task 4 Status:** Completed locally after subagent execution became unavailable due usage limits. Implementation added verifier-driven auto refinement, refinement-attempt bookkeeping, stale-node refresh routing, guided-mode quality pauses, refinement context in knowledge planning, and a higher graph recursion limit for bounded refinement loops.

**Task 4 Verification:**

```text
uv run pytest tests/test_graph_auto_draft.py tests/test_graph_guided_confirmation.py tests/test_knowledge_planning.py -q
17 passed in 1.01s

uv run pytest tests/test_graph_supervisor_planner.py tests/test_graph_auto_draft.py tests/test_graph_guided_confirmation.py tests/test_knowledge_planning.py tests/test_draft_quality.py -q
45 passed in 1.03s

uv run python -m compileall -q src tests
passed with no output

git diff --check -- src/pwps_agent/graph/supervisor.py src/pwps_agent/tools/knowledge_planning.py tests/test_graph_auto_draft.py tests/test_graph_guided_confirmation.py tests/test_knowledge_planning.py
passed with no output
```

## Task 5: Evidence Quality and Search Configuration

**Files:**
- Modify: `src/pwps_agent/config.py`
- Modify: `src/pwps_agent/knowledge/web_search_provider.py`
- Modify: `src/pwps_agent/tools/evidence.py`
- Test: `tests/test_config.py`
- Test: `tests/test_web_search_provider.py`
- Test: `tests/test_evidence_reasoning.py`

- [x] **Step 1: Write failing tests for quality-oriented search config**

Add tests proving env overrides still work and raw content is preserved.

```python
def test_tavily_advanced_raw_content_settings_from_env(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "TAVILY_SEARCH_DEPTH=advanced",
                "TAVILY_INCLUDE_RAW_CONTENT=true",
                "WEB_SEARCH_MAX_RESULTS=8",
            ]
        ),
        encoding="utf-8",
    )

    settings = load_settings(env_file)

    assert settings.web_search.tavily_search_depth == "advanced"
    assert settings.web_search.tavily_include_raw_content is True
    assert settings.web_search.max_results == 8
```

```python
def test_tavily_parse_response_preserves_raw_content() -> None:
    payload = {
        "results": [
            {
                "title": "ER70S-6 datasheet",
                "url": "https://example.com/er70s-6",
                "content": "short snippet",
                "raw_content": "long datasheet content",
                "score": 0.9,
            }
        ]
    }

    results = TavilySearchProvider.parse_response("kq_001", payload)

    assert results[0].raw_content == "long datasheet content"
```

- [x] **Step 2: Run tests**

Run:

```bash
uv run pytest tests/test_config.py tests/test_web_search_provider.py -q
```

Expected: existing raw-content preservation may already pass; config defaults may need only documentation or fixture adjustment. If both pass, keep the tests as regression coverage and move to source ranking.

- [x] **Step 3: Add low-quality source detection helper**

In `tools/evidence.py`, add a helper used by verifier:

```python
def is_low_quality_source_ref(source_ref: str | None) -> bool:
    if not source_ref:
        return False
    lowered = source_ref.lower()
    return any(
        marker in lowered
        for marker in (
            "facebook.com",
            "instagram.com",
            "scribd.com",
            "myshopify.com",
            "/forum/",
            "topic_show",
        )
    )
```

Add a test in `tests/test_evidence_reasoning.py` for these markers.

- [x] **Step 4: Run evidence tests**

Run:

```bash
uv run pytest tests/test_evidence_reasoning.py tests/test_web_search_provider.py tests/test_config.py -q
```

Expected: pass.

**Task 5 Status:** Completed locally. Existing Tavily settings already supported advanced search depth, raw content inclusion, and raw-content parsing, so implementation added regression coverage and moved low-quality source detection into a shared evidence helper reused by the verifier.

**Task 5 Verification:**

```text
uv run pytest tests/test_evidence_reasoning.py tests/test_web_search_provider.py tests/test_config.py -q
22 passed in 0.14s

uv run python -m compileall -q src tests
passed with no output

git diff --check -- src/pwps_agent/tools/evidence.py src/pwps_agent/tools/draft_verifier.py tests/test_config.py tests/test_web_search_provider.py tests/test_evidence_reasoning.py docs/superpowers/plans/2026-05-25-auto-draft-quality-loop.md
passed with no output
```

## Task 6: Richer Field Reasoning Context

**Files:**
- Modify: `src/pwps_agent/tools/field_reasoning.py`
- Modify: `configs/prompts/field_reasoning.md`
- Test: `tests/test_evidence_reasoning.py`

- [x] **Step 1: Write failing prompt-context test**

Add a test that calls `_field_reasoning_user_prompt()` with a state containing missing target fields and asserts the prompt includes field IDs, labels, statuses, target fields, and blocked fields.

```python
def test_field_reasoning_prompt_includes_field_schema_and_targets() -> None:
    state = create_initial_state(
        user_input="Q355B 12mm plate GMAW butt joint flat position AWS D1.1 pWPS draft",
        run_id="reasoning_context",
    )
    state.knowledge_queries = [
        {
            "query_id": "kq_002",
            "target_fields": ["filler_material", "polarity"],
            "purpose": "filler_reference",
        }
    ]

    prompt = _field_reasoning_user_prompt(state, [])

    assert "filler_material" in prompt
    assert "焊材型号/分类号" in prompt
    assert "polarity" in prompt
    assert "blocked inferred fields" in prompt.lower()
    assert "project_name" in prompt
```

- [x] **Step 2: Run test to verify it fails or captures current weak prompt**

Run:

```bash
uv run pytest tests/test_evidence_reasoning.py::test_field_reasoning_prompt_includes_field_schema_and_targets -q
```

Expected: fail because the current prompt only contains core fields and evidence.

- [x] **Step 3: Implement prompt context**

Update `_field_reasoning_user_prompt()` to include:

- Core fields.
- Current field summary with `field_id`, label, status, current value, confidence.
- Missing fields.
- Planned query target fields and purposes.
- Quality report focus fields if present.
- Blocked inferred fields.
- Evidence with `evidence_id`, `source_type`, `source_tier`, `confidence`, `source_ref`, and content.

Keep this as structured plain text or JSON-like text. Do not add complex output JSON instructions to the prompt; the Pydantic schema remains the output contract.

- [x] **Step 4: Update prompt file**

In `configs/prompts/field_reasoning.md`, add these constraints:

- Fill only fields supported by evidence or allowed model fallback context.
- Prefer target fields from planned queries and verifier refinement focus.
- Never infer blocked project metadata.
- For web-only values use `candidate` or `suggested`, not `filled`.
- Use `suggested` with low confidence for model fallback fields that need confirmation.

- [x] **Step 5: Run field reasoning tests**

Run:

```bash
uv run pytest tests/test_evidence_reasoning.py -q
```

Expected: pass.

**Task 6 Status:** Completed locally. Implementation expanded the field-reasoning user prompt with current field schema/status, missing fields, planned-query targets, quality-report focus, blocked inferred fields, and evidence metadata while keeping Pydantic structured output as the output contract. The centralized prompt now prioritizes target/refinement fields and forbids blocked metadata inference.

**Task 6 Verification:**

```text
uv run pytest tests/test_evidence_reasoning.py -q
7 passed in 0.07s

uv run pytest tests/test_evidence_reasoning.py tests/test_web_search_provider.py tests/test_config.py -q
23 passed in 0.08s

uv run python -m compileall -q src tests
passed with no output

git diff --check -- src/pwps_agent/tools/field_reasoning.py configs/prompts/field_reasoning.md tests/test_evidence_reasoning.py
passed with no output
```

## Task 7: Controlled Model Fallback

**Files:**
- Modify: `src/pwps_agent/tools/field_reasoning.py`
- Modify: `src/pwps_agent/graph/nodes.py`
- Test: `tests/test_evidence_reasoning.py`
- Test: `tests/test_graph_auto_draft.py`
- Test: `tests/test_graph_guided_confirmation.py`

- [x] **Step 1: Write failing tests for fallback marking**

Add tests proving fallback fields are never `filled`.

```python
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
```

Add a test that blocked metadata is dropped from fallback patches:

```python
def test_model_fallback_drops_blocked_metadata_fields() -> None:
    fields = {
        "project_name": {"value": "Bridge Project", "status": "candidate"},
        "polarity": {"value": "DCEP", "status": "candidate"},
    }

    marked = _mark_model_fallback_fields(fields)

    assert "project_name" not in marked
    assert "polarity" in marked
```

- [x] **Step 2: Run tests**

Run:

```bash
uv run pytest tests/test_graph_auto_draft.py::test_model_fallback_marks_fields_as_suggested_low_confidence tests/test_graph_auto_draft.py::test_model_fallback_drops_blocked_metadata_fields -q
```

Expected: fail if fallback currently only marks when there is no external evidence or does not drop metadata.

- [x] **Step 3: Implement stricter fallback marking**

Update fallback helper so all fallback fields:

- Have `status="suggested"`.
- Have `confidence="low"`.
- Have `source={"type": "model_fallback", "evidence_ids": []}` unless evidence IDs exist.
- Have `confirmation={"required": True, "confirmed": False}`.
- Exclude blocked metadata fields.
- Are only applied automatically in `auto_draft`. In `guided_confirmation`, verifier findings and unresolved fields should be exposed through `ASK_USER` and confirmation views rather than silently applying fallback values.

- [x] **Step 4: Run fallback tests**

Run:

```bash
uv run pytest tests/test_graph_auto_draft.py tests/test_graph_guided_confirmation.py tests/test_evidence_reasoning.py -q
```

Expected: pass.

**Task 7 Status:** Completed locally. Model fallback patches now drop blocked project metadata, force fallback values to `suggested` with `low` confidence, mark source type as `model_fallback`, preserve explicit confirmation requirement, and keep graph behavior aligned with guided-mode human review pauses.

**Task 7 Verification:**

```text
uv run pytest tests/test_graph_auto_draft.py::test_model_fallback_marks_fields_as_suggested_low_confidence tests/test_graph_auto_draft.py::test_model_fallback_drops_blocked_metadata_fields tests/test_graph_auto_draft.py::test_graph_marks_model_fallback_fields_as_suggested_without_external_evidence -q
3 passed in 0.26s

uv run pytest tests/test_graph_auto_draft.py tests/test_graph_guided_confirmation.py tests/test_evidence_reasoning.py -q
23 passed in 0.90s

uv run python -m compileall -q src tests
passed with no output

git diff --check -- src/pwps_agent/graph/nodes.py src/pwps_agent/tools/draft_verifier.py tests/test_graph_auto_draft.py
passed with no output
```

## Task 8: Synthesis and Markdown Noise Reduction

**Files:**
- Modify: `src/pwps_agent/render/markdown.py` or current draft renderer module
- Modify: `src/pwps_agent/tools/risk_report.py`
- Modify: `src/pwps_agent/storage/persist.py`
- Test: `tests/test_render.py`

- [x] **Step 1: Locate renderer module**

Run:

```bash
rg -n "def render_pwps_draft|待确认项与风险提示|pWPS 草案" src/pwps_agent tests
```

Use the actual module path from the result in the edits below.

- [x] **Step 2: Write failing render test**

Add a test that a quality summary appears and non-critical project metadata missing fields are not all dumped into the main draft risk section.

```python
def test_draft_renders_quality_summary_and_limits_missing_noise() -> None:
    state = create_initial_state(
        user_input="Q355B 12mm plate GMAW butt joint flat position AWS D1.1 pWPS draft",
        run_id="render_quality",
    )
    state.quality_report = {
        "quality_level": "partial",
        "recommended_action": "synthesize_with_limitations",
        "field_counts": {"filled": 7, "candidate": 3, "suggested": 4, "missing": 27},
        "critical_missing_fields": ["preheat_temperature", "interpass_temperature"],
        "weak_evidence_fields": ["current_range"],
        "low_quality_sources": [],
        "blocked_inference_violations": [],
        "refinement_focus_fields": [],
        "target_field_coverage": [],
        "evidence_quality": {"evidence_count": 4, "by_source_tier": {"webpage": 4}},
        "notes": ["Refinement attempts exhausted."],
    }

    draft = render_pwps_draft(state)

    assert "Draft quality" in draft or "草案质量" in draft
    assert "preheat_temperature" in draft
    assert "project_name" not in draft.split("待确认项与风险提示")[-1]
```

- [x] **Step 3: Run render test**

Run:

```bash
uv run pytest tests/test_render.py::test_draft_renders_quality_summary_and_limits_missing_noise -q
```

Expected: fail because current renderer dumps all missing fields.

- [x] **Step 4: Implement concise quality summary**

Update renderer to add a short quality block near the top:

```text
## 草案质量摘要

- 质量等级: partial
- 后续动作: synthesize_with_limitations
- 字段覆盖: filled=7, candidate=3, suggested=4, missing=27
- 关键待确认: preheat_temperature, interpass_temperature
- 弱证据字段: current_range
```

Update missing/risk section to show:

- critical missing fields from quality report;
- candidate/suggested fields requiring confirmation;
- high-severity risks;
- link users to `field_report.json` for the full list.

Do not remove full risk data from `field_report.json`.

- [x] **Step 5: Persist optional quality artifact**

Update `persist_run_artifacts()` to write `quality_report.json` when `state.quality_report` is present.

Add test assertion in existing persistence tests or graph artifact tests:

```python
assert (run_dir / "quality_report.json").exists()
```

- [x] **Step 6: Run render/persistence tests**

Run:

```bash
uv run pytest tests/test_render.py tests/test_graph_auto_draft.py -q
```

Expected: pass.

**Task 8 Status:** Completed locally. Draft rendering now includes a concise quality summary, limits the main unresolved/risk section to critical missing fields, candidate/suggested/confirmation/conflict fields, and high-severity risks, while leaving full detail in `field_report.json`. Persistence writes `quality_report.json` whenever quality data is available.

**Task 8 Verification:**

```text
uv run pytest tests/test_render.py::test_draft_renders_quality_summary_and_limits_missing_noise tests/test_graph_auto_draft.py::test_auto_draft_graph_executes_tool_sequence_and_persists_artifacts tests/test_graph_auto_draft.py::test_run_graph_auto_draft_service_invokes_graph_and_persists_artifacts -q
3 passed in 0.33s

uv run pytest tests/test_render.py tests/test_graph_auto_draft.py -q
17 passed in 0.78s

uv run python -m compileall -q src tests
passed with no output

git diff --check -- src/pwps_agent/render/markdown.py src/pwps_agent/storage/persist.py tests/test_render.py tests/test_graph_auto_draft.py
passed with no output
```

## Task 9: Live Smoke and Progress Documentation

**Files:**
- Modify: `docs/superpowers/plans/2026-05-25-auto-draft-quality-loop.md`
- Modify: `AGENTS.md`

- [x] **Step 1: Run focused test suite**

Run:

```bash
uv run pytest tests/test_draft_quality.py tests/test_graph_auto_draft.py tests/test_graph_guided_confirmation.py tests/test_guided_confirmation.py tests/test_knowledge_planning.py tests/test_evidence_reasoning.py tests/test_render.py tests/test_config.py tests/test_web_search_provider.py -q
```

Expected: pass.

- [x] **Step 2: Run full verification**

Run:

```bash
uv run pytest -q
uv run python -m compileall -q src tests
git diff --check
```

Expected:

```text
pytest passes
compileall passes with no output
git diff --check passes with no output
```

- [x] **Step 3: Run live smoke with quality-oriented settings**

Run:

```bash
KNOWLEDGE_SOURCES=web,model \
TAVILY_SEARCH_DEPTH=advanced \
TAVILY_INCLUDE_RAW_CONTENT=true \
WEB_SEARCH_MAX_RESULTS=8 \
uv run pwps-agent auto-draft \
  "Q355B 12mm plate GMAW butt joint flat position AWS D1.1 pWPS draft" \
  --output-dir outputs/pwps-agent-demo \
  --run-id demo_auto_quality_loop
```

Expected:

- `outputs/pwps-agent-demo/demo_auto_quality_loop/pwps.json` exists.
- `pwps_draft.md` contains a quality summary.
- `quality_report.json` exists.
- `trace.json` contains `draft_verifier`.
- Candidate/suggested fields include at least several of `filler_material`, `polarity`, `shielding_gas`, `current_range`, `voltage_range`, `preheat_temperature`, or `interpass_temperature`.
- Any model fallback values are `suggested`, low-confidence, and confirmation-required.

- [x] **Step 4: Run guided-mode smoke or regression confirmation**

Run a guided-mode regression through the existing CLI/test path. If a live guided smoke is available, use it; otherwise the focused guided graph tests from Step 1 are the acceptance gate for this task.

Expected:

- verifier findings are present in state;
- unresolved quality findings lead to `need_user_input` or confirmation view content;
- no unresolved field is silently promoted by model fallback in guided mode.

- [x] **Step 5: Compare smoke output**

Run:

```bash
jq '[.fields[] | .status] | group_by(.) | map({status: .[0], count: length})' \
  outputs/pwps-agent-demo/demo_auto_quality_loop/pwps.json

jq '.recommended_action, .critical_missing_fields, .weak_evidence_fields' \
  outputs/pwps-agent-demo/demo_auto_quality_loop/quality_report.json
```

Expected: output is evidence for whether the quality loop improved the run. Do not claim the draft is compliant or approval-ready.

- [x] **Step 6: Update progress documentation**

Update this plan with:

- final status;
- focused test output;
- full verification output;
- live smoke output path;
- quality summary from `quality_report.json`.

Update `AGENTS.md` Current Implementation Progress only after verification passes. Add a concise bullet such as:

```text
- Draft workflows now include a planner-executor-verifier-synthesis quality loop. In `auto_draft`, the LLM uses verifier feedback for bounded refinement and cautious suggestions; in `guided_confirmation`, verifier findings are surfaced for human review. Runs persist `quality_report.json`.
```

**Task 9 Status:** Completed. Local verification passed, and the live quality-oriented auto-draft smoke completed after an external DeepSeek 503 retry cycle. The live trace shows the intended loop: initial verifier result `refine_search`, a second planning/search/reasoning pass, final verifier result `synthesize`, then draft composition and finish.

**Task 9 Verification:**

```text
uv run pytest tests/test_draft_quality.py tests/test_graph_auto_draft.py tests/test_graph_guided_confirmation.py tests/test_guided_confirmation.py tests/test_knowledge_planning.py tests/test_evidence_reasoning.py tests/test_render.py tests/test_config.py tests/test_web_search_provider.py -q
67 passed in 1.00s

uv run pytest tests/test_contracts.py tests/test_graph_supervisor_planner.py tests/test_graph_auto_draft.py -q
29 passed in 0.99s

uv run pytest -q
144 passed in 2.47s

uv run python -m compileall -q src tests
passed with no output

git diff --check
passed with no output

KNOWLEDGE_SOURCES=web,model TAVILY_SEARCH_DEPTH=advanced TAVILY_INCLUDE_RAW_CONTENT=true WEB_SEARCH_MAX_RESULTS=8 uv run pwps-agent auto-draft "Q355B 12mm plate GMAW butt joint flat position AWS D1.1 pWPS draft" --output-dir outputs/pwps-agent-quality-loop --run-id quality_loop_smoke3
outputs/pwps-agent-quality-loop/quality_loop_smoke3
status: done
```

**Live Smoke Evidence:**

```text
output_dir: outputs/pwps-agent-quality-loop/quality_loop_smoke3
artifacts: evidence_index.json, field_report.json, pwps.json, pwps_draft.md, quality_report.json, trace.json
trace: draft_verifier refine_search at step 15, then draft_verifier synthesize at step 30
quality: partial
recommended_action: synthesize
field_counts: candidate=12, filled=7, missing=18, suggested=4
critical_missing_fields: []
weak_evidence_fields: standard_year, base_material_standard, groove_type, weld_type, gas_flow_rate, polarity, current_range, voltage_range, travel_speed, heat_input, preheat_temperature, interpass_temperature
```

**Implementation Status:** Complete.

## Implementation Order

1. Task 1, because all later work needs serializable quality contracts.
2. Task 2, because deterministic verifier behavior is the root of the quality loop.
3. Task 3, because the graph must be able to run verifier before synthesis.
4. Task 4, because refinement is only meaningful after verifier routing exists.
5. Task 5, because better evidence quality improves verifier outcomes but should not block core loop testing.
6. Task 6, because richer reasoning context uses verifier and query-target data.
7. Task 7, because fallback must be safe before final synthesis uses it.
8. Task 8, because rendering should reflect the verified quality state.
9. Task 9, because documentation must only be updated after verified implementation.

## Acceptance Criteria

- `auto_draft` trace includes `draft_verifier` before `compose_draft`.
- The graph can refine at least once when verifier finds uncovered critical fields.
- Refinement has a configurable upper bound and cannot loop indefinitely.
- `auto_draft` treats the LLM as the reviewer substitute: verifier feedback may trigger bounded search refinement or low-confidence `suggested` fallback values.
- `guided_confirmation` treats the human as the reviewer: verifier feedback must appear in confirmation/ASK_USER flow and must not be silently resolved by model fallback.
- `quality_report` is stored in `PWPSState` and persisted as `quality_report.json`.
- `field_reasoning` receives enough structured context to map evidence to target pWPS fields.
- Web/model-derived values remain `candidate` or `suggested`, never formal conclusions.
- Blocked project metadata cannot be filled by model fallback or web inference.
- Main draft includes a quality summary and no longer dumps every ordinary missing metadata field into the primary risk section.
- The live smoke command produces an auditable partial draft with better field coverage and an explicit quality status.

## Non-Goals

- Do not implement a welding rule engine.
- Do not claim compliance, qualification coverage, or approval readiness.
- Do not add a relational database.
- Do not require local proprietary standards to pass tests.
- Do not remove existing `guided_confirmation` behavior.
- Do not collapse the two interaction modes into one behavior; auto and guided share contracts but not the reviewer actor.
- Do not make social/web snippets look like verified standard facts.

## Self-Review

- Spec coverage: covers self-verification loop, evidence quality, field coverage, bounded refinement, controlled fallback, synthesis, persistence, verification, and mode-specific reviewer roles.
- Placeholder scan: no intentional placeholder markers remain; exact files and commands are listed.
- Type consistency: quality models use serializable Pydantic objects and merge as dictionaries in `PWPSState`.
- Scope check: this is one coherent subsystem: draft quality loop. It touches graph, verifier, evidence, reasoning, rendering, guided confirmation, and docs, but all changes serve the same quality-review behavior with mode-specific actor binding.
