# Project Documentation Index

Quick navigation for pWPS Agent developers.

## For New Developers

**Start here** (in this order):

1. **`.instructions.md`** (repo root) - Development guidelines and working rules
2. **`.agent.md`** (repo root) - Current goals and next priorities
3. **`AGENTS.md`** (repo root) - Design principles and implementation status

Then choose based on your task:

- **Implementing a feature**: Read the applicable `architecture.md` section + `.instructions.md` code patterns
- **Understanding data model**: `data_schema.md`
- **Debugging the graph**: `architecture.md` → `graph/` module code
- **Adding a tool**: `agent_design.md` → `tools/` module code
- **Extending guidance**: Review `src/pwps_agent/domain_skills/` markdown files
- **Continuing current hardening work**: `superpowers/plans/2026-05-25-llm-led-dual-mode-hardening.md`

## Full Reference

### Architecture & Design

- **`architecture.md`** - System components, LangGraph flow, module roles
- **`agent_design.md`** - LLM Supervisor reasoning, action loops, interaction modes
- **`data_schema.md`** - PWPSState structure, field definitions, evidence model
- **`requirements.md`** - Original Stage One requirements (reference only)

### Active Implementation Plan

- **`superpowers/plans/2026-05-25-llm-led-dual-mode-hardening.md`** - LLM-led dual mode hardening for `auto_draft` and `guided_confirmation`

### Phase Implementation Plans (Archive)

- **`superpowers/plans/README.md`** - Index of completed phases
- **`superpowers/plans/2026-05-24-stage-one-completion-roadmap.md`** - Master roadmap
- Earlier dated `.md` files in `plans/` are completed phase documentation (reference only)

### Implementation Specs (Archive)

- Files in `superpowers/specs/` document specific design decisions for past phases

---

## Key Principles to Remember

**When starting work:**

1. Don't read all docs — read only what's needed for your task
2. Check `.instructions.md` "Code Change Process" section
3. Review relevant Domain Skills in `src/pwps_agent/domain_skills/`
4. Look at existing tests for similar patterns

**When finishing work:**

1. Update AGENTS.md "Current Implementation Progress"
2. Run full test suite + smoke test
3. Clean dead code/imports/debug output
4. Commit with proper co-author trailer

**Questions?**

- About project scope/design: AGENTS.md Core Design Principles
- About coding patterns: `.instructions.md` Code Style Conventions
- About what's next: `.agent.md` Priority Goals and the active hardening plan
- About a specific phase: See that phase's plan/spec under `superpowers/`

---

Last updated: 2026-05-25
