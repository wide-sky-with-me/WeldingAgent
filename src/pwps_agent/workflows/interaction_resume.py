from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from pwps_agent.config import Settings
from pwps_agent.core.contracts import Evidence
from pwps_agent.core.publishability import publishability_for_field
from pwps_agent.core.state import PWPSState
from pwps_agent.graph.builder import build_auto_draft_graph
from pwps_agent.graph.policy import plan_next_auto_draft_action
from pwps_agent.graph.state import GraphRuntimeContext
from pwps_agent.workflows.auto_draft import AutoDraftDependencies, _build_dependencies
from pwps_agent.workflows.guided_confirmation import apply_guided_confirmation_payload
from pwps_agent.workflows.guided_confirmation import GuidedConfirmationResumePlanner


class InteractionResumeResult(BaseModel):
    state: PWPSState
    output_dir: str


class AutoDraftInteractionResumePlanner:
    def __init__(self, knowledge_sources: list[str]) -> None:
        self.knowledge_sources = knowledge_sources

    def plan_next_action(self, state: PWPSState):
        return plan_next_auto_draft_action(state, self.knowledge_sources)


def apply_interaction_payload(state: PWPSState, payload: dict[str, Any]) -> PWPSState:
    purpose = _pending_interaction_purpose(state)
    if purpose == "guided_field_confirmation":
        updated = apply_guided_confirmation_payload(state, payload)
        updated.status = "running"
        updated.pending_interaction = None
        return updated
    if purpose == "initial_minimum_context":
        return _apply_initial_info_payload(state, payload)
    raise ValueError(f"Unsupported interaction purpose: {purpose}")


def resume_interaction(
    state: PWPSState,
    payload: dict[str, Any],
    settings: Settings,
    dependencies: AutoDraftDependencies | None = None,
) -> InteractionResumeResult:
    if state.status != "need_user_input":
        raise ValueError("interaction resume requires state.status == need_user_input")

    updated = apply_interaction_payload(state, payload)
    deps = dependencies or _build_dependencies(settings)
    planner = (
        GuidedConfirmationResumePlanner()
        if updated.interaction_mode == "guided_confirmation"
        else AutoDraftInteractionResumePlanner(settings.knowledge.sources)
    )
    result = build_auto_draft_graph().invoke(
        {
            "pwps_state": updated,
            "context": GraphRuntimeContext(
                settings=settings,
                dependencies=deps,
                supervisor_planner=planner,
                checkpoint_enabled=True,
            ),
        }
    )
    final_state = result["pwps_state"]
    return InteractionResumeResult(
        state=final_state,
        output_dir=str(settings.paths.output_dir / final_state.run_id),
    )


def _apply_initial_info_payload(
    state: PWPSState,
    payload: dict[str, Any],
) -> PWPSState:
    field_values = dict(payload.get("fields", {}))
    if not field_values:
        raise ValueError("Initial information payload must include fields.")

    updated = state.model_copy(deep=True)
    user_message = str(payload.get("message") or "User supplied initial welding context.")
    evidence_id = f"ev_user_interaction_{len(updated.evidence) + 1}"
    updated.evidence.append(
        Evidence(
            evidence_id=evidence_id,
            source_type="user_input",
            content=user_message,
            related_fields=list(field_values),
            source_tier="user",
            reliability="high",
            confidence="high",
        )
    )
    for field_id, value in field_values.items():
        if field_id not in updated.fields:
            continue
        field = updated.fields[field_id]
        field.value = value
        field.status = "filled"
        field.confidence = "high"
        field.source = {"type": "user_input", "ref": evidence_id}
        if evidence_id not in field.evidence_ids:
            field.evidence_ids.append(evidence_id)
        field.confirmation = {
            "required": False,
            "confirmed": False,
            "source": "initial_info_interaction",
        }
        field.publishability = publishability_for_field(field)

    updated.status = "running"
    updated.pending_interaction = None
    updated.trace.append(
        {
            "step": len(updated.trace) + 1,
            "node": "interaction_resume",
            "event_type": "state_update",
            "summary": "Applied runtime interaction payload.",
            "payload": {
                "purpose": "initial_minimum_context",
                "field_ids": list(field_values),
                "created_at": datetime.now(UTC).isoformat(),
            },
        }
    )
    return updated


def _pending_interaction_purpose(state: PWPSState) -> str:
    pending = state.pending_interaction or {}
    purpose = pending.get("purpose")
    if isinstance(purpose, str):
        return purpose
    if state.interaction_mode == "guided_confirmation":
        return "guided_field_confirmation"
    if state.interaction_mode == "auto_draft":
        return "initial_minimum_context"
    return ""
