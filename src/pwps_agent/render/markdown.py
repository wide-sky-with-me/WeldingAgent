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
    lines.extend(_render_quality_summary(state))

    for index, section in enumerate(["A", "B", "C", "D", "E"], start=1):
        section_payload = state.sections.get(section)
        if section_payload:
            lines.extend(_render_structured_section(index, section, section_payload))
        else:
            lines.extend(_render_state_section(index, section, state))

    lines.append("## 6. 待确认项与风险提示")
    lines.append("")
    unresolved = _main_draft_unresolved_fields(state)
    high_risks = _high_severity_risks(state)
    if not unresolved:
        lines.append("- 当前字段均已填写或确认。")
    else:
        for field in unresolved:
            lines.append(f"- `{field.field_id}` {field.label}: {field.status}")
    for risk in high_risks:
        field_id = risk.get("field_id") or "general"
        risk_type = risk.get("risk_type") or risk.get("type") or "risk"
        severity = risk.get("severity") or "high"
        lines.append(f"- `{field_id}` {risk_type}: severity={severity}")
    if unresolved or high_risks:
        lines.append("- 完整字段状态和风险清单见 `field_report.json`。")
    lines.append("")
    return "\n".join(lines)


def _render_quality_summary(state: PWPSState) -> list[str]:
    if not state.quality_report:
        return []
    report = state.quality_report
    field_counts = report.get("field_counts") or {}
    count_summary = ", ".join(
        f"{key}={value}" for key, value in sorted(field_counts.items())
    )
    critical_missing = ", ".join(report.get("critical_missing_fields") or []) or "none"
    weak_evidence = ", ".join(report.get("weak_evidence_fields") or []) or "none"
    return [
        "## 草案质量摘要",
        "",
        f"- 质量等级: {report.get('quality_level', 'unknown')}",
        f"- 后续动作: {report.get('recommended_action', 'unknown')}",
        f"- 字段覆盖: {count_summary or 'unknown'}",
        f"- 关键待确认: {critical_missing}",
        f"- 弱证据字段: {weak_evidence}",
        "",
    ]


def _main_draft_unresolved_fields(state: PWPSState) -> list:
    critical_missing = set()
    if state.quality_report:
        critical_missing.update(state.quality_report.get("critical_missing_fields") or [])
    fields = []
    for field in state.fields.values():
        if field.status == "missing" and field.field_id not in critical_missing:
            continue
        if field.status in {
            "missing",
            "candidate",
            "suggested",
            "need_confirmation",
            "conflict",
        }:
            fields.append(field)
    return fields


def _high_severity_risks(state: PWPSState) -> list[dict[str, Any]]:
    high_risks = []
    for risk in state.risks:
        if not isinstance(risk, dict):
            continue
        severity = str(risk.get("severity") or "").lower()
        if severity in {"high", "critical"}:
            high_risks.append(risk)
    return high_risks


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
        "quality_report": state.quality_report,
        "notes": ["This report describes draft field status only."],
    }
