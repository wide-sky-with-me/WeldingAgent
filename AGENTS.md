# AGENTS.md

This file guides Codex or other AI coding agents working in this repository.

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

## Agent Working Rules

- When a task is completed, update the relevant progress document in the same turn. For implementation work, this usually means updating the applicable file under `docs/superpowers/plans/` and, when the overall project status changes, the `Current Implementation Progress` section in this file.
- When the user says an instruction or design decision should be remembered for this project, record it in `AGENTS.md`; do not leave important project rules only in chat history.
- Keep progress updates evidence-based: include the verification command, result, and any live smoke output path when relevant.
- Do not mark a task complete in progress docs until the implementation and verification have actually run.
- After each work cycle, clean up obvious junk code, temporary assertions, dead test scaffolding, unused imports, and accidental debug output before verification and commit.

## Current Stage

Stage one goals:

- Accept a natural-language welding requirement.
- Let the LLM Supervisor extract core pWPS fields.
- Support `auto_draft` mode: user provides minimum input, the model drafts the rest as candidate/suggested values with risks.
- Support `guided_confirmation` mode: the system discusses field groups with the user, gives recommendations and explanations, and only promotes user-confirmed fields after confirmation.
- Let users add supplemental information at any time and merge it into `PWPSState` without restarting the run.
- Search local documents and web sources for similar pWPS/WPS references.
- Use LLM reasoning to convert evidence into field candidates.
- Generate A/B/C/D/E pWPS draft sections.
- Produce field source, missing-field, and risk reports.
- Save trace for debugging and replay.

Out of scope for stage one:

- Full welding standards rule engine.
- Local relational database dependency.
- PQR/WPQR qualification coverage validation.
- Formal approval workflow.
- Expert sign-off.
- Guaranteed compliance.

## Current Implementation Progress

As of 2026-05-25, the repository has a runnable `auto_draft` vertical slice and a minimal LangGraph auto-draft action loop:

