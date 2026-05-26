from __future__ import annotations

from pathlib import Path
from typing import Any

from pwps_agent.config import Settings
from pwps_agent.core.modes import build_confirmation_view
from pwps_agent.core.state import PWPSState
from pwps_agent.web.runtime_api import build_run_snapshot, save_run_state, serve_workbench
from pwps_agent.workflows.guided_confirmation import (
    apply_guided_confirmation_payload,
    resume_guided_confirmation,
    resume_guided_confirmation_from_checkpoint,
)


def web_state_payload(state: PWPSState) -> dict[str, Any]:
    return {
        **build_run_snapshot(state, Path(".") / state.run_id),
        "confirmation_view": build_confirmation_view(state),
    }


def apply_confirmation_payload(state: PWPSState, payload: dict[str, Any]) -> PWPSState:
    return apply_guided_confirmation_payload(state, payload)


def apply_resume_payload(state: PWPSState, payload: dict[str, Any]) -> dict[str, Any]:
    settings = Settings()
    if payload.get("output_dir"):
        settings.paths.output_dir = Path(str(payload["output_dir"]))
    result = resume_guided_confirmation(state, payload, settings=settings)
    return {"state": result.state, "output_dir": result.output_dir}


def apply_resume_run_payload(run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    settings = Settings()
    if payload.get("output_dir"):
        settings.paths.output_dir = Path(str(payload["output_dir"]))
    result = resume_guided_confirmation_from_checkpoint(
        run_id=run_id,
        payload=payload,
        settings=settings,
    )
    return {"state": result.state, "output_dir": result.output_dir}


def load_state(path: Path) -> PWPSState:
    return PWPSState.model_validate_json(path.read_text(encoding="utf-8"))


def save_state(path: Path, state: PWPSState) -> None:
    path.write_text(state.model_dump_json(indent=2), encoding="utf-8")


def serve_guided_confirmation(
    state_path: Path,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> None:
    state = load_state(state_path)
    base_output_dir = _base_output_dir_for_state_path(state_path, state)
    save_run_state(base_output_dir, state)
    serve_workbench(base_output_dir, host=host, port=port)


def _base_output_dir_for_state_path(state_path: Path, state: PWPSState) -> Path:
    if state_path.name == "pwps.json" and state_path.parent.name == state.run_id:
        return state_path.parent.parent
    return state_path.parent
