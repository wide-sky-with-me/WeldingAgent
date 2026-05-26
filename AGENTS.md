# AGENTS.md

This file guides Codex or other AI coding agents working on the pWPS project.

**⚠️ Start here**: [.instructions.md](.instructions.md) and [.agent.md](.agent.md) for development guidelines and current goals.

## Project Overview

This repository implements a first-stage **LLM-centric pWPS draft generation Agent**.

The system is not a rule engine and not a multi-agent expert committee. The first-stage architecture is:

```text
LLM Supervisor Agent + Domain Skills + Runtime Tools + PWPSState + Knowledge Provider
```

The LLM Supervisor is the main actor. It reads the current state, follows domain skills for task guidance, calls runtime tools for concrete operations, interprets results, updates state, and eventually produces a pWPS draft plus field/source/risk reports.

In this repository, **Domain Skills** are guidance and experience packages for the LLM, not LangGraph subflows and not ordinary Python tool functions. Runtime tools execute concrete operations. LangGraph subflows organize interaction modes and state transitions.

The system currently targets draft generation only. Do not claim that outputs are formal, compliant, or ready for signing.

## Core Design Principles

1. LLM Supervisor is the workflow protagonist.
2. Domain Skills guide the Supervisor with domain workflows, field semantics, risk rules, and interaction patterns; they are not independent decision-makers.
3. Runtime Tools provide executable capabilities such as search, parsing, rendering, persistence, and field-state merging.
4. LangGraph is used for stateful execution, replay, checkpoints, routing, and interaction-mode subflows.
5. PWPSState is the source of truth; important information must not live only in chat text.
6. Schema and contracts constrain data shape, not welding business decisions.
7. Do not build a hard-coded welding rule engine in stage one.
8. Knowledge Provider is a black box. It currently uses local docs and web search; future implementations may use databases.
9. Every generated field must carry source, evidence, confidence, and status when possible.
10. Web and LLM-derived values must be marked as reference/candidate/suggested, not formal conclusions.
11. Project metadata such as customer name, contract number, project name, reviewer, or approver must not be invented.

## Development Workflow

⚠️ **See `.instructions.md` for comprehensive development guidelines.**

Key points:
- State First: PWPSState is the single source of truth
- Preserve Uncertainty: Mark all values with source + confidence metadata
- Centralize Prompts: production prompts must be managed under `configs/prompts/` or Domain Skill markdown files with clear notes about purpose, mode, and expected structured-output contract; do not scatter prompt text inside runtime code.
- Runtime code may assemble structured state payloads for user prompts, but model role, task-boundary, mode behavior, safety wording, and output expectations belong in centralized prompt/Domain Skill files.
- Document Changes: Update this section after completion with verification details
- Clean Code: Remove dead code, debug output, temp scaffolding before committing
- Test Always: Full test suite + smoke test before marking done

## Current Stage

**Stage One**: Autonomous draft generation with human-in-the-loop confirmation.

**Goals (✅ DONE):**
- Accept natural-language welding requirement → structured draft
- Support `auto_draft` mode (autonomous with visible uncertainty)
- Support `guided_confirmation` mode (human confirmation with evidence)
- Support `supplement_update` (add info at any time, re-evaluate)
- Search local documents and web sources
- Use LLM reasoning to convert evidence → candidates
- Generate A/B/C/D/E pWPS draft sections
- Produce field/source/risk reports
- Save complete trace for debugging

**Out of scope:**
- Full welding standards rule engine
- Local relational database
- PQR/WPQR qualification validation
- Formal approval workflow
- Expert sign-off
- Guaranteed compliance

## Current Implementation Progress

As of 2026-05-25:

**Graph Runtime**
- LangGraph auto-draft and guided-confirmation action loops ✅
- LLM Supervisor with structured AgentAction planning ✅
- Loop protection for repeated actions ✅
- Checkpoint/resume system ✅

**Core Tools**
- requirement_understanding (LLM-backed) ✅
- knowledge_planning (model-planned queries) ✅
- knowledge_planning falls back to a targeted deterministic query when a remote provider structured-output parser error occurs, while preserving the parser error in `ToolResult.errors` ✅
- web_search (Tavily + Brave, caching, retry logic) ✅
- local_doc_search (markdown/text retrieval) ✅
- field_reasoning (evidence → candidates) ✅
- field_reasoning no longer uses deterministic welding-content keyword fallback; empty LLM output leaves fields missing unless explicit model fallback is enabled ✅
- section_generation (A/B/C/D/E structured output) ✅
- risk_report (missing fields, thermal/qualification flags) ✅