- Core Pydantic contracts and initial `PWPSState` are implemented.
- Provider-neutral `.env` loading is implemented for LLM, web search, and runtime paths.
- Prompt text is centrally managed under `configs/prompts/`.
- LLM-backed tools use structured output through Pydantic schemas; production code should prefer LangChain `with_structured_output(PydanticModel)`.
- The default runtime LLM adapter is `LangChainStructuredClient`, configured with OpenAI-compatible `LLM_API_KEY`, `LLM_BASE_URL`, and `LLM_MODEL`.
- DeepSeek V4 structured-output smoke testing passed with `LLM_THINKING_TYPE=disabled` and `LLM_STRUCTURED_OUTPUT_METHOD=function_calling`.
- `requirement_understanding`, `knowledge_planning`, and `field_reasoning` are LLM-backed and schema-validated.
- `knowledge_planning` generates targeted model-planned queries instead of fixed query templates.
- `auto_draft` runs requirement extraction, query planning, real web search, evidence conversion, field reasoning, Markdown rendering, field report rendering, trace persistence, and output persistence.
- `graph/` now contains the first LangGraph runtime slice: LLM Supervisor action planning, action routing, runtime tool execution, draft composition, finish handling, and injectable graph dependencies for tests/resume flows.
- `pwps-agent auto-draft` now routes through the graph-backed `run_graph_auto_draft()` service by default; the older linear `run_auto_draft()` remains available for compatibility and legacy workflow tests.
- The graph Supervisor now uses `LLMSupervisorPlanner` by default to request structured `AgentAction` output from an LLM with Domain Skill context; `SUPERVISOR_PLANNER` is not an exposed runtime setting.
- Supervisor action trace now records planner mode, and unsupported LLM-selected graph actions/tools are rejected before routing with failed-state finish behavior.
- LLM Supervisor planning now has loop protection for repeated completed actions and invalid interruptions: if the model requests a completed tool/domain-skill/report/draft step, or asks the user in `auto_draft`, the Supervisor records an override trace event and advances through the safe next action instead of relying on LangGraph's recursion limit.
- CLI auto-draft now emits structured runtime logs to stderr for run start, graph construction, Supervisor actions, tool events, overrides, and completion; the known upstream LangGraph/LangChain `allowed_objects` pending-deprecation warning is narrowly filtered at package import.
- `USE_DOMAIN_SKILL` is now a graph action: active domain skills and skill-use history are stored in `PWPSState`, requested skill names are validated through the prompt loader, selections are traceable, and active skill context is injected into later LLM Supervisor prompts.
- The graph runtime now has retry-aware post-tool routing, tool exception capture, failed-result handling, and failed-state-preserving finish behavior.
- Web search execution in the graph supports multiple planned queries through a bounded thread pool, per-query timeout handling, partial-success trace records, and per-query error/timeout trace events.
- Knowledge sources are now configurable through `KNOWLEDGE_SOURCES` as an ordered source list, for example `local_doc,web` or `web,model`. Local retrieval can be disabled when no local knowledge base exists; mixed `local_doc` plus `web` planned queries now still execute web search; model fallback can only produce `suggested` fields that require confirmation.
- Default working mode is configurable through `PWPS_INTERACTION_MODE=auto_draft|guided_confirmation` and used by `pwps-agent draft`; explicit `auto-draft` and `guided-draft` CLI commands remain per-run overrides.
- Local document retrieval scans configured markdown/text files, ranks matching snippets, and emits `local_doc` search results and evidence through the graph `local_doc_search` tool when enabled.
- Web search providers now support instance-level query caching plus configurable transient-error retry/backoff, while avoiding retries for non-transient authorization failures.
- Evidence converted from web search now includes source-tier and confidence metadata, classifying references as official-standard, textbook, or webpage tier while preserving candidate/reference-only semantics.
- Run persistence now writes `evidence_index.json` with retrieval context, evidence records, evidence-to-field mappings, and field-to-evidence mappings for reuse and audit.
- Structured section generation and risk reporting now run as explicit tools before draft persistence; `PWPSState.sections` and `field_report` carry structured output for the renderer.
- State patch merging now goes through `core/state_merge.py`, with allowed patch keys, unknown-key/unknown-field merge warnings, field priority protection, candidate preservation, timestamp metadata, and ID-based de-duplication for knowledge queries, search results, and evidence.
- Supervisor action decisions now include action metadata in trace, including action type, tool name, and action index.
- Graph runtime checkpoint helpers persist safe resume points under `<output_dir>/<run_id>/checkpoints/`, including numbered checkpoint files and `latest.json`.
- Graph runs can be interrupted after a configured number of runtime steps and resumed from the latest checkpoint by loading the saved `PWPSState` with resume mode.
- `guided_confirmation` now has a first interaction slice: grouped confirmation views with clarification questions, candidates, evidence snippets, risks, explicit user confirmation records, edit/rollback history, a graph `ASK_USER` pause node, graph-backed resume through compose/finish, state-file CLI commands, and a lightweight local Web UI/API.
- `guided_confirmation` now supports durable checkpoint-backed resume by `run_id`; after user confirmation it returns through the graph Supervisor, pauses again while candidate, suggested, conflict, need-confirmation, or explicit candidate-option fields remain, and composes/finishes only when confirmation is complete.
- `supplement_update` is now a first-class graph path: `UPDATE_STATE` applies user supplements, saved-state and run-checkpoint CLI commands can merge supplemental fields, artifacts are regenerated, and checkpoints are persisted.
- `domain_skills/` now contains first-stage markdown guidance packages for auto-draft, guided confirmation, evidence handling, and risk review.
- `prompt_loader` can safely load individual Domain Skills and ordered Domain Skill context bundles for future Supervisor prompts.
- The graph slice currently covers autonomous `auto_draft` plus guided-confirmation `ASK_USER` pause/resume through draft composition; durable checkpoint-backed live user sessions and richer multi-turn interaction remain future work.
- Tests currently cover config loading, contracts, interaction modes, guided confirmation view/history/resume/Web helpers, web search providers, LLM clients, requirement understanding, knowledge planning, evidence reasoning, rendering, state merge, domain skill loading, auto draft workflow, graph auto draft workflow, graph guided-confirmation pause behavior, graph retry/timeout behavior, graph checkpoint/resume behavior, graph Supervisor planner injection, and CLI.

Recent verification:

