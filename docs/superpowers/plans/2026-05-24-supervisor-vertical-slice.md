# Supervisor Vertical Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a runnable `auto_draft` vertical slice that extracts core fields with an OpenAI-compatible model client, searches real web providers, converts results to evidence/candidates, renders outputs, and persists run artifacts.

**Architecture:** Keep LangGraph out for this slice and implement a replaceable `run_auto_draft()` application service. Runtime tools remain focused modules: LangChain structured-output client, centralized prompt loading, requirement understanding, evidence extraction, field reasoning, persistence, and CLI. Tests use deterministic fake clients and recorded search payloads; runtime code does not include mock web-search providers.

**Tech Stack:** Python 3.14, Pydantic v2, LangChain `with_structured_output`, OpenAI-compatible chat API, pytest via `uv`.

**Status:** Completed. Verified with `uv run pytest -q` (`31 passed`) and a live DeepSeek/Tavily smoke run writing `/tmp/pwps-agent-smoke/smoke_langchain_structured_explicit`.

---

### Task 1: OpenAI-Compatible LLM Client

**Files:**
- Create: `src/pwps_agent/llm/__init__.py`
- Create: `src/pwps_agent/llm/openai_compatible.py`
- Test: `tests/test_llm_client.py`

- [x] Write failing tests for request payload shape, base URL handling, bearer auth, and JSON response parsing.
- [x] Implement `OpenAICompatibleClient` with injectable transport.
- [x] Add `LangChainStructuredClient` using `with_structured_output(PydanticModel)` for runtime structured output.
- [x] Run `uv run pytest tests/test_llm_client.py -v`.

### Task 2: Requirement Understanding Tool

**Files:**
- Create: `src/pwps_agent/tools/__init__.py`
- Create: `src/pwps_agent/tools/requirement_understanding.py`
- Test: `tests/test_requirement_understanding.py`

- [x] Write failing tests that parse structured LLM output into `core_fields` and field updates.
- [x] Implement centralized prompt loading and Pydantic structured output parsing.
- [x] Add explicit user-input normalization for fields written directly by the user without turning this into a welding rule engine.
- [x] Run `uv run pytest tests/test_requirement_understanding.py -v`.

### Task 3: Evidence Extraction And Field Reasoning

**Files:**
- Create: `src/pwps_agent/tools/evidence.py`
- Create: `src/pwps_agent/tools/field_reasoning.py`
- Test: `tests/test_evidence_reasoning.py`

- [x] Write failing tests that convert `SearchResult` to `Evidence` and add candidate fields from simple structured claims.
- [x] Implement deterministic minimal extraction and field candidate merge.
- [x] Add LLM-backed field reasoning with Pydantic candidate schema.
- [x] Run `uv run pytest tests/test_evidence_reasoning.py -v`.

### Task 4: Auto Draft Workflow And Persistence

**Files:**
- Create: `src/pwps_agent/workflows/__init__.py`
- Create: `src/pwps_agent/workflows/auto_draft.py`
- Create: `src/pwps_agent/storage/__init__.py`
- Create: `src/pwps_agent/storage/persist.py`
- Test: `tests/test_auto_draft_workflow.py`

- [x] Write failing tests for end-to-end auto draft with fake LLM transport and fake search provider object.
- [x] Implement `run_auto_draft()` and artifact persistence to `pwps.json`, `pwps_draft.md`, `field_report.json`, `trace.json`.
- [x] Wire model-planned `knowledge_planning` before web search.
- [x] Run `uv run pytest tests/test_auto_draft_workflow.py -v`.

### Task 5: CLI

**Files:**
- Modify: `pyproject.toml`
- Create: `src/pwps_agent/cli.py`
- Test: `tests/test_cli.py`

- [x] Write failing tests for CLI argument parsing and output directory reporting.
- [x] Implement `pwps-agent auto-draft "<requirement>"`.
- [x] Run `uv run pytest tests/test_cli.py -v`.

### Task 6: Verification

**Files:**
- Modify as needed based on test failures only.

- [x] Run `uv run pytest -q`.
- [x] If `.env` has real credentials, run one smoke command with a short requirement.
- [x] Run `git status --short --branch`.
- [x] Summarize implemented scope and remaining gaps.
