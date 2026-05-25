# LLM Supervisor Planner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a replaceable Supervisor planner interface and make the LLM-backed planner the default LangGraph action selector.

**Architecture:** Use the LLM planner as the normal runtime path. Keep an optional planner dependency on `GraphRuntimeContext` for tests, resume flows, and controlled recovery. The LLM planner builds compact state and Domain Skill context, then requests a structured `AgentAction` through the existing structured-output client helper.

**Tech Stack:** Python 3.14, Pydantic v2, LangGraph, pytest via `uv`.

**Status:** Completed. The graph supervisor now has an injectable planner seam and uses an LLM-backed planner by default to request structured `AgentAction` output with Domain Skill context. Deterministic progression is retained only as an internal safety/test helper, not as an exposed runtime mode.

**Stability update 2026-05-25:** Live `SUPERVISOR_PLANNER=llm` smoke exposed that an LLM planner can repeatedly request already completed tool actions, causing LangGraph's recursion limit to stop the run. The Supervisor now detects repeated completed actions, records an `agent_action_overridden` trace event, and advances through the deterministic next action. CLI auto-draft also emits runtime logs to stderr, and the known upstream LangGraph/LangChain `allowed_objects` pending-deprecation warning is narrowly filtered.

**Mode update 2026-05-25:** `SUPERVISOR_PLANNER` is no longer a supported configuration key. `auto_draft` now explicitly runs as an autonomous drafting mode and overrides premature `ASK_USER` actions to the safe next graph step. `guided_confirmation` uses guided-confirmation Domain Skill context by default and continues pausing while candidate, suggested, conflict, need-confirmation, or explicit candidate-option fields remain.

---

### Task 1: Planner Injection Tests

**Files:**
- Create: `tests/test_graph_supervisor_planner.py`
- Modify: `src/pwps_agent/graph/state.py`
- Modify: `src/pwps_agent/graph/supervisor.py`

- [x] Write tests proving an injected planner controls `supervisor_node` output and that the LLM planner calls structured output with the `AgentAction` schema.
- [x] Run `uv run pytest tests/test_graph_supervisor_planner.py -v` and confirm the tests fail before implementation.
- [x] Add optional `supervisor_planner` to `GraphRuntimeContext`.
- [x] Implement a planner protocol, internal safe progression helper, and `LLMSupervisorPlanner`.
- [x] Run `uv run pytest tests/test_graph_supervisor_planner.py -v` and confirm the tests pass.

### Task 2: Regression Verification And Progress Docs

**Files:**
- Modify: `docs/superpowers/plans/2026-05-24-llm-supervisor-planner.md`
- Modify: `AGENTS.md`

- [x] Run `uv run pytest -q`.
- [x] Update this plan with final status and verification evidence.
- [x] Update `AGENTS.md` Current Implementation Progress only after verification passes.

Verification:

```text
uv run pytest tests/test_config.py tests/test_guided_confirmation.py tests/test_guided_confirmation_resume.py tests/test_graph_supervisor_planner.py tests/test_graph_auto_draft.py tests/test_cli.py -q
48 passed

uv run pytest -q
113 passed

uv run python -m compileall -q src tests
passed

git diff --check
passed with no output

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

uv run pytest tests/test_graph_supervisor_planner.py -v
2 passed, 1 warning

uv run pytest -q
37 passed, 1 warning
```