**Interaction Modes**
- auto_draft (autonomous with candidates/suggestions/missing) ✅
- auto_draft initial information gate pauses inside the graph with a transport-neutral interaction request when minimum core fields are missing ✅
- auto_draft initial gate remains active after requirement understanding when the extracted state still lacks minimum startup fields, and closes once retrieval/reasoning has started ✅
- guided_confirmation (pause/confirm/evidence/history) ✅
- guided_confirmation option recommendation keeps key choices in need-confirmation until explicit user confirmation ✅
- guided_confirmation policy prevents empty user pauses: if no candidate/missing/confirmation content exists, premature `ASK_USER` or `guided_options` actions are routed back to evidence planning/reasoning ✅
- Runtime interaction state is stored in `PWPSState.pending_interaction` / `interaction_requests`; terminal, Web, and API inputs should act as adapters for the same `ASK_USER` pause shape ✅
- Generic `interaction-resume` reuses normal draft runtime dependency construction when dependencies are not injected, so CLI resume can continue through real LLM/search-backed graph execution ✅
- Interactive terminal runs of `draft`, `auto-draft`, and `guided-draft` now consume the same `pending_interaction` pause shape inline: the CLI prints questions/recommendations, blocks for user input when `stdin.isatty()`, resumes through `resume_interaction()`, and continues the graph in the same process ✅
- supplement_update (patch state, re-evaluate) ✅

**Persistence & Artifacts**
- pwps.json (structured state) ✅
- pwps_draft.md (Markdown output) ✅
- field_report.json (fields + evidence + risks) ✅
- trace.json (complete action history) ✅
- evidence_index.json (evidence ↔ field mappings) ✅
- quality_report.json (draft quality verification) ✅
- agent_metrics.json (field status, override, confirmation, weak-evidence metrics) ✅

**Domain Skills & Guidance**
- pwps_auto_draft.md (autonomous draft guidance) ✅
- pwps_guided_confirmation.md (confirmation interaction) ✅
- pwps_evidence_handling.md (uncertainty classification) ✅
- pwps_risk_review.md (risk flagging) ✅
- `configs/prompts/README.md` documents the production prompt registry and the boundary between centralized prompt text and runtime state payloads ✅

**Active Hardening Plan**
- `docs/superpowers/plans/2026-05-25-llm-led-dual-mode-hardening.md` is the active plan.
- The LLM Supervisor remains the main actor.
- `auto_draft` should only ask at the beginning when minimum core fields are missing.
- `guided_confirmation` should recommend options and require human confirmation for key choices.
- Implemented hardening: initial information gates, transport-neutral runtime interaction requests, generic interaction resume, centralized Supervisor prompts, publishability/state separation, evidence policy, guided options, Supervisor policy extraction, and agent eval metrics.

**Recent Verification**

