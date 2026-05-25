# pWPS Agent

LLM-centric pWPS draft generation agent core.

This repository implements a first-stage assistant for generating **draft** preliminary Welding Procedure Specifications (pWPS). It uses a single LLM Supervisor, Domain Skills, runtime tools, `PWPSState`, LangGraph orchestration, local document retrieval, web search, and structured output contracts.

The system is intended to help engineers create traceable draft material quickly. It does **not** produce formally approved, signed, or guaranteed-compliant welding procedures.

## Current Capability

The current stage supports:

- `auto_draft` CLI flow through LangGraph.
- Structured requirement extraction with LLM-backed tools.
- Model-planned knowledge queries.
- Local markdown/text document retrieval.
- Web search provider integration.
- Evidence conversion and evidence-to-field linking.
- Field candidate reasoning.
- Explicit Domain Skill selection and trace records.
- Guided confirmation state services, CLI commands, and lightweight local Web UI/API.
- Checkpoint-backed guided confirmation resume by `run_id`.
- Supplemental update flow for saved state files or run checkpoints.
- Structured A/B/C/D/E section generation.
- Structured field/risk report generation.
- Persistent run artifacts:
  - `pwps.json`
  - `pwps_draft.md`
  - `field_report.json`
  - `trace.json`
  - `evidence_index.json`

## Safety Boundary

All output is draft assistance only.

- Unknown project metadata stays blank or `待确认`.
- Web-derived and LLM-derived values remain candidate/suggested unless confirmed by the user.
- Thermal control, PWHT, heat input, and qualification-sensitive values should be reviewed carefully.
- The system does not perform PQR/WPQR coverage validation.
- The system does not replace welding engineer review or formal approval.

## Requirements

- Python `>=3.14`
- `uv`
- LLM provider compatible with OpenAI-style APIs
- Optional web search provider credentials

Install dependencies:

```bash
uv sync
```

## Configuration

Create `.env` in the repository root. Do not commit secrets.

Minimal LLM configuration:

```text
LLM_API_KEY=...
LLM_BASE_URL=https://api.example.com
LLM_MODEL=...
LLM_TEMPERATURE=0.2
LLM_STRUCTURED_OUTPUT_METHOD=function_calling
LLM_THINKING_TYPE=disabled
```

Supervisor planner mode:

```text
SUPERVISOR_PLANNER=deterministic
```

Use `SUPERVISOR_PLANNER=llm` to let the LLM choose structured `AgentAction` values. Deterministic mode is the safer default for smoke testing.

Web search:

```text
WEB_SEARCH_PROVIDER=tavily
TAVILY_API_KEY=...
```

or:

```text
WEB_SEARCH_PROVIDER=brave
BRAVE_SEARCH_API_KEY=...
```

Runtime paths:

```text
PWPS_LOCAL_DOCS_DIR=data/local_docs
PWPS_OUTPUT_DIR=data/outputs
LOCAL_DOC_MAX_RESULTS=5
LOCAL_DOC_SNIPPET_CHARS=420
```

Local documents can be `.md`, `.markdown`, or `.txt` files.

## Quick Start

Run a real auto-draft smoke:

```bash
uv run pwps-agent auto-draft \
  "Q355B 12mm plate GMAW butt joint flat position AWS D1.1 pWPS draft" \
  --output-dir /tmp/pwps-agent-demo \
  --run-id demo_q355b_gmaw
```

Expected output:

```text
/tmp/pwps-agent-demo/demo_q355b_gmaw
```

Inspect generated files:

```bash
find /tmp/pwps-agent-demo/demo_q355b_gmaw -maxdepth 1 -type f -print
sed -n '1,180p' /tmp/pwps-agent-demo/demo_q355b_gmaw/pwps_draft.md
```

Validate the persisted state can be loaded:

```bash
uv run python -c "from pathlib import Path; from pwps_agent.core.state import PWPSState; PWPSState.model_validate_json(Path('/tmp/pwps-agent-demo/demo_q355b_gmaw/pwps.json').read_text(encoding='utf-8')); print('state reload ok')"
```

## CLI Commands

### Auto Draft

