# Stage One Completion Roadmap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the current runnable pWPS draft prototype into a coherent stage-one Agent runtime with graph-first execution, real LLM Supervisor control, guided multi-turn confirmation, supplemental updates, local document retrieval, and reproducible smoke verification.

**Architecture:** Use LangGraph as the production orchestration boundary and keep `PWPSState` as the source of truth. LLM Supervisor planning should choose structured `AgentAction` values, while runtime tools remain narrow, testable, and schema-validated. Each phase below should land as a working increment with focused tests and progress-document updates.

**Tech Stack:** Python 3.14, Pydantic v2, LangGraph, LangChain structured output, pytest through `uv`, stdlib local Web UI/API for the current guided-confirmation slice.

---

## Current Baseline

The current repository already has:

- Runnable `auto_draft` vertical slice.
- Structured LLM-backed tools for requirement understanding, knowledge planning, and field reasoning.
- Real web search provider integration with caching/retry behavior.
- Evidence conversion, field merge priority rules, Markdown draft rendering, field report rendering, trace persistence, and `evidence_index.json`.
- LangGraph action loop with deterministic planning, tool routing, retry/timeout handling, checkpoint/resume helpers, and injectable planner support.
- First guided-confirmation slice with grouped view, user confirmations, edit/rollback history, CLI commands, graph `ASK_USER` pause, graph-backed resume, and lightweight local Web UI/API.

Verified baseline:

```text
uv run pytest -q
64 passed, 1 warning
```

## Completion Strategy

Do not try to finish all remaining work in one branch. Execute the phases in order. Each phase should end with:

```text
uv run pytest -q
uv run python -m compileall -q src tests
git diff --check
```

When a phase changes project status, update:

- The phase plan under `docs/superpowers/plans/`.
- The `Current Implementation Progress` section in `AGENTS.md`.

## Phase 1: Make LangGraph The Production Auto-Draft Runtime

> **Status:** Completed. `pwps-agent auto-draft` now routes through a graph-backed `run_graph_auto_draft()` service by default; the older linear `run_auto_draft()` remains available for compatibility and legacy workflow tests.

**Goal:** Make `pwps-agent auto-draft` run through the graph runtime by default instead of the older linear workflow.

**Why first:** The project architecture says LangGraph is the runtime boundary. Until CLI/API use the graph path, later Supervisor and multi-turn work will remain split across two execution models.

**Primary files:**

- Modify: `src/pwps_agent/cli.py`
- Modify: `src/pwps_agent/graph/builder.py`
- Modify: `src/pwps_agent/graph/state.py`
- Modify: `src/pwps_agent/workflows/auto_draft.py`
- Test: `tests/test_cli.py`
- Test: `tests/test_graph_auto_draft.py`
- Test: `tests/test_auto_draft_workflow.py`

**Work items:**

- [x] Add a graph-backed `run_graph_auto_draft()` application service or equivalent wrapper.
- [x] Route `pwps-agent auto-draft` to the graph-backed path by default.
- [x] Keep the linear `run_auto_draft()` only as compatibility/test support, or remove it after all callers are migrated.
- [x] Preserve existing output files: `pwps.json`, `pwps_draft.md`, `field_report.json`, `trace.json`, `evidence_index.json`.
- [x] Add CLI regression coverage proving the command uses graph semantics, including supervisor action trace entries.
- [x] Update progress docs after verification passes.

**Acceptance gates:**

```text
uv run pytest tests/test_cli.py tests/test_graph_auto_draft.py tests/test_auto_draft_workflow.py -q
uv run pytest -q
uv run python -m compileall -q src tests
git diff --check
```

**Manual smoke:**

```text
uv run pwps-agent auto-draft "Q355B 12mm plate GMAW butt joint flat AWS D1.1 pWPS draft" --output-dir /tmp/pwps-agent-smoke --run-id graph_default_smoke
```

Expected:

```text
/tmp/pwps-agent-smoke/graph_default_smoke
```

The output directory must contain all required artifacts and graph Supervisor trace entries.

Verification:

