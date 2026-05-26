from __future__ import annotations

from typing import Any, TextIO


def render_terminal_interaction(interaction: dict) -> str:
    """Render a transport-neutral interaction request for a terminal."""

    lines: list[str] = []
    title = str(interaction.get("title") or "Runtime interaction")
    lines.append(f"[需要用户输入] {title}")

    for key in ("summary", "assistant_message"):
        value = interaction.get(key)
        if value:
            lines.append(str(value))

    for index, question in enumerate(_questions(interaction), start=1):
        if lines:
            lines.append("")
        prompt = str(question.get("prompt") or "Please provide input.")
        lines.append(f"{index}. {prompt}")
        field_ids = [str(field_id) for field_id in question.get("field_ids") or []]
        if field_ids:
            lines.append(f"   字段: {', '.join(field_ids)}")
        options = list(question.get("options") or [])
        for option_index, option in enumerate(options, start=1):
            lines.extend(_render_option(option_index, _as_dict(option)))

    return "\n".join(lines)


def collect_terminal_response(
    interaction: dict,
    stdin: TextIO,
    stdout: TextIO,
) -> str:
    print("", file=stdout)
    print(render_terminal_interaction(interaction), file=stdout)
    while True:
        print("请输入选项编号或 field=value: ", end="", flush=True, file=stdout)
        value = stdin.readline()
        if value == "":
            raise EOFError("Input ended while waiting for runtime interaction response.")
        value = value.strip()
        if value:
            return value
        print("不能为空。", file=stdout)


def _render_option(index: int, option: dict[str, Any]) -> list[str]:
    marker = " [推荐]" if option.get("recommended") else ""
    label = option.get("label") or option.get("value")
    lines = [f"   {index}. {label}{marker}"]
    suitability = option.get("suitability")
    if suitability:
        lines.append(f"      适用性: {suitability}")
    risk_note = option.get("risk_note")
    if risk_note:
        lines.append(f"      风险: {risk_note}")
    return lines


def _questions(interaction: dict) -> list[dict[str, Any]]:
    return [_as_dict(question) for question in interaction.get("questions") or []]


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return dict(value)
