# LangGraph Supervisor Loop Design

## Scope

Build the smallest LangGraph runtime slice that moves the existing `auto_draft`
application service toward the target architecture without breaking the current
CLI behavior.

This slice introduces graph modules and a deterministic supervisor plan for the
existing auto-draft path. It does not attempt full autonomous multi-turn
reasoning, checkpoint recovery, guided confirmation dialogue, or domain-skill
selection yet.

## Architecture

The first graph will wrap the existing tool sequence:

```text
START
  -> supervisor
  -> route_action
  -> call_tool / compose_draft / finish
  -> supervisor
  -> END
```

The supervisor node will emit one `AgentAction` at a time based on state and
trace progress. This keeps the first implementation deterministic and testable
while preserving the same `AgentAction` shape that a future LLM Supervisor can
produce. Runtime tool nodes will call the existing requirement understanding,
knowledge planning, web search, evidence conversion, field reasoning, rendering,
and persistence components.

The graph owns orchestration only. It must not introduce welding business rules,
invent project metadata, or weaken field source/status/confidence tracking.

## Components

- `src/pwps_agent/graph/state.py`: graph dependency bundle and graph state type.
- `src/pwps_agent/graph/supervisor.py`: deterministic supervisor action planner
  for the current auto-draft graph.
- `src/pwps_agent/graph/router.py`: maps `AgentAction` to node names.
- `src/pwps_agent/graph/nodes.py`: executes runtime tool actions and draft
  composition.
- `src/pwps_agent/graph/builder.py`: builds and compiles the LangGraph graph.
- `tests/test_graph_auto_draft.py`: verifies routing and end-to-end graph
  artifacts using deterministic dependencies.

## Data Flow

The graph starts from a `PWPSState` created by `create_initial_state()`.
Dependencies are passed through a small `GraphRuntimeContext` object so tests can
inject fake LLM and search components. Each node returns an updated state object
or a state patch compatible with LangGraph invocation.

The minimal action order is:

1. `CALL_TOOL requirement_understanding`
2. `CALL_TOOL knowledge_planning`
3. `CALL_TOOL web_search`
4. `CALL_TOOL field_reasoning`
5. `COMPOSE_DRAFT`
6. `FINISH`

## Error Handling

Tool failures should be recorded in trace and set state status to `failed` for
this slice. Provider and LLM exceptions should not be swallowed silently. The
existing CLI can continue to use the application service until a later task wires
the graph into CLI runtime.

## Testing

Tests must use deterministic fake dependencies, not live web or live LLM calls.
The first tests should fail before graph code exists, then pass after the
minimal graph implementation.

Verification commands:

```text
uv run pytest tests/test_graph_auto_draft.py -v
uv run pytest -q
```
