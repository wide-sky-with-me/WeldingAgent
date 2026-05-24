from __future__ import annotations

from pydantic import BaseModel

from pwps_agent.config import Settings
from pwps_agent.core.contracts import AgentAction
from pwps_agent.core.modes import confirm_fields, edit_confirmation, rollback_confirmation
from pwps_agent.core.state import PWPSState
from pwps_agent.graph.builder import build_auto_draft_graph
from pwps_agent.graph.checkpoints import load_latest_checkpoint
from pwps_agent.graph.state import GraphRuntimeContext
from pwps_agent.workflows.auto_draft import AutoDraftDependencies


class GuidedConfirmationResumeResult(BaseModel):
    state: PWPSState
    output_dir: str


class GuidedConfirmationResumePlanner:
    def plan_next_action(self, state: PWPSState) -> AgentAction:
        completed_nodes = {entry.get("node") for entry in state.trace}
        if _has_pending_confirmation_fields(state):
            return AgentAction(
                action_type="ASK_USER",
                rationale_summary="Additional candidate fields still need user confirmation.",
                expected_state_change="Pause with the next grouped confirmation view.",
            )
        if "compose_draft" not in completed_nodes:
            return AgentAction(
                action_type="COMPOSE_DRAFT",
                rationale_summary="Compose draft after user guided-confirmation input.",
                expected_state_change="Persist draft/report artifacts from confirmed state.",
            )
        return AgentAction(
            action_type="FINISH",
            rationale_summary="Guided-confirmation resume has produced artifacts.",
            expected_state_change="Mark run as done.",
            stop_reason="guided_confirmation_resume_complete",
        )


def apply_guided_confirmation_payload(
    state: PWPSState,
    payload: dict,
) -> PWPSState:
    operation = str(payload.get("operation", "confirm"))
    if operation == "rollback":
        return rollback_confirmation(
            state,
            confirmation_id=str(payload["confirmation_id"]),
            user_message=str(payload.get("message") or "Rollback confirmation."),
            reason=payload.get("reason"),
        )

    field_values = dict(payload.get("fields", {}))
    if not field_values:
        raise ValueError("Confirmation payload must include fields.")

    common = {
        "field_values": field_values,
        "user_message": str(payload.get("message") or "User confirmation."),
        "rationale_shown": payload.get("rationale_shown"),
        "evidence_ids_shown": list(payload.get("evidence_ids_shown", [])),
        "user_rationale": payload.get("reason"),
    }
    if operation == "edit":
        return edit_confirmation(
            state,
            confirmation_id=str(payload["confirmation_id"]),
            **common,
        )
    return confirm_fields(
        state,
        action=str(payload.get("action", "modified")),
        **common,
    )


def resume_guided_confirmation(
    state: PWPSState,
    payload: dict,
    settings: Settings,
    dependencies: AutoDraftDependencies | None = None,
) -> GuidedConfirmationResumeResult:
    if state.status != "need_user_input":
        raise ValueError("guided_confirmation resume requires state.status == need_user_input")

    updated = apply_guided_confirmation_payload(state, payload)
    updated.status = "running"
    updated.trace.append(
        {
            "step": len(updated.trace) + 1,
            "node": "guided_confirmation_resume",
            "event_type": "state_update",
            "summary": "Applied user confirmation payload and resumed draft generation.",
            "payload": {
                "confirmation_id": updated.confirmations[-1].confirmation_id,
                "field_ids": updated.confirmations[-1].field_ids,
            },
        }
    )
    deps = dependencies or AutoDraftDependencies(
        llm_client=object(),
        search_provider=object(),
    )
    graph = build_auto_draft_graph()
    result = graph.invoke(
        {
            "pwps_state": updated,
            "context": GraphRuntimeContext(
                settings=settings,
                dependencies=deps,
                supervisor_planner=GuidedConfirmationResumePlanner(),
                checkpoint_enabled=True,
            ),
        }
    )
    final_state = result["pwps_state"]
    return GuidedConfirmationResumeResult(
        state=final_state,
        output_dir=str(settings.paths.output_dir / final_state.run_id),
    )


def resume_guided_confirmation_from_checkpoint(
    run_id: str,
    payload: dict,
    settings: Settings,
    dependencies: AutoDraftDependencies | None = None,
) -> GuidedConfirmationResumeResult:
    state = load_latest_checkpoint(settings.paths.output_dir, run_id)
    return resume_guided_confirmation(
        state,
        payload,
        settings=settings,
        dependencies=dependencies,
    )


def _has_pending_confirmation_fields(state: PWPSState) -> bool:
    return any(
        field.status in {"candidate", "need_confirmation"}
        for field in state.fields.values()
    )