```bash
uv run pwps-agent auto-draft \
  "Q355B 12mm plate GMAW butt joint flat position AWS D1.1 pWPS draft" \
  --output-dir /tmp/pwps-agent-demo \
  --run-id demo_auto
```

### Guided Confirmation View

```bash
uv run pwps-agent guided-confirm-view /path/to/pwps.json
```

### Confirm Fields In A State File

```bash
uv run pwps-agent guided-confirm /path/to/pwps.json \
  --set filler_material=ER50-6 \
  --message "Confirm filler material" \
  --reason "Engineer accepted for draft"
```

### Confirm And Resume From A State File

```bash
uv run pwps-agent guided-confirm-resume /path/to/pwps.json \
  --set filler_material=ER50-6 \
  --message "Confirm and resume" \
  --output-dir /tmp/pwps-guided-out
```

### Confirm And Resume From Latest Checkpoint

```bash
uv run pwps-agent guided-confirm-resume-run demo_auto \
  --set filler_material=ER50-6 \
  --message "Confirm from checkpoint" \
  --output-dir /tmp/pwps-agent-demo
```

This loads:

```text
<output_dir>/<run_id>/checkpoints/latest.json
```

### Supplemental Update For A Saved State

```bash
uv run pwps-agent supplement-state /path/to/pwps.json \
  --message "Base material standard is GB/T 1591." \
  --set base_material_standard="GB/T 1591" \
  --output-dir /tmp/pwps-supplement-out
```

### Supplemental Update From Latest Checkpoint

```bash
uv run pwps-agent supplement-run demo_auto \
  --message "Shielding gas is 80% Ar / 20% CO2." \
  --set shielding_gas="80% Ar / 20% CO2" \
  --output-dir /tmp/pwps-agent-demo
```

### Local Guided Confirmation Web UI

```bash
uv run pwps-agent guided-confirm-web /path/to/pwps.json --host 127.0.0.1 --port 8765
```

Open:

```text
http://127.0.0.1:8765
```

## Output Files

Each successful run writes:

```text
pwps.json
pwps_draft.md
field_report.json
trace.json
evidence_index.json
```

`pwps.json` is the structured state. `pwps_draft.md` is the human-readable draft. `field_report.json` lists missing, candidate, confirmed, conflict, retained candidate, evidence, and risk information. `trace.json` records graph actions and tool results. `evidence_index.json` links evidence to fields and fields to evidence.

## Architecture

High-level architecture:

```text
LLM Supervisor Agent
  + Domain Skills
  + Runtime Tools
  + PWPSState
  + Knowledge Providers
  + LangGraph Runtime
```

Important modules:

- `src/pwps_agent/graph/`: LangGraph runtime, routing, checkpoints, nodes.
- `src/pwps_agent/core/`: contracts, field state, merge behavior, interaction services.
- `src/pwps_agent/tools/`: runtime tools for extraction, planning, evidence, local docs, sections, reports.
- `src/pwps_agent/knowledge/`: local document and web search providers.
- `src/pwps_agent/domain_skills/`: markdown guidance packages for the Supervisor.
- `src/pwps_agent/render/`: Markdown rendering.
- `src/pwps_agent/storage/`: run artifact persistence.
- `src/pwps_agent/web/`: lightweight guided confirmation Web UI/API.

Design docs:

- `docs/architecture.md`
- `docs/agent_design.md`
- `docs/requirements.md`
- `docs/data_schema.md`
- `docs/superpowers/plans/2026-05-24-stage-one-completion-roadmap.md`

## Development

Run focused tests:

```bash
uv run pytest tests/test_graph_auto_draft.py -q
uv run pytest tests/test_guided_confirmation_resume.py -q
uv run pytest tests/test_graph_supplement_update.py -q
```

Run full verification:

```bash
uv run pytest -q
uv run python -m compileall -q src tests
git diff --check
```

Current expected full test baseline:

```text
97 passed, 1 warning
```

## Project Status

Stage one is largely runnable but still in active development.

Remaining planned work:

- Phase 8: deterministic smoke harness and sample run scripts.
- Phase 9: production hardening for error handling, docs, configuration, and CLI polish.

See:

```text
docs/superpowers/plans/2026-05-24-stage-one-completion-roadmap.md
```
