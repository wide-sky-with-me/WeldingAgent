# LLM Supervisor Planner Design

## Scope

Add the smallest replaceable Supervisor planning seam for the existing
LangGraph auto-draft graph. The graph must still run deterministically by
default, while allowing tests and future runtime wiring to inject an
LLM-backed planner that emits the same `AgentAction` contract.

This slice does not add guided-confirmation routing, checkpoint recovery,
interactive user turns, or full autonomous tool selection beyond the existing
auto-draft graph nodes.

## Architecture

`GraphRuntimeContext` gains an optional `supervisor_planner`. The supervisor
node delegates action selection to that planner when present; otherwise it uses
the current deterministic auto-draft planner. This keeps current tests and CLI
behavior stable while creating the LLM replacement point.

The new `LLMSupervisorPlanner` builds a compact prompt from:

- current `PWPSState` summary;
- ordered Domain Skill context;
- supported action/tool names for the current graph;
- safety constraints around draft/candidate wording and no invented metadata.

It calls the existing structured-output client helper with the shared
`AgentAction` Pydantic schema, so action shape remains centralized.

## Data Flow

```text
GraphRuntimeContext
  -> supervisor_node
  -> supervisor_planner.plan_next_action(state)
  -> AgentAction
  -> route_action
```

The LLM planner only chooses the next action. Runtime tool execution remains in
`graph/nodes.py`, and state mutation remains traceable through existing node
outputs.

## Testing

Tests use fake planners and fake structured clients. They must not call a live
LLM or web provider.

Verification commands:

```text
uv run pytest tests/test_graph_supervisor_planner.py -v
uv run pytest -q
```
