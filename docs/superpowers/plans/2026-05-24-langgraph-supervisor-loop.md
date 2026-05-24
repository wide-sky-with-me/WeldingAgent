# LangGraph Supervisor Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a minimal LangGraph Supervisor action loop that can execute the existing `auto_draft` path through graph nodes.

**Architecture:** The graph layer owns orchestration and reuses existing runtime tools. A deterministic supervisor emits `AgentAction` objects in the current auto-draft order so the first graph is testable without live LLM reasoning. CLI wiring remains unchanged in this slice.

**Tech Stack:** Python 3.14, Pydantic v2, LangGraph, LangChain structured output clients, pytest via `uv`.

**Status:** Completed. The repository now has a minimal LangGraph auto-draft action loop with deterministic supervisor planning, runtime tool routing, draft persistence, and passing test coverage.

---

### Task 1: Graph Auto-Draft Behavior Test

**Files:**
- Create: `tests/test_graph_auto_draft.py`

- [x] Write a failing test that builds the graph with deterministic dependencies, invokes it from an initial `PWPSState`, and asserts persisted artifacts plus trace nodes.
- [x] Run `uv run pytest tests/test_graph_auto_draft.py -v` and confirm it fails because `pwps_agent.graph` does not exist.

### Task 2: LangGraph Dependency And Graph Modules

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Create: `src/pwps_agent/graph/__init__.py`
- Create: `src/pwps_agent/graph/state.py`
- Create: `src/pwps_agent/graph/supervisor.py`
- Create: `src/pwps_agent/graph/router.py`
- Create: `src/pwps_agent/graph/nodes.py`
- Create: `src/pwps_agent/graph/builder.py`

- [x] Add `langgraph` as a runtime dependency.
- [x] Implement `GraphRuntimeContext` for injectable dependencies and output settings.
- [x] Implement deterministic supervisor planning for the six auto-draft actions.
- [x] Implement router mapping from action type/tool name to graph node names.
- [x] Implement tool and compose nodes by reusing existing modules.
- [x] Build a `StateGraph` with `START`, `END`, conditional routing, and compiled invocation.
- [x] Run `uv run pytest tests/test_graph_auto_draft.py -v` and confirm it passes.

### Task 3: Full Verification And Progress Docs

**Files:**
- Modify: `docs/superpowers/plans/2026-05-24-langgraph-supervisor-loop.md`
- Modify: `AGENTS.md`

- [x] Run `uv run pytest -q`.
- [x] Update this plan status and checked tasks only after verification passes.
- [x] Update `AGENTS.md` Current Implementation Progress with the graph slice and verification evidence.

Verification:

```text
uv run pytest tests/test_graph_auto_draft.py -v
1 passed, 1 warning

uv run pytest -q
32 passed, 1 warning
```
