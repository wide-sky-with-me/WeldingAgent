from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pwps_agent.core.state import PWPSState


def save_checkpoint(
    state: PWPSState,
    output_root: Path,
    node_name: str,
) -> Path:
    checkpoint_dir = output_root / state.run_id / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    step = state.step_count
    filename = f"{step:04d}-{node_name}.json"
    payload = {
        "run_id": state.run_id,
        "node": node_name,
        "step_count": step,
        "state": json.loads(state.model_dump_json()),
    }
    path = checkpoint_dir / filename
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    latest = checkpoint_dir / "latest.json"
    latest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_latest_checkpoint(
    output_root: Path,
    run_id: str,
    resume: bool = False,
) -> PWPSState:
    latest = output_root / run_id / "checkpoints" / "latest.json"
    payload: dict[str, Any] = json.loads(latest.read_text(encoding="utf-8"))
    state = PWPSState.model_validate(payload["state"])
    if resume and state.status == "interrupted":
        state.status = "running"
    return state
