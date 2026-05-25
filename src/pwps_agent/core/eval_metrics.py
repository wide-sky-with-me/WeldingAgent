from __future__ import annotations

from collections import Counter
from typing import Any

from pwps_agent.core.state import PWPSState


def compute_agent_metrics(state: PWPSState) -> dict[str, Any]:
    override_reasons = Counter()
    override_count = 0
    for entry in state.trace:
        if entry.get("event_type") != "agent_action_overridden":
            continue
        override_count += 1
        reason_code = (entry.get("payload") or {}).get("reason_code") or "unknown"
        override_reasons[str(reason_code)] += 1

    field_status_counts = Counter(field.status for field in state.fields.values())
    publishability_counts = Counter(
        field.publishability or "unknown" for field in state.fields.values()
    )
    confirmation_counts = Counter(record.action for record in state.confirmations)
    quality_report = state.quality_report or {}

    return {
        "run_id": state.run_id,
        "interaction_mode": state.interaction_mode,
        "final_status": state.status,
        "field_status_counts": dict(sorted(field_status_counts.items())),
        "publishability_counts": dict(sorted(publishability_counts.items())),
        "confirmation_counts": dict(sorted(confirmation_counts.items())),
        "weak_evidence_count": len(quality_report.get("weak_evidence_fields") or []),
        "override_count": override_count,
        "override_reason_counts": dict(sorted(override_reasons.items())),
        "refinement_attempts": state.refinement_attempts,
        "quality_level": quality_report.get("quality_level"),
        "recommended_action": quality_report.get("recommended_action"),
    }