```text
uv run pytest tests/test_config.py tests/test_guided_confirmation.py tests/test_guided_confirmation_resume.py tests/test_graph_supervisor_planner.py tests/test_graph_auto_draft.py tests/test_cli.py -q
48 passed

uv run pytest -q
113 passed

uv run python -m compileall -q src tests
passed

git diff --check
passed with no output

uv run pytest tests/test_config.py tests/test_graph_auto_draft.py tests/test_graph_supervisor_planner.py -q
22 passed

uv run pytest -q
106 passed

uv run python -m compileall -q src tests
passed

git diff --check
passed with no output

KNOWLEDGE_SOURCES=web,model uv run pwps-agent auto-draft "Q355B 12mm plate GMAW butt joint flat position AWS D1.1 pWPS draft" --output-dir /tmp/pwps-agent-knowledge-source-smoke --run-id web_model_demo_final3
/tmp/pwps-agent-knowledge-source-smoke/web_model_demo_final3
persisted pwps.json status: done
local_doc_search events: 0
web_search_query events: 3

uv run pytest tests/test_graph_supervisor_planner.py::test_graph_overrides_repeated_completed_llm_tool_action -q
1 passed

uv run pytest tests/test_cli.py::test_cli_auto_draft_emits_progress_logs -q
1 passed

uv run pwps-agent auto-draft "Q355B 12mm plate GMAW butt joint flat position AWS D1.1 pWPS draft" --output-dir /tmp/pwps-agent-fix-smoke --run-id demo_auto_fix
/tmp/pwps-agent-fix-smoke/demo_auto_fix

uv run pytest tests/test_config.py tests/test_graph_supervisor_planner.py tests/test_graph_auto_draft.py tests/test_cli.py -q
27 passed

uv run pytest -q
99 passed

uv run python -m compileall -q src tests
passed

git diff --check
passed with no output

uv run pytest tests/test_section_generation.py tests/test_risk_report.py tests/test_render.py -q
8 passed

uv run pytest -q
96 passed, 1 warning

uv run python -m compileall -q src tests
passed

git diff --check
passed with no output

uv run pytest tests/test_local_doc_provider.py tests/test_local_doc_search.py tests/test_graph_auto_draft.py -q
10 passed, 1 warning

uv run pytest -q
91 passed, 1 warning

uv run python -m compileall -q src tests
passed

git diff --check
passed with no output

uv run pytest tests/test_modes.py tests/test_cli.py tests/test_graph_supplement_update.py -q
17 passed, 1 warning

uv run pytest -q
84 passed, 1 warning

uv run python -m compileall -q src tests
passed

git diff --check
passed with no output

uv run pytest tests/test_guided_confirmation.py tests/test_guided_confirmation_resume.py tests/test_guided_confirmation_web.py tests/test_cli.py tests/test_graph_guided_confirmation.py -q
23 passed, 1 warning

uv run pytest -q
78 passed, 1 warning

uv run python -m compileall -q src tests
passed

git diff --check
passed with no output

uv run pytest tests/test_domain_skills.py tests/test_graph_supervisor_planner.py -q
10 passed, 1 warning

uv run pytest -q
73 passed, 1 warning

uv run python -m compileall -q src tests
passed

git diff --check
passed with no output

uv run pytest tests/test_config.py tests/test_graph_supervisor_planner.py tests/test_graph_auto_draft.py tests/test_cli.py -q
15 passed, 1 warning

uv run pytest -q
69 passed, 1 warning

uv run python -m compileall -q src tests
passed

git diff --check
passed with no output

uv run pytest tests/test_cli.py tests/test_graph_auto_draft.py tests/test_auto_draft_workflow.py -q
9 passed, 1 warning

uv run pytest -q
66 passed, 1 warning

uv run python -m compileall -q src tests
passed

git diff --check
passed with no output

uv run pytest -q
64 passed, 1 warning

uv run pytest tests/test_graph_guided_confirmation.py -q
3 passed, 1 warning

uv run pytest tests/test_guided_confirmation.py tests/test_guided_confirmation_web.py tests/test_cli.py -q
11 passed

uv run pytest tests/test_guided_confirmation_resume.py tests/test_guided_confirmation_web.py tests/test_cli.py tests/test_graph_guided_confirmation.py -q
14 passed, 1 warning

uv run python -m compileall -q src tests
passed

uv run pwps-agent guided-confirm /tmp/pwps-guided-state.json --set filler_material=ER50-6 --message "Confirm filler from smoke" --reason "Smoke test" --evidence-id ev_web_1
confirm_1

uv run pwps-agent guided-confirm-resume /tmp/pwps-guided-resume-state.json --set filler_material=ER50-6 --message "Confirm filler and resume" --reason "CLI resume smoke" --output-dir /tmp/pwps-guided-resume-out
/tmp/pwps-guided-resume-out/guided_resume_smoke

curl -s -D - http://127.0.0.1:8765/api/state
HTTP/1.0 200 OK

curl -s -X POST http://127.0.0.1:8765/api/resume ...
status: done, has_draft: true, output_dir: /tmp/pwps-guided-web-resume-out/web_resume_smoke

uv run pytest -q
49 passed, 1 warning

uv run pytest tests/test_knowledge_planning.py tests/test_web_search_provider.py tests/test_evidence_reasoning.py tests/test_state_merge.py tests/test_auto_draft_workflow.py tests/test_graph_retry.py -q
22 passed, 1 warning

uv run python -m compileall -q src tests
passed

uv run pytest -q
45 passed, 1 warning

uv run pytest tests/test_graph_checkpoint_resume.py tests/test_graph_supervisor_planner.py tests/test_graph_retry.py tests/test_graph_auto_draft.py -v
8 passed, 1 warning

uv run pytest tests/test_state_merge.py tests/test_graph_retry.py tests/test_graph_auto_draft.py tests/test_auto_draft_workflow.py -v
8 passed, 1 warning

uv run pytest tests/test_graph_supervisor_planner.py -v
2 passed, 1 warning

uv run pytest tests/test_domain_skills.py -v
3 passed

uv run pytest tests/test_graph_auto_draft.py -v
1 passed, 1 warning

uv run pwps-agent auto-draft "Q355B 12mm plate GMAW butt joint flat AWS D1.1 pWPS draft" --output-dir /tmp/pwps-agent-smoke --run-id smoke_langchain_structured_explicit
/tmp/pwps-agent-smoke/smoke_langchain_structured_explicit
```

