# Quick Start for Codex in Goal Mode

**You are working on**: pWPS Agent (LLM-centric welding procedure spec draft generation)

## 5-Minute Orientation

1. **What's the project?**
   - See: `AGENTS.md` "Project Overview" section
   - TL;DR: LLM Supervisor + Domain Skills + LangGraph = autonomous draft generation

2. **What are the rules?**
   - See: `.instructions.md` (COMPREHENSIVE - start here!)
   - Key: State First, Preserve Uncertainty, Test Always, Document Changes

3. **What should I work on?**
   - See: `.agent.md` "Next Priority Goals"
   - Pick one of Phase 8 options (A/B/C/D) - all equally ready

4. **How do I debug/verify?**
   - Full test: `uv run pytest -q` (expect 144 passed)
   - Smoke test: `uv run pwps-agent auto-draft "Q355B 12mm GMAW" --output-dir /tmp/smoke --run-id test1`
   - Compilation: `uv run python -m compileall -q src tests`

5. **What if I get stuck?**
   - Architecture details: `docs/architecture.md`
   - Data model: `docs/data_schema.md`
   - Agent design: `docs/agent_design.md`
   - See `docs/README.md` for full navigation

## File Navigation Quick Map

```
ROOT (Start here)
├── .instructions.md    ← Development guidelines (MUST READ)
├── .agent.md          ← Current goals and priorities
├── AGENTS.md          ← Design principles + implementation status
│
├── README.md          ← User-facing documentation
├── README.zh-CN.md    ← Chinese version
│
└── docs/
    ├── README.md      ← Documentation index
    ├── architecture.md
    ├── agent_design.md
    ├── data_schema.md
    └── superpowers/plans/README.md  ← Archive of completed phases
```

## The Golden Rules

✅ **Always**
- State First: PWPSState is the single source of truth
- Test: Full suite + smoke test before committing
- Preserve Uncertainty: Mark all values with source + confidence
- Document: Update AGENTS.md after completion

❌ **Never**
- Hard-code welding rules
- Invent project metadata (customer name, contract #, etc.)
- Hide uncertainty in field values
- Skip trace logging

## Common Commands

```bash
# Run tests
uv run pytest -q

# Smoke test (end-to-end verification)
uv run pwps-agent auto-draft "Q355B 12mm GMAW butt joint flat" \
  --output-dir /tmp/smoke --run-id smoke1

# Full verification before commit
uv run pytest -q && \
uv run python -m compileall -q src tests && \
git diff --check

# Load and inspect generated state
uv run python -c "
from pathlib import Path
from pwps_agent.core.state import PWPSState
state = PWPSState.model_validate_json(
  Path('/tmp/smoke/smoke1/pwps.json').read_text()
)
print(f'Fields filled: {len([f for f in state.fields.values() if f.value])}')
print(f'Missing: {len([f for f in state.fields.values() if not f.value])}')
"
```

## Task Workflow

When starting a new task:

1. **Understand**: Read relevant section in `.instructions.md`
2. **Check**: Review similar existing code/tests
3. **Plan**: Understand what needs to change (read AGENTS.md progress)
4. **Code**: Make minimal, surgical changes
5. **Test**: Full suite + smoke test
6. **Clean**: Remove debug output, dead code
7. **Document**: Update AGENTS.md Current Implementation Progress
8. **Commit**: Include co-author trailer

Example commit message:
```
[graph] Add retry logic for LLM supervisor action timeouts

- Supervisor now retries failed action planning up to 2 times
- Added backoff between retries
- Marked retry events in trace.json
- Verified: uv run pwps-agent auto-draft ... → /tmp/smoke/test1

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
```

## Phase 8 Options (Pick One)

**All are equally ready. Choose based on interest:**

### A: Sample Run Harness & Documentation
- Create deterministic sample runs
- Document expected outputs
- Add run scripts
- Clean up old docs

### B: Error Handling & Edge Cases  
- Add fallback for LLM structured output failures
- Handle partial web search results
- Support missing local docs gracefully
- Circuit breaker for provider outages

### C: CLI Polish & Help
- Add `--help` with usage examples
- Improve error messages
- Add config validation command
- Document environment variables

### D: Domain Skills Enrichment
- Expand guided_confirmation field grouping
- Add PWHT/thermal risk detection
- Create WPS vs pWPS guidance
- Enhance evidence classification

---

**Last updated**: 2026-05-25
**Test baseline**: 144 passed, 1 warning
**Questions?** Start with `.instructions.md`, then AGENTS.md
