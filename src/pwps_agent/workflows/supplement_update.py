from __future__ import annotations

from pydantic import BaseModel

from pwps_agent.config import Settings
from pwps_agent.core.contracts import AgentAction
from pwps_agent.core.state import PWPSState
from pwps_agent.graph.builder import build_auto_draft_graph
from pwps_agent.graph.checkpoints import load_latest_checkpoint
from pwps_agent.graph.state import GraphRuntimeContext
from pwps_agent.workflows.auto_draft import AutoDraftDependencies


class SupplementUpdateResult(BaseModel):
    state: PWPSState
    output_dir: str


class SupplementUpdatePlanner:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def plan_next_action(self, state: PWPSState) -> AgentAction:
        supplement_step = _last_node_index(state, "supplement_update")
        if supplement_step is None:
            return AgentAction(
                action_type="UPDATE_STATE",
                tool_args={
                    "operation": "supplement_update",
                    "supplement": str(self.payload["supplement"]),
                    "fields": dict(self.payload["fields"]),
                },
                rationale_summary="Apply supplemental user information to PWPSState.",
                expected_state_change="Merge supplement fields and preserve source evidence.",
            )

        compose_step = _last_node_index(state, "compose_draft")
        if compose_step is None or compose_step < supplement_step:
            return AgentAction(
                action_type="COMPOSE_DRAFT",
                rationale_summary="Re-compose draft after supplemental information.",
                expected_state_change="Persist updated draft and field report.",
            )

        return AgentAction(
            action_type="FINISH",
            rationale_summary="Supplement update has been merged and artifacts regenerated.",
            expected_state_change="Mark supplement update run as done.",
            stop_reason="supplement_update_complete",
        )


def resume_supplement_update(
    state: PWPSState,
    payload: dict,
    settings: Settings,
    dependencies: AutoDraftDependencies | None = None,
) -> SupplementUpdateResult:
    _validate_payload(payload)
    state = state.model_copy(deep=True)
    state.status = "running"
    deps = dependencies or AutoDraftDependencies(
        llm_client=object(),
        search_provider=object(),
    )
    graph = build_auto_draft_graph()
    result = graph.invoke(
        {
            "pwps_state": state,
            "context": GraphRuntimeContext(
                settings=settings,
                dependencies=deps,
                supervisor_planner=SupplementUpdatePlanner(payload),
                checkpoint_enabled=True,
            ),
        }
    )
    final_state = result["pwps_state"]
    return SupplementUpdateResult(
        state=final_state,
        output_dir=str(settings.paths.output_dir / final_state.run_id),
    )


def resume_supplement_update_from_checkpoint(
    run_id: str,
    payload: dict,
    settings: Settings,
    dependencies: AutoDraftDependencies | None = None,
) -> SupplementUpdateResult:
    state = load_latest_checkpoint(settings.paths.output_dir, run_id)
    return resume_supplement_update(
        state,
        payload,
        settings=settings,
        dependencies=dependencies,
    )


def _validate_payload(payload: dict) -> None:
    if not payload.get("supplement"):
        raise ValueError("Supplement update requires supplement text.")
    if not payload.get("fields"):
        raise ValueError("Supplement update requires at least one field.")


def _last_node_index(state: PWPSState, node: str) -> int | None:
    for index in range(len(state.trace) - 1, -1, -1):
        if state.trace[index].get("node") == node:
            return index
    return None
