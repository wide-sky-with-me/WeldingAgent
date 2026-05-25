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
    if state.quality_report:
        (run_dir / "quality_report.json").write_text(
            json.dumps(state.quality_report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    (run_dir / "trace.json").write_text(
        json.dumps(state.trace, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (run_dir / "evidence_index.json").write_text(
        json.dumps(_build_evidence_index(state), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return run_dir


def _to_json(model: BaseModel) -> str:
    return model.model_dump_json(indent=2)


def _build_evidence_index(state: PWPSState) -> dict[str, Any]:
    evidence_to_fields: dict[str, set[str]] = {}
    field_to_evidence: dict[str, set[str]] = {}
    for field_id, field in state.fields.items():
        evidence_ids = set(field.evidence_ids)
        for candidate in field.candidates:
            evidence_ids.update(candidate.get("evidence_ids", []))
        for evidence_id in evidence_ids:
            if not evidence_id:
                continue
            evidence_to_fields.setdefault(evidence_id, set()).add(field_id)
            field_to_evidence.setdefault(field_id, set()).add(evidence_id)

    return {
        "run_id": state.run_id,
        "search_context": {
            "queries": state.knowledge_queries,
            "results": state.search_results,
        },
        "evidence": [item.model_dump() for item in state.evidence],
        "evidence_to_fields": {
            evidence_id: sorted(fields) for evidence_id, fields in sorted(evidence_to_fields.items())
        },
        "field_to_evidence": {
            field_id: sorted(evidence_ids)
            for field_id, evidence_ids in sorted(field_to_evidence.items())
        },
    }