```bash
uv run pytest -q
159 passed

uv run pytest tests/test_interaction_gates.py tests/test_publishability.py tests/test_evidence_policy.py tests/test_guided_options.py tests/test_eval_metrics.py -q
11 passed

uv run pytest tests/test_graph_auto_draft.py tests/test_graph_guided_confirmation.py tests/test_graph_supervisor_planner.py tests/test_guided_confirmation.py tests/test_guided_confirmation_resume.py -q
43 passed

uv run pytest tests/test_interaction_gates.py tests/test_graph_auto_draft.py tests/test_graph_supervisor_planner.py -q
35 passed

uv run pytest -q
170 passed

uv run pytest -q
172 passed

uv run pytest tests/test_graph_supervisor_planner.py tests/test_graph_guided_confirmation.py tests/test_guided_confirmation_resume.py -q
30 passed

uv run pytest tests/test_knowledge_planning.py tests/test_interaction_resume.py -q
6 passed

uv run pytest tests/test_interaction_resume.py tests/test_cli.py::test_cli_parser_accepts_generic_interaction_resume -q
3 passed

uv run pytest tests/test_interaction_gates.py tests/test_interaction_resume.py tests/test_graph_guided_confirmation.py tests/test_graph_supervisor_planner.py -q
26 passed

uv run pytest tests/test_cli.py -q
18 passed

uv run pytest tests/test_guided_confirmation_resume.py tests/test_guided_confirmation_web.py tests/test_guided_confirmation.py -q
15 passed

uv run pytest tests/test_graph_auto_draft.py tests/test_evidence_reasoning.py tests/test_cli.py -q
33 passed

uv run python -m compileall -q src tests
passed

git diff --check
passed with no output

LLM_API_KEY=stub LLM_BASE_URL=http://127.0.0.1:18080/v1 LLM_MODEL=stub KNOWLEDGE_SOURCES=model uv run pwps-agent auto-draft ... --output-dir /tmp/pwps-agent-e2e-hardening --run-id auto_dual_mode_hardening
/tmp/pwps-agent-e2e-hardening/auto_dual_mode_hardening ✅
pwps.json: status=done; draft includes ER50-6, 80% Ar / 20% CO2, DCEP, 180-260 A, 22-28 V, 180-350 mm/min, heat input, preheat, interpass, and PWHT draft values

LLM_API_KEY=stub LLM_BASE_URL=http://127.0.0.1:18080/v1 LLM_MODEL=stub KNOWLEDGE_SOURCES=model uv run pwps-agent guided-draft ... --run-id guided_dual_mode_hardening3
status=need_user_input; guided_options generated recommendations for key fields

uv run pwps-agent guided-confirm-resume /tmp/pwps-agent-e2e-hardening/guided_dual_mode_hardening3/pwps.json ...
/tmp/pwps-agent-e2e-hardening/guided_dual_mode_hardening3 ✅
pwps.json: status=done; user_confirmed=12; remaining candidate/suggested/need_confirmation/conflict=0; quality report refreshed after confirmation

uv run pwps-agent auto-draft "Q355B 12mm GMAW" --output-dir /tmp/smoke --run-id verify1
/tmp/smoke/verify1 ✅
pwps.json: status=done, fields=7 filled + 18 missing
trace: 5 supervisor actions, 3 web queries, full completion
```

## Architecture Overview

High-level:

```
graph/              LangGraph runtime (nodes, routing, checkpoints)
agent/              LLM Supervisor (planner, reasoning, structured output)
tools/              Runtime tools (search, reasoning, rendering, persistence)
core/               Contracts, field state, merging logic
knowledge/          Local docs + web search providers
render/             Markdown draft and report rendering
domain_skills/      Guidance markdown for the Supervisor
configs/
  ├── prompts/      Prompt texts (never hardcode in code!)
  └── agent.yaml    Configuration templates
```

See `docs/architecture.md` for detailed module breakdown.

## pWPS Field Structure

Output organized into sections:

```
A. File and project metadata
B. Welding applicability scope
C. Filler and auxiliary materials
D. Welding parameters
E. Thermal control and heat treatment
```

Core input fields:
- applicable_standard
- base_material
- thickness/wall_thickness
- workpiece_type
- diameter (when pipe/tube)
- welding_process
- joint_type
- welding_position

## Output Files

Each run produces:

```
<output_dir>/<run_id>/
├── pwps.json              (state)
├── pwps_draft.md          (Markdown)
├── field_report.json      (fields + evidence + risks)
├── trace.json             (action history)
├── evidence_index.json    (evidence ↔ field mappings)
└── checkpoints/           (resume points)
    ├── 0.json
    ├── 1.json
    └── latest.json
```

## Development

**Test baseline**
```bash
uv run pytest -q
142 passed
```

**Smoke test**
```bash
uv run pwps-agent auto-draft "Q355B 12mm GMAW butt joint flat" \
  --output-dir /tmp/smoke --run-id test1
```

**Full verification**
```bash
uv run pytest -q && \
uv run python -m compileall -q src tests && \
git diff --check
```

## Documentation Index

- `.instructions.md` - Development guidelines (START HERE)
- `.agent.md` - Current goals and priorities
- `docs/README.md` - Documentation navigation
- `docs/architecture.md` - Module responsibilities and architecture
- `docs/agent_design.md` - LLM Supervisor reasoning
- `docs/data_schema.md` - State and contract models
- `docs/requirements.md` - Original Stage One requirements
- `docs/superpowers/plans/` - Completed phase documentation (archive)

## Important Notes

- **Do not** modify existing Pydantic contracts without updating all dependent code
- **Do not** add features without updating Domain Skills guidance
- **Do not** skip trace logging
- **Do not** invent project metadata (customer name, contract #, etc.)
- **Always** mark uncertain values with source + confidence
- **Always** preserve evidence links in field_report
- **Always** run full verification before committing

---

Last updated: 2026-05-25
