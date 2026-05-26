# Interaction Adapters And Web Workbench Design

## Scope

Refactor user interaction so `auto_draft` and `guided_confirmation` remain the
only user-facing running modes, while CLI terminal and React Web become
transport adapters above the same runtime interaction protocol.

This design replaces the current browser flow that is embedded as a Python HTML
string in `src/pwps_agent/web/guided_confirmation.py`. It also prevents the CLI
from becoming a special second workflow. CLI and Web must both consume
`PWPSState.pending_interaction`, submit user responses through the same resume
boundary, and let the graph continue.

The system must treat model output and user input asymmetrically:

- Model-facing and user-facing agent output must be structured, readable, and
  task-oriented.
- User input may be incomplete, informal, mixed-language, or ambiguous.
- Ambiguous user input should be normalized when possible, and otherwise lead to
  another focused runtime interaction request.

## Product Modes

The project has two primary modes.

### `auto_draft`

`auto_draft` is the low-interaction drafting mode. It should ask during runtime
only when the minimum startup context is insufficient. Once enough startup
context exists, it should continue through retrieval, reasoning, verification,
and draft composition with visible uncertainty.

Examples of valid startup follow-up:

- Missing base material.
- Missing thickness or wall thickness.
- Missing workpiece type when pipe-specific fields may matter.
- Missing welding process or joint type.

After retrieval or reasoning starts, unresolved values should be represented as
missing, candidate, suggested, weak-evidence, or risk entries rather than
turning `auto_draft` into a guided session.

### `guided_confirmation`

`guided_confirmation` is the human-in-the-loop mode. The agent gathers and
organizes evidence, recommends options, explains suitability and risk, and asks
the user to confirm critical fields. User-confirmed values become
`user_confirmed`; agent-derived values do not.

Critical choices include welding process, base material applicability, joint
type, welding position, filler material, shielding gas, polarity, core
parameter ranges, preheat/interpass assumptions, and PWHT assumptions when
relevant.

## Interaction Protocol

`PWPSState.pending_interaction` is the single runtime pause contract. It must be
usable by CLI, Web, and future API clients without changing graph semantics.

The protocol should evolve from the current `InteractionRequest` shape into a
more explicit contract:

```text
InteractionRequest
  request_id
  interaction_mode
  purpose
  title
  summary
  assistant_message
  questions[]
  expected_response
  allow_partial
  transport_neutral
```

`assistant_message` is the polished user-facing explanation generated or
assembled for the adapter. It should be concise and ordered:

1. What is blocked or needs confirmation.
2. What the agent currently understands.
3. What options or references are available.
4. What the user can answer now.

`questions[]` remains structured and machine-readable:

```text
InteractionQuestion
  question_id
  field_ids
  prompt
  input_kind
  required
  options[]
  missing_reason
  ambiguity_note
```

`options[]` should support recommendation UI:

```text
InteractionOption
  value
  label
  suitability
  risk_note
  recommended
  evidence_ids
  field_updates
```

The protocol is not tied to terminal prompts, HTML controls, or React
components.

## User Response Normalization

Adapters should not require users to answer as perfect `field=value` payloads.
They should accept free-form text and convert it into a structured
`InteractionResponse` before resuming the graph:

```text
InteractionResponse
  request_id
  fields
  selected_options
  message
  reason
  evidence_ids_shown
  action
  unresolved_text
```

Normalization is a runtime tool boundary, not a UI trick. A new interaction
normalizer should:

- Accept a free-form user message plus the current `InteractionRequest`.
- Prefer deterministic parsing for option numbers, exact option labels, and
  explicit `field=value` pairs.
- Use an LLM-backed structured parser when the user writes informal text such as
  "12mm Q355B plate, gas shielded MIG, flat butt joint".
- Preserve the original user text as evidence.
- Return a follow-up interaction request when required fields are still missing
  or values conflict.

The normalizer must not invent missing project metadata. It may infer field
candidates only when the user text or selected option supports them.

## Runtime Flow

The graph remains the owner of state transitions:

```text
run_graph_draft
  -> graph action loop
  -> ask_user node attaches pending_interaction
  -> adapter displays request
  -> adapter collects raw response
  -> normalizer creates InteractionResponse
  -> resume_interaction applies response
  -> graph action loop continues
```

Adapters may block, poll, stream, or render UI, but they must not decide field
promotion rules. Field status changes happen through `resume_interaction()` and
the existing state merge/confirmation logic.

## CLI Adapter

The CLI is the terminal adapter for the shared protocol.

Responsibilities:

- Run `draft`, `auto-draft`, or `guided-draft`.
- If the graph pauses and `stdin.isatty()` is true, render the interaction
  request in terminal-friendly text.
- Show option numbers, recommendation markers, suitability, risk notes, and
  target fields.
- Accept option number, exact value, `field=value` pairs, or free-form text.
- Normalize input and call `resume_interaction()` in the same process.
- Continue until the graph finishes, fails, or reaches a non-terminal
  non-interactive pause.