```text
uv run pytest tests/test_cli.py tests/test_graph_auto_draft.py tests/test_auto_draft_workflow.py -q
9 passed, 1 warning

uv run pytest -q
66 passed, 1 warning

uv run python -m compileall -q src tests
passed

git diff --check
passed with no output
```

## Phase 2: Promote LLM Supervisor Planning From Seam To Runtime Option

> **Status:** Completed. `SUPERVISOR_PLANNER=deterministic|llm` is now loaded from config, graph auto-draft injects `LLMSupervisorPlanner` in `llm` mode, Supervisor trace records planner mode, and unsupported LLM-selected graph actions/tools are rejected before routing.

**Goal:** Make `LLMSupervisorPlanner` usable from CLI/config while preserving deterministic planner support for tests.

**Why second:** Once graph is the default runtime, the next architectural gap is that the Supervisor is still mostly deterministic by default.

**Primary files:**

- Modify: `src/pwps_agent/config.py`
- Modify: `src/pwps_agent/cli.py`
- Modify: `src/pwps_agent/graph/supervisor.py`
- Modify: `src/pwps_agent/graph/state.py`
- Modify: `src/pwps_agent/agent/prompt_loader.py`
- Test: `tests/test_graph_supervisor_planner.py`
- Test: `tests/test_cli.py`
- Possibly create: `tests/test_supervisor_runtime_selection.py`

**Work items:**

- [x] Add config for Supervisor planner mode, for example `SUPERVISOR_PLANNER=deterministic|llm`.
- [x] Wire CLI/runtime dependency construction so `llm` mode uses `LangChainStructuredClient`.
- [x] Expand `LLMSupervisorPlanner` prompt payload to include enough state for safe action choice: pending action, recent trace summaries, current risks, missing fields, confirmations, and available tools.
- [x] Keep available actions constrained to implemented graph actions only.
- [x] Add validation for unsupported tool/action combinations.
- [x] Add deterministic fake-client tests for LLM planner runtime selection.
- [x] Add trace assertions that planner mode and selected domain-skill context are recorded.

**Acceptance gates:**

```text
uv run pytest tests/test_graph_supervisor_planner.py tests/test_cli.py -q
uv run pytest -q
uv run python -m compileall -q src tests
git diff --check
```

**Manual smoke:**

```text
SUPERVISOR_PLANNER=deterministic uv run pwps-agent auto-draft "Q355B 12mm plate GMAW butt joint flat AWS D1.1 pWPS draft" --output-dir /tmp/pwps-agent-smoke --run-id deterministic_graph_smoke
```

For live LLM smoke, use the configured `.env` provider only after tests pass:

```text
SUPERVISOR_PLANNER=llm uv run pwps-agent auto-draft "Q355B 12mm plate GMAW butt joint flat AWS D1.1 pWPS draft" --output-dir /tmp/pwps-agent-smoke --run-id llm_supervisor_smoke
```

Verification:

```text
uv run pytest tests/test_config.py tests/test_graph_supervisor_planner.py tests/test_graph_auto_draft.py tests/test_cli.py -q
15 passed, 1 warning

uv run pytest -q
69 passed, 1 warning

uv run python -m compileall -q src tests
passed

git diff --check
passed with no output
```

## Phase 3: Add Active Domain Skill Selection And Traceable Skill Use

> **Status:** Completed. `USE_DOMAIN_SKILL` is now a graph action with routing, stateful active-skill tracking, domain-skill history, trace payloads, skill-name validation, and active skill context injection into LLM Supervisor prompts.

**Goal:** Let the Supervisor explicitly select and record Domain Skill context instead of always using a fixed bundle.

**Why third:** Domain Skills are a first-class architecture concept. The runtime should show which skill guidance was used and why.

**Primary files:**

- Modify: `src/pwps_agent/graph/supervisor.py`
- Modify: `src/pwps_agent/graph/router.py`
- Modify: `src/pwps_agent/graph/nodes.py`
- Modify: `src/pwps_agent/core/state.py`
- Modify: `src/pwps_agent/core/contracts.py`
- Test: `tests/test_domain_skills.py`
- Test: `tests/test_graph_supervisor_planner.py`