## pWPS Field Scope

The system should organize output around these sections:

```text
A. File and project metadata
B. Welding applicability scope
C. Filler and auxiliary materials
D. Welding parameters
E. Thermal control and heat treatment
```

Important core input fields:

```text
applicable_standard
base_material
thickness or wall_thickness
workpiece_type
diameter, when pipe/tube
welding_process
joint_type
welding_position
```

These are the minimum fields usually needed to find similar pWPS/WPS cases. If they are missing, the Supervisor may ask clarifying questions, generate a template-only draft, or produce a missing-information report.

## Recommended Repository Structure

```text
pwps-agent/
├── configs/
│   ├── agent.yaml
│   ├── model.yaml
│   ├── workflow.yaml
│   ├── state_schema.yaml
│   ├── fields_schema.yaml
│   ├── knowledge.yaml
│   └── prompts/
│
├── data/
│   ├── local_docs/
│   ├── index/
│   └── outputs/
│
├── src/
│   └── pwps_agent/
│       ├── graph/
│       ├── agent/
│       ├── domain_skills/
│       ├── tools/
│       ├── core/
│       ├── knowledge/
│       ├── retrieval/
│       ├── llm/
│       ├── render/
│       ├── storage/
│       └── utils/
│
├── scripts/
└── tests/
```

## Module Responsibilities

### `graph/`

LangGraph runtime:

- `builder.py`: build and compile the graph.
- `state.py`: define `PWPSState`.
- `supervisor.py`: node that calls the LLM Supervisor.
- `router.py`: route `AgentAction` to tool/action nodes.
- `subflows.py`: interaction-mode subflows such as `auto_draft`, `guided_confirmation`, and supplemental update.
- `checkpoints.py`: checkpoint and recovery helpers.

### `agent/`

LLM Supervisor implementation:

