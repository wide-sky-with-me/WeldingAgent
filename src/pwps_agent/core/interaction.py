from __future__ import annotations

from pwps_agent.core.state import PWPSState


MINIMUM_AUTO_DRAFT_FIELDS = [
    "base_material",
    "thickness",
    "workpiece_type",
    "welding_process",
    "joint_type",
    "welding_position",
]


def missing_minimum_auto_draft_fields(state: PWPSState) -> list[str]:
    missing: list[str] = []
    for field_id in MINIMUM_AUTO_DRAFT_FIELDS:
        field = state.fields.get(field_id)
        if field is None or field.value in (None, ""):
            missing.append(field_id)
            continue
        if field.status not in {"filled", "user_confirmed"}:
            missing.append(field_id)
    return missing


def should_interrupt_for_initial_info(state: PWPSState) -> bool:
    if state.interaction_mode != "auto_draft":
        return False
    if _workflow_started(state):
        return False
    return bool(missing_minimum_auto_draft_fields(state))


def _workflow_started(state: PWPSState) -> bool:
    return any(entry.get("node") != "supervisor" for entry in state.trace)