**Work items:**

- [x] Add state fields for active domain skills or skill-use history.
- [x] Implement `USE_DOMAIN_SKILL` routing as a real graph action.
- [x] Validate requested skill names through `prompt_loader`.
- [x] Record skill name, rationale, and loaded context identifier in trace.
- [x] Include active skill context in subsequent LLM Supervisor prompts.
- [x] Add tests for valid skill selection, invalid skill rejection, and trace payload shape.

**Acceptance gates:**

```text
uv run pytest tests/test_domain_skills.py tests/test_graph_supervisor_planner.py -q
uv run pytest -q
uv run python -m compileall -q src tests
git diff --check
```

Verification:

```text
uv run pytest tests/test_domain_skills.py tests/test_graph_supervisor_planner.py -q
10 passed, 1 warning

uv run pytest -q
73 passed, 1 warning

uv run python -m compileall -q src tests
passed

git diff --check
passed with no output
```

## Phase 4: Complete Guided Confirmation As A Durable Multi-Turn Runtime

**Goal:** Move guided confirmation from first interaction slice to durable graph-backed live session flow.

**Why fourth:** The current guided flow can pause/resume and render a local UI, but it is still state-file backed and not a durable session loop.

**Primary files:**

- Modify: `src/pwps_agent/workflows/guided_confirmation.py`
- Modify: `src/pwps_agent/web/guided_confirmation.py`
- Modify: `src/pwps_agent/graph/checkpoints.py`
- Modify: `src/pwps_agent/graph/builder.py`
- Modify: `src/pwps_agent/graph/nodes.py`
- Test: `tests/test_guided_confirmation.py`
- Test: `tests/test_guided_confirmation_resume.py`
- Test: `tests/test_guided_confirmation_web.py`
- Test: `tests/test_graph_guided_confirmation.py`

**Work items:**

- [ ] Store live guided-confirmation pause points as checkpoints, not only ad hoc state files.
- [ ] Add resume-by-run-id behavior using latest checkpoint.
- [ ] Let the graph return to Supervisor after user confirmation instead of always jumping directly to compose/finish.
- [ ] Support repeated confirmation groups across multiple turns.
- [ ] Preserve edit/rollback history across checkpoint reloads.
- [ ] Add Web/API tests for resume from checkpoint and second confirmation turn.
- [ ] Add CLI smoke commands for run-id based guided resume.

**Acceptance gates:**

```text
uv run pytest tests/test_guided_confirmation.py tests/test_guided_confirmation_resume.py tests/test_guided_confirmation_web.py tests/test_graph_guided_confirmation.py -q
uv run pytest -q
uv run python -m compileall -q src tests
git diff --check
```

## Phase 5: Implement Supplement Update As A First-Class Graph Mode

**Goal:** Let users add information during or after a run, merge it into `PWPSState`, and regenerate affected outputs without restarting.

**Why fifth:** Stage one explicitly requires supplemental information at any time. Current code has state service coverage, but not a full graph/CLI/API workflow.

**Primary files:**

- Modify: `src/pwps_agent/core/modes.py`
- Modify: `src/pwps_agent/cli.py`
- Modify: `src/pwps_agent/graph/router.py`
- Modify: `src/pwps_agent/graph/nodes.py`
- Modify: `src/pwps_agent/workflows/guided_confirmation.py`
- Possibly create: `src/pwps_agent/workflows/supplement_update.py`
- Test: `tests/test_modes.py`
- Test: `tests/test_cli.py`
- Possibly create: `tests/test_graph_supplement_update.py`

**Work items:**

- [ ] Add CLI command for applying supplemental text to a saved state or run checkpoint.
- [ ] Add graph action/node for supplement parsing and state patch merge.
- [ ] Reuse `requirement_understanding` for supplement extraction where appropriate.
- [ ] Re-evaluate affected fields through `field_reasoning` when evidence or core fields change.
- [ ] Re-compose draft/report after supplement merge.
- [ ] Add tests for supplement during `auto_draft`, during `need_user_input`, and after completed draft.

