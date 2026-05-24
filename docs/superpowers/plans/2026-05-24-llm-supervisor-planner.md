# LLM Supervisor Planner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a replaceable Supervisor planner interface and an LLM-backed planner for LangGraph auto-draft action selection.

**Architecture:** Keep deterministic planning as the default path and add an optional planner dependency on `GraphRuntimeContext`. The LLM planner builds compact state and Domain Skill context, then requests a structured `AgentAction` through the existing structured-output client helper.

**Tech Stack:** Python 3.14, Pydantic v2, LangGraph, pytest via `uv`.

**Status:** Completed. The graph supervisor now has an injectable planner seam, keeps deterministic auto-draft planning as the default, and includes an LLM-backed planner that requests structured `AgentAction` output with Domain Skill context.

---

### Task 1: Planner Injection Tests

**Files:**
- Create: `tests/test_graph_supervisor_planner.py`
- Modify: `src/pwps_agent/graph/state.py`
- Modify: `src/pwps_agent/graph/supervisor.py`

- [x] Write tests proving an injected planner controls `supervisor_node` output and that the LLM planner calls structured output with the `AgentAction` schema.
- [x] Run `uv run pytest tests/test_graph_supervisor_planner.py -v` and confirm the tests fail before implementation.
- [x] Add optional `supervisor_planner` to `GraphRuntimeContext`.
- [x] Implement a planner protocol, deterministic planner class, and `LLMSupervisorPlanner`.
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
uv run pytest tests/test_graph_supervisor_planner.py -v
2 passed, 1 warning

uv run pytest -q
37 passed, 1 warning
```