- `supervisor_agent.py`: prompt + model + structured output.
- `action_schema.py`: `AgentAction` schema.
- `memory_view.py`: compact state summary for the LLM.
- `prompt_loader.py`: prompt and domain-skill loading helpers.
- `model_client.py`: OpenAI-compatible model client. The endpoint may be any provider that supports the OpenAI API shape.
- `langchain_client.py`: preferred structured-output client using LangChain chat models and Pydantic schemas.

### `domain_skills/`

Domain guidance packages for the Supervisor:

- `pwps_auto_draft.md`: how to generate a draft from minimum input while preserving uncertainty.
- `pwps_guided_confirmation.md`: how to ask for field confirmation, explain candidates, and record user choices.
- `pwps_evidence_handling.md`: how to classify user input, local docs, web references, and LLM suggestions.
- `pwps_risk_review.md`: how to flag missing, low-confidence, thermal/PWHT, and qualification-sensitive fields.

Domain Skills do not execute business actions directly. They instruct the LLM Supervisor how to use state, tools, evidence, and wording safely.

### `tools/`

Executable runtime capabilities:

- `requirement_understanding.py`: structured extraction from user input or supplemental input.
- `knowledge_planning.py`: dynamic model-planned knowledge queries based on known fields, missing fields, and target evidence needs.
- `local_doc_search.py`: local document retrieval.
- `web_search.py`: web search wrapper.
- `evidence_extract.py`: convert search results or document snippets into structured evidence.
- `field_reasoning.py`: propose field candidates from evidence.
- `field_merge.py`: merge tool results into `PWPSState`.
- `section_generation.py`: generate A/B/C/D/E section drafts from field state.
- `draft_render.py`: render Markdown/HTML drafts.
- `risk_report.py`: produce missing-field and risk reports.
- `state_persist.py`: save state, trace, and output files.

Tools should have narrow responsibilities and return structured `ToolResult` objects. Tools must not mutate global state directly.

Do not make web search a fixed string template as the primary behavior. The Supervisor should call knowledge planning first, then execute one or more planned queries. A fixed query template is only acceptable as a fallback when planning fails.

### `core/`

Data contracts and state helpers:

- `contracts.py`: shared contract models.
- `field_state.py`: `FieldState` model.
- `field_manager.py`: merge fields, add candidates, link evidence.
- `source.py`: source and evidence types.
- `errors.py`: custom errors.

Do not implement a welding rule engine here in stage one.

### `knowledge/`

Black-box knowledge providers:

- `base.py`: provider interface.
- `provider.py`: composite provider.
- `local_doc_provider.py`: local document retrieval.
- `web_search_provider.py`: web search wrapper.
- `result_ranker.py`: lightweight ranking/merging.

The Supervisor should not depend on provider internals.

Web search must use real provider integrations, not mock providers. The provider is selected by `WEB_SEARCH_PROVIDER` and configured through `.env`.

### `render/`

Draft and report rendering:

- Markdown first.
- HTML optional.
- DOCX/PDF can be added later.

## Coding Guidelines

- Prefer typed Python and Pydantic models.
- Keep node inputs/outputs serializable.
- Manage prompts centrally under `configs/prompts/`; do not scatter production prompts inside tool functions.
- Treat Pydantic schemas as the primary structured-output contract. Put field semantics, required uncertainty wording, and extraction constraints into model docstrings and `Field(description=...)` where possible.
- Use structured LLM output wherever possible. For LLM-backed tools, prefer LangChain `with_structured_output(PydanticModel)` with useful Pydantic model and `Field(description=...)` text instead of complex format instructions in prompts.
- Keep prompts focused on role, task boundary, safety rules, and domain constraints; keep output shape in Pydantic schemas.
- Do not duplicate JSON shape instructions in multiple prompts when the same constraint belongs in a shared Pydantic model.
- Keep model temperature low for reproducibility.
- Read model configuration from `.env`; use `LLM_API_KEY`, `LLM_BASE_URL`, and `LLM_MODEL` as provider-neutral names. Compatibility aliases such as `OPENAI_API_KEY` are allowed only for SDKs that require OpenAI-style environment names.
- Read structured-output mode from `LLM_STRUCTURED_OUTPUT_METHOD`, normally `function_calling` for providers that support OpenAI-compatible tool calling, with `json_mode` or `json_schema` only when the provider supports that path.
- For DeepSeek V4 structured output through function/tool calling, prefer non-thinking mode unless the client fully supports thinking-mode tool-call semantics; use `LLM_THINKING_TYPE=disabled` when needed.
- Log every Supervisor action, domain-skill selection, tool call, and tool result to trace.
- Avoid hidden side effects.
- Keep business wording clear: use “draft”, “candidate”, “suggested”, “needs confirmation”.
- Never label a web result or LLM suggestion as verified standard fact.

