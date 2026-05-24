# Minimal Core Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first runnable pWPS Agent core that can load configuration, maintain pWPS field state, support `auto_draft` and `guided_confirmation`, render a draft/report, and expose real web-search provider adapters.

**Architecture:** Keep the first implementation as a small Python package under `src/pwps_agent`. Pydantic models define contracts; pure services initialize and update state; web search providers use real external APIs when configured and return unified `SearchResult` objects. No mock web-search provider is part of runtime code.

**Tech Stack:** Python 3.14, Pydantic v2, pytest via `uv`, stdlib HTTP for provider adapters.

**Status:** Completed for the current core slice. The repo has passing tests for config, contracts, modes, rendering, and real web-search provider adapters.

---

### Task 1: Project Skeleton And Config Tests

**Files:**
- Create: `pyproject.toml`
- Create: `src/pwps_agent/__init__.py`
- Create: `src/pwps_agent/config.py`
- Test: `tests/test_config.py`

- [x] Write tests that load `.env` style files without exposing secrets and prefer provider-neutral `LLM_*` values.
- [x] Implement minimal config models and parser.
- [x] Run `uv sync` and `uv run pytest tests/test_config.py -v`.

### Task 2: Contracts And Field State

**Files:**
- Create: `src/pwps_agent/core/contracts.py`
- Create: `src/pwps_agent/core/fields.py`
- Test: `tests/test_contracts.py`

- [x] Write tests for `AgentAction`, `ToolResult`, `FieldState`, `ConfirmationRecord`, and default A/B/C/D/E field initialization.
- [x] Implement the Pydantic contracts.
- [x] Run `uv run pytest tests/test_contracts.py -v`.

### Task 3: Interaction Modes

**Files:**
- Create: `src/pwps_agent/core/state.py`
- Create: `src/pwps_agent/core/modes.py`
- Test: `tests/test_modes.py`

- [x] Write tests for `auto_draft`, `guided_confirmation`, and supplemental updates.
- [x] Implement state creation, user confirmation promotion to `user_confirmed`, and supplement merge behavior.
- [x] Run `uv run pytest tests/test_modes.py -v`.

### Task 4: Rendering

**Files:**
- Create: `src/pwps_agent/render/markdown.py`
- Test: `tests/test_render.py`

- [x] Write tests that render a draft with missing, candidate, suggested, and user-confirmed fields.
- [x] Implement Markdown draft and simple field report rendering.
- [x] Run `uv run pytest tests/test_render.py -v`.

### Task 5: Real Web Search Provider Adapters

**Files:**
- Create: `src/pwps_agent/knowledge/web_search_provider.py`
- Test: `tests/test_web_search_provider.py`

- [x] Write tests for provider selection, missing-key validation, request shape, and response parsing using recorded sample payloads.
- [x] Implement Tavily and Brave provider adapters with stdlib HTTP.
- [x] Do not add a mock provider to runtime code.
- [x] Run `uv run pytest tests/test_web_search_provider.py -v`.

### Task 6: Verification

**Files:**
- Modify as needed based on test failures only.

- [x] Run `uv run pytest -q`.
- [x] Run `git status --short --branch`.
- [x] Summarize implemented scope and remaining gaps.
