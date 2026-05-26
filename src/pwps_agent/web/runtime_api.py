from __future__ import annotations

from pathlib import Path
from typing import Any

from pwps_agent.config import Settings
from pwps_agent.core.state import PWPSState
from pwps_agent.interaction.normalizer import normalize_interaction_response
from pwps_agent.render.markdown import render_field_report
from pwps_agent.workflows.interaction_resume import resume_interaction


def build_run_snapshot(state: PWPSState, output_dir: Path) -> dict[str, Any]:
    return {
        "run_id": state.run_id,
        "mode": state.interaction_mode,
        "interaction_mode": state.interaction_mode,
        "status": state.status,
        "pending_interaction": state.pending_interaction,
        "interaction_requests": list(state.interaction_requests),
        "fields": {
            field_id: field.model_dump()
            for field_id, field in state.fields.items()
        },
        "field_report": state.field_report or render_field_report(state),
        "quality_report": state.quality_report,
        "confirmations": [record.model_dump() for record in state.confirmations],
        "trace": list(state.trace),
        "has_draft": bool(state.draft_markdown),
        "draft_markdown": state.draft_markdown,
        "output_dir": str(output_dir),
    }


def save_run_state(base_output_dir: Path, state: PWPSState) -> Path:
    run_dir = base_output_dir / state.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    state_path = run_dir / "pwps.json"
    state_path.write_text(state.model_dump_json(indent=2), encoding="utf-8")
    return state_path


def load_run_state(base_output_dir: Path, run_id: str) -> PWPSState:
    state_path = base_output_dir / run_id / "pwps.json"
    return PWPSState.model_validate_json(state_path.read_text(encoding="utf-8"))


def apply_run_response(
    base_output_dir: Path,
    run_id: str,
    payload: dict[str, Any],
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or Settings()
    settings.paths.output_dir = base_output_dir
    state = load_run_state(base_output_dir, run_id)
    response = normalize_interaction_response(
        state.pending_interaction or {},
        str(payload.get("message") or ""),
        explicit_fields=payload.get("fields"),
    )
    result = resume_interaction(state, response, settings=settings)
    save_run_state(base_output_dir, result.state)
    return build_run_snapshot(result.state, Path(result.output_dir))
