# LangGraph Supervisor Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the middle-stage LangGraph/Supervisor runtime with explicit action execution, retry routing, and robust state patch merging.

**Architecture:** Add a canonical merge engine under `core/`, keep workflow compatibility through `_merge_state_patch()`, and enhance graph routing so tool failures can retry before failing the run. Keep web query execution sequential in this slice while recording per-query trace data for later parallelization.

**Tech Stack:** Python 3.14, Pydantic v2, LangGraph, pytest via `uv`.

**Status:** Completed. The graph runtime now has retry-aware post-tool routing, per-query web search trace with timeout handling, and a canonical state merge engine with field priority and de-duplication behavior.

---

### Task 1: State Merge Engine

**Files:**
- Create: `src/pwps_agent/core/state_merge.py`
- Create: `tests/test_state_merge.py`
- Modify: `src/pwps_agent/workflows/auto_draft.py`

- [x] Write failing tests for unknown patch warnings, user-priority field protection, field candidate preservation, and ID-based list de-duplication.
- [x] Run `uv run pytest tests/test_state_merge.py -v` and confirm it fails before implementation.
- [x] Implement `merge_state_patch()` in `core/state_merge.py`.
- [x] Delegate `workflows.auto_draft._merge_state_patch()` to the new merge engine.
- [x] Run `uv run pytest tests/test_state_merge.py -v` and confirm it passes.

### Task 2: Graph Retry Routing

**Files:**
- Create: `tests/test_graph_retry.py`
- Modify: `src/pwps_agent/graph/state.py`
- Modify: `src/pwps_agent/graph/router.py`
- Modify: `src/pwps_agent/graph/nodes.py`
- Modify: `src/pwps_agent/graph/builder.py`

- [x] Write failing tests for a retryable tool exception that succeeds on retry, an exhausted tool failure that marks state failed, and per-query web search timeout/partial success.
- [x] Run `uv run pytest tests/test_graph_retry.py -v` and confirm it fails before implementation.
- [x] Add retry, query timeout, and max parallel query settings to `GraphRuntimeContext`.
- [x] Add post-tool routing in `router.py`.
- [x] Catch tool exceptions and failed `ToolResult` values in `call_tool_node`.
- [x] Wire `call_tool` conditional routing in `builder.py`.
- [x] Run `uv run pytest tests/test_graph_retry.py -v` and confirm it passes.

### Task 3: Regression Verification And Progress Docs

**Files:**
- Modify: `docs/superpowers/plans/2026-05-24-langgraph-supervisor-completion.md`
- Modify: `AGENTS.md`

- [x] Run `uv run pytest -q`.
- [x] Run `git diff --check`.
- [x] Update this plan and `AGENTS.md` with verification evidence only after commands pass.

Verification:

```text
uv run pytest tests/test_state_merge.py -v
3 passed

uv run pytest tests/test_graph_retry.py -v
3 passed, 1 warning

uv run pytest tests/test_state_merge.py tests/test_graph_retry.py tests/test_graph_auto_draft.py tests/test_auto_draft_workflow.py -v
8 passed, 1 warning

uv run pytest -q
43 passed, 1 warning

git diff --check
passed with no output
```