**Acceptance gates:**

```text
uv run pytest tests/test_modes.py tests/test_cli.py tests/test_graph_supplement_update.py -q
uv run pytest -q
uv run python -m compileall -q src tests
git diff --check
```

## Phase 6: Add Local Document Retrieval Provider

**Goal:** Implement local document retrieval as a real knowledge source alongside web search.

**Why sixth:** The architecture and stage-one goals require local documents plus web references. Current implementation mostly covers web.

**Primary files:**

- Create: `src/pwps_agent/knowledge/local_doc_provider.py`
- Create: `src/pwps_agent/tools/local_doc_search.py`
- Modify: `src/pwps_agent/config.py`
- Modify: `src/pwps_agent/graph/supervisor.py`
- Modify: `src/pwps_agent/graph/nodes.py`
- Modify: `src/pwps_agent/tools/evidence.py`
- Create: `tests/fixtures/local_docs/`
- Create: `tests/test_local_doc_provider.py`
- Create: `tests/test_local_doc_search.py`
- Modify: `tests/test_graph_auto_draft.py`

**Work items:**

- [ ] Define a simple local document result schema using existing `SearchResult`/`Evidence` contracts where possible.
- [ ] Index or scan small deterministic fixture documents under `tests/fixtures/local_docs/`.
- [ ] Implement keyword/BM25-style retrieval without adding a database dependency.
- [ ] Convert local snippets into evidence with `source_type="local_doc"`.
- [ ] Let knowledge planning target `local_doc`, `web`, or both.
- [ ] Add graph tool routing for `local_doc_search`.
- [ ] Add tests proving local evidence links to fields and appears in `evidence_index.json`.

**Acceptance gates:**

```text
uv run pytest tests/test_local_doc_provider.py tests/test_local_doc_search.py tests/test_graph_auto_draft.py -q
uv run pytest -q
uv run python -m compileall -q src tests
git diff --check
```

## Phase 7: Split Section Generation And Risk Review Into Explicit Tools

**Goal:** Make A/B/C/D/E section generation and risk report generation explicit runtime tools instead of only renderer behavior.

**Why seventh:** Current rendering is useful, but the architecture expects traceable generation/reporting actions with uncertainty and risk semantics.

**Primary files:**

- Create: `src/pwps_agent/tools/section_generation.py`
- Create: `src/pwps_agent/tools/risk_report.py`
- Modify: `src/pwps_agent/render/markdown.py`
- Modify: `src/pwps_agent/graph/supervisor.py`
- Modify: `src/pwps_agent/graph/nodes.py`
- Modify: `configs/prompts/`
- Create: `configs/prompts/section_generation.md`
- Create: `configs/prompts/risk_report.md`
- Create: `tests/test_section_generation.py`
- Create: `tests/test_risk_report.py`
- Modify: `tests/test_render.py`

**Work items:**

- [ ] Add Pydantic schemas for section generation output and risk report output.
- [ ] Keep field status/source/evidence/confidence visible in generated sections.
- [ ] Keep project metadata blank or `待确认` when not user-provided.
- [ ] Add graph actions for `GENERATE_REPORT` and section generation where needed.
- [ ] Persist generated sections and risk report in `PWPSState`.
- [ ] Keep Markdown renderer as a pure formatter over structured state.
- [ ] Add tests for missing-field risks, low-confidence evidence, thermal/PWHT risk notes, and web-reference-only wording.

**Acceptance gates:**

```text
uv run pytest tests/test_section_generation.py tests/test_risk_report.py tests/test_render.py -q
uv run pytest -q
uv run python -m compileall -q src tests
git diff --check
```

## Phase 8: Add End-To-End Smoke Harness And Sample Runs

**Goal:** Make it easy to verify the whole system with deterministic fixtures and optional live provider smoke tests.

**Why eighth:** The project now has many slices; a reproducible smoke harness prevents regressions and makes demos repeatable.

**Primary files:**

