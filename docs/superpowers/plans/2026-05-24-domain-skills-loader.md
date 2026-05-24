# Domain Skills Loader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add repo-local Domain Skill markdown packages and loader helpers so the future LLM Supervisor can include domain guidance explicitly.

**Architecture:** Keep Domain Skills as markdown guidance files under `src/pwps_agent/domain_skills/`. Extend the existing prompt loader with safe domain-skill loading helpers and a bundled-context formatter. Do not make Domain Skills executable tools or LangGraph subflows.

**Tech Stack:** Python 3.14, stdlib paths/dataclasses, pytest via `uv`.

**Status:** Completed. Domain Skill markdown packages now live under `src/pwps_agent/domain_skills/`, and the prompt loader can safely load individual skills or ordered Supervisor context bundles.

---

### Task 1: Domain Skill Loader Tests

**Files:**
- Create: `tests/test_domain_skills.py`
- Modify: `src/pwps_agent/agent/prompt_loader.py`

- [x] Write failing tests for safe domain skill loading, path traversal rejection, and bundled context formatting.
- [x] Run `uv run pytest tests/test_domain_skills.py -v` and confirm it fails before implementation.

### Task 2: Domain Skill Files And Loader

**Files:**
- Modify: `src/pwps_agent/agent/prompt_loader.py`
- Create: `src/pwps_agent/domain_skills/__init__.py`
- Create: `src/pwps_agent/domain_skills/pwps_auto_draft.md`
- Create: `src/pwps_agent/domain_skills/pwps_guided_confirmation.md`
- Create: `src/pwps_agent/domain_skills/pwps_evidence_handling.md`
- Create: `src/pwps_agent/domain_skills/pwps_risk_review.md`

- [x] Implement `DomainSkill`, `load_domain_skill()`, and `load_domain_skill_bundle()`.
- [x] Add four first-stage Domain Skill markdown packages matching `AGENTS.md`.
- [x] Run `uv run pytest tests/test_domain_skills.py -v` and confirm it passes.

### Task 3: Verification And Progress Docs

**Files:**
- Modify: `docs/superpowers/plans/2026-05-24-domain-skills-loader.md`
- Modify: `AGENTS.md`

- [x] Run `uv run pytest -q`.
- [x] Update this plan and `AGENTS.md` only after verification passes.

Verification:

```text
uv run pytest tests/test_domain_skills.py -v
3 passed

uv run pytest -q
35 passed, 1 warning
```