## LangGraph Pattern

Use an LLM action loop:

```text
START
  ↓
supervisor
  ↓
route_action
  ├── call_tool
  ├── update_state
  ├── ask_user
  ├── compose_draft
  ├── generate_report
  └── END
  ↓
supervisor
```

Do not implement the first version as a hard-coded linear workflow unless it is only a temporary smoke test.

Supported interaction modes:

```text
auto_draft
  User supplies minimum core input.
  Supervisor fills the draft with user-provided, candidate, suggested, and missing fields.
  The system minimizes interruptions and makes uncertainty visible.

guided_confirmation
  Supervisor presents related field groups to the user.
  Each candidate includes a recommendation, explanation, source/evidence, and risk note.
  User-confirmed values can be promoted to confirmed field status.

supplement_update
  User can add information at any time.
  The system parses the supplement, patches related fields, and re-evaluates affected draft/report parts.
```

## AgentAction Schema

The Supervisor should output actions like:

```json
{
  "action_type": "CALL_TOOL",
  "tool_name": "web_search",
  "tool_args": {
    "query": "Q355B 12mm GMAW butt joint flat position pWPS WPS"
  },
  "rationale_summary": "Core scenario fields are available; search for similar cases and parameter references.",
  "expected_state_change": "Add similar-case evidence for filler and welding parameters."
}
```

Supported action types:

```text
USE_DOMAIN_SKILL
CALL_TOOL
UPDATE_STATE
ASK_USER
COMPOSE_DRAFT
GENERATE_REPORT
FINISH
```

## Output Files

Each run should be able to produce:

```text
pwps.json
pwps_draft.md
field_report.json
trace.json
```

Optional:

```text
pwps_draft.html
field_report.md
```

## Safety and Accuracy Notes

This is an engineering-assistance system. It must not present draft output as final welding procedure approval.

Always preserve uncertainty:

- Unknown project metadata stays blank or “待确认”.
- Web-derived values are `candidate` or `reference_only`.
- LLM-derived values are `suggested`.
- Thermal control, PWHT, heat input, and qualification-sensitive fields should be flagged when not backed by strong evidence.

## Development Order

Recommended implementation order:

1. Define `PWPSState`, `AgentAction`, `FieldState`, `Evidence`, `ToolResult`.
2. Implement LLM Supervisor with structured output.
3. Implement LangGraph builder and router.
4. Implement `interaction_mode` handling for `auto_draft`, `guided_confirmation`, and supplemental updates.
5. Implement requirement understanding tool.
6. Implement field initialization and field merge tools.
7. Implement local doc and web search tools.
8. Implement evidence extraction and field reasoning tools.
9. Implement draft rendering.
10. Implement field/risk report.
11. Add trace persistence.
12. Add domain-skill guidance files.
13. Add tests and sample runs.

## Testing Expectations

Add tests for:

- Schema validation.
- Supervisor action parsing.
- Tool result merging.
- Field evidence linking.
- Auto draft mode from minimum input.
- Guided confirmation mode with user-confirmed field promotion.
- Supplemental input updates to existing field state.
- Draft rendering with missing fields.
- Trace generation.
- End-to-end demo input.

Use small deterministic fixtures under `tests/fixtures/`.

## Do Not Do

- Do not add a hard-coded welding rule engine in stage one.
- Do not make LLM a fallback after rules.
- Do not create multiple expert agents prematurely.
- Do not store important results only in natural language messages.
- Do not generate fake project metadata.
- Do not remove uncertainty labels from candidate values.
- Do not claim final compliance or approval.
