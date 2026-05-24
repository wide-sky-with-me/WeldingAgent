# Supervisor Checkpoint And Resume Design

## Scope

Add reliable runtime observability and recovery points for the current
LangGraph auto-draft path. The Supervisor must log every action decision, graph
runtime nodes must persist resumable checkpoints, and tests must cover the
Supervisor path.

This slice does not add a user-facing resume CLI yet. It adds the repo-level
runtime helpers needed for a later CLI command.

## Design

Supervisor logging stays in `supervisor_node`: every planned `AgentAction` is
recorded in `state.actions` and `state.trace`.

Checkpointing is handled by a new `graph/checkpoints.py` module. Checkpoints are
stored under:

```text
<output_dir>/<run_id>/checkpoints/
  0001-<node>.json
  latest.json
```

Only safe resume points are checkpointed by default: tool nodes, compose, and
finish. Supervisor-only checkpoints are avoided because they contain a pending
action that has not executed yet; resuming from those can duplicate the same
Supervisor decision.

`GraphRuntimeContext` owns runtime controls:

- `checkpoint_enabled`: persist checkpoint files after safe nodes.
- `interrupt_after_steps`: stop after N checkpointed runtime steps.

When interruption triggers, the node marks the state as `interrupted`, writes an
`interrupt` trace event, persists the checkpoint, and router sends the graph to
`END`. Loading a checkpoint for resume resets `interrupted` back to `running`
and clears no completed trace.

## Testing

Tests use deterministic fake tools and do not call live LLM or web providers.

Required verification:

```text
uv run pytest tests/test_graph_checkpoint_resume.py -v
uv run pytest tests/test_graph_supervisor_planner.py -v
uv run pytest -q
```
