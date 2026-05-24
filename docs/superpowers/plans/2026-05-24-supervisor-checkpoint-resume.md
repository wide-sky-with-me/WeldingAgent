# Supervisor Checkpoint And Resume Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Supervisor-path logging coverage plus safe checkpoint/interruption/resume support for the LangGraph auto-draft runtime.

**Architecture:** Keep Supervisor action logging in `supervisor_node`, add checkpoint persistence helpers under `graph/`, and checkpoint only safe runtime nodes after execution. `GraphRuntimeContext` carries checkpoint and interruption options; routers end the graph when state is interrupted.

**Tech Stack:** Python 3.14, Pydantic v2, LangGraph, pytest via `uv`.

**Status:** Completed. The graph runtime now persists safe checkpoints, can interrupt after configured runtime steps, can resume from the latest checkpoint, and has Supervisor-path trace coverage for action metadata.

---

### Task 1: Checkpoint And Resume Tests

**Files:**
- Create: `tests/test_graph_checkpoint_resume.py`
- Create: `src/pwps_agent/graph/checkpoints.py`
- Modify: `src/pwps_agent/graph/state.py`
- Modify: `src/pwps_agent/graph/router.py`
- Modify: `src/pwps_agent/graph/nodes.py`

- [x] Write failing tests for checkpoint files after runtime nodes, interruption after one checkpointed step, and resume from latest checkpoint.
- [x] Run `uv run pytest tests/test_graph_checkpoint_resume.py -v` and confirm it fails before implementation.
- [x] Implement checkpoint save/load helpers.
- [x] Add runtime checkpoint options to `GraphRuntimeContext`.
- [x] Add interruption-aware routing.
- [x] Persist checkpoints from safe runtime nodes.
- [x] Run `uv run pytest tests/test_graph_checkpoint_resume.py -v` and confirm it passes.

### Task 2: Supervisor Path Regression

**Files:**
- Modify: `tests/test_graph_supervisor_planner.py`

- [x] Add assertions that Supervisor trace payload includes action type, tool name, and action index.
- [x] Run `uv run pytest tests/test_graph_supervisor_planner.py -v`.

### Task 3: Full Verification And Progress Docs

**Files:**
- Modify: `docs/superpowers/plans/2026-05-24-supervisor-checkpoint-resume.md`
- Modify: `AGENTS.md`

- [x] Run `uv run pytest -q`.
- [x] Run `git diff --check`.
- [x] Update this plan and `AGENTS.md` with verification evidence only after commands pass.

Verification:

```text
uv run pytest tests/test_graph_checkpoint_resume.py tests/test_graph_supervisor_planner.py -v
4 passed, 1 warning

uv run pytest tests/test_graph_checkpoint_resume.py tests/test_graph_supervisor_planner.py tests/test_graph_retry.py tests/test_graph_auto_draft.py -v
8 passed, 1 warning

uv run pytest -q
45 passed, 1 warning

git diff --check
passed with no output
```
