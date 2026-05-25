from __future__ import annotations

from typing import Any

from pwps_agent.core.fields import FIELD_DEFINITIONS
from pwps_agent.core.state import PWPSState


SECTION_TITLES = {
    "A": "文件与项目元信息",
    "B": "焊接适用范围",
    "C": "焊材与辅助材料",
    "D": "焊接参数",
    "E": "热处理与温控",
}


def render_pwps_draft(state: PWPSState) -> str:
    lines = [
        "# pWPS 草案",
        "",
        "> 本文件为 pWPS draft，不代表正式合规、签发或批准结论。",
        "",
        f"- 运行模式: `{state.interaction_mode}`",
        "",
    ]

    for index, section in enumerate(["A", "B", "C", "D", "E"], start=1):
        section_payload = state.sections.get(section)
        if section_payload:
            lines.extend(_render_structured_section(index, section, section_payload))
        else:
            lines.extend(_render_state_section(index, section, state))

    lines.append("## 6. 待确认项与风险提示")
    lines.append("")
    unresolved = [
        field
        for field in state.fields.values()
        if field.status in {"missing", "candidate", "suggested", "need_confirmation", "conflict"}
    ]
    if not unresolved:
        lines.append("- 当前字段均已填写或确认。")
    else:
        for field in unresolved:
            lines.append(f"- `{field.field_id}` {field.label}: {field.status}")
    lines.append("")
    return "\n".join(lines)


def _render_structured_section(index: int, section: str, payload: object) -> list[str]:
    section_payload = payload if isinstance(payload, dict) else {}
    lines = [
        f"## {index}. {section_payload.get('title') or SECTION_TITLES[section]}",
        "",
        "| 字段 | 值 | 状态 | 说明 |",
        "|---|---|---|---|",
    ]
    for item in section_payload.get("fields", []):
        if not isinstance(item, dict):
            continue
        note_parts = [f"confidence={item.get('confidence', 'unknown')}"]
        evidence_ids = item.get("evidence_ids") or []
        if evidence_ids:
            note_parts.append(f"evidence={','.join(evidence_ids)}")
        if item.get("note"):
            note_parts.append(str(item["note"]))
        lines.append(
            f"| {item.get('label', item.get('field_id', ''))} | "
            f"{item.get('value', '待确认')} | "
            f"`{item.get('status', 'missing')}` | "
            f"{'; '.join(note_parts)} |"
        )
    lines.append("")
    return lines


def _render_state_section(index: int, section: str, state: PWPSState) -> list[str]:
    lines = [
        f"## {index}. {SECTION_TITLES[section]}",
        "",
        "| 字段 | 值 | 状态 | 说明 |",
        "|---|---|---|---|",
    ]
    for field_id, _label in FIELD_DEFINITIONS[section]:
        field = state.fields[field_id]
        value = "待确认" if field.value in (None, "") else str(field.value)
        note = field.note or ""
        lines.append(f"| {field.label} | {value} | `{field.status}` | {note} |")
    lines.append("")
    return lines


def render_field_report(state: PWPSState) -> dict[str, Any]:
    missing = []
    candidate = []
    suggested = []
    user_confirmed = []
    conflict = []
    retained_candidates = {}

    for field in state.fields.values():
        if field.status == "missing":
            missing.append(field.field_id)
        elif field.status == "candidate":
            candidate.append(field.field_id)
        elif field.status == "suggested":
            suggested.append(field.field_id)
        elif field.status == "user_confirmed":
            user_confirmed.append(field.field_id)
        elif field.status == "conflict":
            conflict.append(field.field_id)
        if field.candidates:
            retained_candidates[field.field_id] = list(field.candidates)

    return {
        "summary": {
            "field_count": len(state.fields),
            "interaction_mode": state.interaction_mode,
        },
        "missing_fields": missing,
        "candidate_fields": candidate,
        "suggested_fields": suggested,
        "user_confirmed_fields": user_confirmed,
        "conflict_fields": conflict,
        "retained_candidates": retained_candidates,
        "evidence_map": {
            field.field_id: list(field.evidence_ids)
            for field in state.fields.values()
            if field.evidence_ids
        },
        "risks": list(state.risks),
        "notes": ["This report describes draft field status only."],
    }
