# LLM Evidence Reasoning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the placeholder keyword-only field reasoning with an LLM-backed tool that reads real web evidence and returns traceable candidate pWPS fields.

**Architecture:** Keep web search as a real provider and convert results to Evidence. Add an LLM-backed `reason_fields_from_evidence()` tool that uses centralized prompts plus LangChain/Pydantic structured output, returning candidate fields with value, status, confidence, evidence IDs, and notes. Keep deterministic user-input normalization only for explicit fields supplied by the user; do not introduce welding rule-engine logic.

**Tech Stack:** Python 3.14, Pydantic v2, LangChain `with_structured_output`, OpenAI-compatible chat API, pytest.

**Status:** Completed. `field_reasoning` now uses centralized prompts plus Pydantic structured output, and the auto-draft workflow persists model-derived candidate fields from real web evidence.

---

### Task 1: Structured Field Reasoning Contract

**Files:**
- Modify: `src/pwps_agent/tools/field_reasoning.py`
- Test: `tests/test_evidence_reasoning.py`

- [x] Write failing tests for structured LLM output mapping to candidate field patches.
- [x] Add `reason_fields_from_evidence(state, evidence, client)` returning `ToolResult`.
- [x] Run `uv run pytest tests/test_evidence_reasoning.py -v`.

### Task 2: Workflow Wiring

**Files:**
- Modify: `src/pwps_agent/workflows/auto_draft.py`
- Test: `tests/test_auto_draft_workflow.py`

- [x] Write failing tests that `run_auto_draft()` calls the evidence reasoning tool and persists its candidates.
- [x] Wire `AutoDraftDependencies` to include an evidence reasoning tool.
- [x] Run `uv run pytest tests/test_auto_draft_workflow.py -v`.

### Task 3: Verification

**Files:**
- Modify only if tests reveal issues.

- [x] Run `uv run pytest -q`.
- [x] If network approval is available, run one bounded live smoke test.
- [x] Inspect generated `field_report.json` and draft for candidate fields derived from real web evidence.
