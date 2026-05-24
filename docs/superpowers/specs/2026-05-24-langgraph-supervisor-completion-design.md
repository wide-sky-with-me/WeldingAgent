# LangGraph Supervisor Completion Design

## Scope

Complete the middle-stage LangGraph/Supervisor runtime enough to make actions,
routing, retry, and state merging explicit and testable. The goal is to move
away from hidden linear workflow behavior while keeping the current `auto_draft`
vertical slice stable.

This stage does not add a full interactive UI, real asynchronous web execution,
or formal welding rule validation.

## Architecture

The graph remains the orchestration boundary. The Supervisor chooses one
`AgentAction`; router nodes decide where that action goes; runtime nodes execute
tools or compose artifacts; state merge code applies tool patches with explicit
priority and conflict behavior.

The current deterministic auto-draft planner remains a fallback. LLM-backed
planning can use the same graph path because action execution is now explicit.

## Components

- `core/state_merge.py`: canonical merge engine for `PWPSState` patches.
- `workflows/auto_draft.py`: compatibility wrapper delegates to merge engine.
- `graph/router.py`: routes Supervisor actions and post-tool retry outcomes.
- `graph/nodes.py`: records action execution results, catches tool errors, and
  leaves retry decisions to the router.
- `graph/state.py`: graph runtime options such as max retry count.

## Action And Retry Semantics

Every Supervisor-selected action is appended to `state.actions` and trace. Every
runtime node writes a trace item containing action type, tool name when present,
success, attempt number, and retryability.

Tool retry is graph-level behavior:

1. `CALL_TOOL` routes to `call_tool`.
2. `call_tool` executes one tool action and records success or failure.
3. `route_after_tool` sends successful tools back to `supervisor`.
4. Retryable failed tools route back to `call_tool` until the configured retry
   limit is reached.
5. Exhausted failures mark state `failed` and route to `finish`.

For this slice, retry is sequential and deterministic. Parallel query execution
is represented as per-query trace and partial failure records inside the
`web_search` tool branch; true async execution can be added later without
changing the trace shape.

## State Merge Semantics

The merge engine accepts only known patch keys. Unknown top-level keys and
unknown field IDs are not fatal, but they are recorded in trace as merge
warnings.

Field merge priority:

1. `user_confirmed`
2. user-origin `filled`
3. other `filled`
4. `candidate`, `suggested`, `need_confirmation`
5. `missing`

Lower-priority incoming values do not overwrite higher-priority field values.
They are preserved as candidates with evidence IDs and timestamp metadata.
Same-or-higher-priority incoming values may update the field. Evidence,
knowledge queries, and search results are appended with ID-based de-duplication.

## Testing

Tests must use deterministic fake tools and no live web or LLM calls.

Verification commands:

```text
uv run pytest tests/test_state_merge.py -v
uv run pytest tests/test_graph_retry.py -v
uv run pytest -q
```
