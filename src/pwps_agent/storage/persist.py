from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from pwps_agent.core.state import PWPSState


def persist_run_artifacts(
    state: PWPSState,
    draft_markdown: str,
    field_report: dict[str, Any],
    output_root: Path,
) -> Path:
    run_dir = output_root / state.run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    (run_dir / "pwps.json").write_text(
        _to_json(state),
        encoding="utf-8",
    )
    (run_dir / "pwps_draft.md").write_text(draft_markdown, encoding="utf-8")
    (run_dir / "field_report.json").write_text(
        json.dumps(field_report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (run_dir / "trace.json").write_text(
        json.dumps(state.trace, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return run_dir


def _to_json(model: BaseModel) -> str:
    return model.model_dump_json(indent=2)