- Create: `scripts/smoke_auto_draft.py`
- Create: `scripts/smoke_guided_confirmation.py`
- Create: `docs/smoke-testing.md`
- Create: `tests/test_smoke_scripts.py`
- Possibly create: `tests/fixtures/sample_states/`

**Work items:**

- [ ] Add a deterministic no-network smoke using fake clients/providers.
- [ ] Add optional live smoke commands documented separately and guarded by `.env` availability.
- [ ] Save representative output paths under `/tmp`, not in repo.
- [ ] Validate required artifacts exist and contain expected high-level keys.
- [ ] Document DeepSeek/OpenAI-compatible structured-output environment settings.

**Acceptance gates:**

```text
uv run pytest tests/test_smoke_scripts.py -q
uv run pytest -q
uv run python -m compileall -q src tests
git diff --check
```

## Phase 9: Production Hardening Pass

**Goal:** Clean up runtime boundaries, errors, observability, docs, and user-facing behavior for a stage-one handoff.

**Why last:** Hardening is most useful after the runtime shape stabilizes.

**Primary files:**

- Modify: `src/pwps_agent/config.py`
- Modify: `src/pwps_agent/cli.py`
- Modify: `src/pwps_agent/web/guided_confirmation.py`
- Modify: `docs/architecture.md`
- Modify: `docs/agent_design.md`
- Modify: `docs/requirements.md`
- Modify: `AGENTS.md`
- Add targeted tests as needed.

**Work items:**

- [ ] Normalize error messages for missing `.env`, web provider auth failure, LLM structured-output failure, and bad state files.
- [ ] Ensure every failure leaves a trace record and, when possible, a persisted failed state.
- [ ] Add config documentation for all runtime knobs.
- [ ] Add user-facing CLI help examples.
- [ ] Review docs so they describe actual current behavior, not only target architecture.
- [ ] Run full verification and a live smoke if credentials are available.

**Acceptance gates:**

```text
uv run pytest -q
uv run python -m compileall -q src tests
git diff --check
```

Optional live smoke:

```text
uv run pwps-agent auto-draft "Q355B 12mm plate GMAW butt joint flat AWS D1.1 pWPS draft" --output-dir /tmp/pwps-agent-stage-one --run-id final_stage_one_smoke
```

## Suggested Commit Boundaries

Use one commit per phase unless a phase is too large. If a phase grows beyond one day of work, split by tested vertical increment:

```text
feat: route auto draft through graph runtime
feat: enable llm supervisor planner mode
feat: record domain skill selection in graph
feat: support durable guided confirmation sessions
feat: add graph supplement update flow
feat: add local document retrieval
feat: add section generation and risk review tools
test: add stage one smoke harness
docs: harden stage one runtime documentation
```

## Recommended Execution Order

1. Phase 1, because it removes the biggest architectural split.
2. Phase 2, because it makes the LLM Supervisor real in the runtime path.
3. Phase 3, because active Domain Skill selection depends on Supervisor planning.
4. Phase 4, because multi-turn guided confirmation depends on graph-first runtime.
5. Phase 5, because supplement update needs the same durable state/session model.
6. Phase 6, because local document retrieval expands evidence sources without changing session semantics.
7. Phase 7, because section/risk generation is easier once evidence and state are stable.
8. Phase 8, because smoke harness should cover the real completed flows.
9. Phase 9, because documentation and hardening should reflect the final stage-one behavior.

## Done Definition For Stage One

Stage one can be considered complete when:

- `pwps-agent auto-draft` uses LangGraph by default.
- LLM Supervisor planner can be enabled through config and emits structured `AgentAction`.
- Domain Skill use is selected or recorded in trace.
- `guided_confirmation` supports durable multi-turn pause/resume.
- `supplement_update` can merge user input without restarting a run.
- Both local docs and web search can contribute evidence.
- Draft sections and risk reports are generated from structured state with uncertainty preserved.
- All required artifacts are persisted for every successful run.
- Failed or interrupted runs leave debuggable trace/checkpoint state.
- Full tests, compileall, diff check, and at least one smoke run pass.