Non-TTY behavior remains script-friendly. If stdin is not interactive, the CLI
should persist the paused state and print the output directory/status instead of
blocking.

The CLI implementation should move display and parsing helpers out of
`src/pwps_agent/cli.py` into focused adapter modules so CLI command routing does
not own interaction semantics.

## React Web Workbench

The new Web UI is a mixed workbench, not a simple confirmation page.

Layout:

- Top bar: run id, mode selector, status, output directory, provider status.
- Main center: current interaction task with the assistant message, required
  questions, free-form input, and option controls.
- Left rail or upper activity area: runtime steps and recent agent events.
- Right panel: field status grouped by pWPS section, with status chips and
  confidence/source indicators.
- Draft panel: Markdown draft preview when available, with missing/candidate
  markers visible.
- Evidence drawer: evidence snippets linked from options and field rows.
- Confirmation history: accepted, modified, skipped, and rolled back decisions.

The Web UI should support both modes:

- In `auto_draft`, show a compact startup form when the minimum context is
  missing, then switch to progress/draft view.
- In `guided_confirmation`, show recommendation cards and confirmation controls
  for each pending interaction.

The UI should never require the user to understand internal state names. It may
show field ids in secondary text for debugging, but primary labels should use
domain-friendly Chinese labels.

## Web Backend API

Replace the old `guided-confirm-web` server with a small API that serves the
React app and exposes runtime operations.

Required endpoints:

```text
GET  /api/runs/{run_id}
POST /api/runs
POST /api/runs/{run_id}/respond
POST /api/runs/{run_id}/supplement
GET  /api/runs/{run_id}/artifacts/pwps.json
GET  /api/runs/{run_id}/artifacts/pwps_draft.md
```

The API payload for `/respond` should accept raw user text, selected option
ids/numbers, and optional explicit fields. The backend normalizes the payload
against the current `pending_interaction`, applies it through
`resume_interaction()`, persists state, and returns the updated run snapshot.

The first implementation may use Python's standard HTTP server to avoid adding
backend dependencies, but the interface should be shaped so it can move to
FastAPI later without changing the React client contract.

## Frontend Project Shape

Add a real frontend project instead of embedding HTML in Python strings:

```text
web/
  package.json
  index.html
  src/
    app/
      App.tsx
      api.ts
      types.ts
    components/
      RunHeader.tsx
      InteractionPanel.tsx
      FieldStatusPanel.tsx
      DraftPreview.tsx
      EvidenceDrawer.tsx
      EventTimeline.tsx
      ConfirmationHistory.tsx
    styles/
      app.css
```

The first version should use React with Vite, TypeScript, and plain CSS. The UI
should be dense, operational, and domain-specific rather than a marketing page.
It should not use cards inside cards, oversized hero sections, or decorative
generic gradients. The primary screen is the pWPS workbench.

## Deprecation Strategy

`src/pwps_agent/web/guided_confirmation.py` should be treated as legacy.

Migration steps:

1. Keep state load/save helpers if still useful, but move generic helpers out of
   the guided-only module.
2. Replace `render_guided_confirmation_html()` with a static React app serving
   path.
3. Replace guided-only resume endpoints with mode-neutral interaction endpoints.
4. Keep `pwps-agent guided-confirm-web` only as a compatibility alias that
   starts the new workbench for an existing run or state path.
5. Update tests so they assert API payload shape and static asset serving rather
   than searching for text inside embedded HTML.

## Error Handling

Interaction errors should be user-actionable:

- Missing required fields: return a new focused interaction request.
- Ambiguous answer: ask a narrower follow-up and show what was understood.
- Invalid option number: explain valid choices.
- Provider or graph failure: preserve trace and show the run status as failed.
- Non-interactive CLI pause: persist artifacts and print resume instructions.

The Web UI should show errors near the current interaction panel and keep the
field/draft panels visible when possible.

## Testing

Backend tests:

```text
tests/test_interaction_normalizer.py
tests/test_cli_interaction_adapter.py
tests/test_web_runtime_api.py
```

Frontend tests should at least include build verification:

```text
pnpm install
pnpm test
pnpm build
```

Repository verification:

```text
uv run pytest tests/test_interaction_resume.py tests/test_interaction_gates.py tests/test_cli.py tests/test_web_runtime_api.py -q
uv run pytest -q
uv run python -m compileall -q src tests
git diff --check
```

## Acceptance Criteria

- `auto_draft` and `guided_confirmation` remain runtime modes; CLI and Web are
  adapters above them.
- CLI can continue an interactive run in the same command after a graph pause.
- CLI accepts free-form text as well as structured field values.
- Web UI is a React workbench with mode selection, current interaction,
  recommendation options, field state, evidence, confirmation history, and draft
  preview.
- Web API accepts raw user responses and normalizes them before graph resume.
- Old embedded guided-confirmation HTML is no longer the primary Web UI.
- Model/user-facing assistant messages are ordered and readable; user input is
  allowed to be messy and may trigger additional focused follow-up requests.
