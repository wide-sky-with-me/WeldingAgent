from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class FieldState(BaseModel):
    field_id: str
    section: Literal["A", "B", "C", "D", "E"]
    label: str
    value: Any | None = None
    unit: str | None = None
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    source: dict[str, Any] | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    confirmation: dict[str, Any] = Field(default_factory=dict)
    confidence: Literal["high", "medium", "low", "unknown"] = "unknown"
    status: Literal[
        "missing",
        "filled",
        "candidate",
        "suggested",
        "user_confirmed",
        "conflict",
        "need_confirmation",
        "not_applicable",
    ] = "missing"
    note: str | None = None


FIELD_DEFINITIONS: dict[str, list[tuple[str, str]]] = {
    "A": [
        ("pwps_no", "pWPS编号"),
        ("revision_no", "修订号"),
        ("date", "编制日期"),
        ("applicable_standard", "适用标准"),
        ("standard_year", "标准年份"),
        ("company", "编制单位"),
        ("project_name", "项目名称"),
        ("client", "客户名称"),
        ("contract_no", "合同号"),
    ],
    "B": [
        ("base_material", "母材牌号"),
        ("base_material_standard", "母材标准"),
        ("workpiece_type", "板/管类型"),
        ("thickness", "厚度/壁厚"),
        ("diameter", "管径/外径"),
        ("welding_process", "焊接方法"),
        ("joint_type", "接头类型"),
        ("groove_type", "坡口形式"),
        ("weld_type", "焊缝类型"),
        ("welding_position", "焊接位置"),
    ],
    "C": [
        ("filler_material", "焊材型号/分类号"),
        ("filler_trade_name", "焊材牌号"),
        ("filler_diameter", "焊丝/焊条直径"),
        ("shielding_gas", "保护气体"),
        ("gas_flow_rate", "气体流量"),
        ("flux", "焊剂"),
        ("backing_gas", "背面保护气"),
        ("drying_requirement", "焊材烘干要求"),
    ],
    "D": [
        ("polarity", "电流类型/极性"),
        ("current_range", "电流范围"),
        ("voltage_range", "电压范围"),
        ("travel_speed", "焊接速度"),
        ("heat_input", "热输入范围"),
        ("pass_count", "层道数"),
        ("bead_sequence", "焊道/层道安排"),
        ("weaving", "摆动方式"),
    ],
    "E": [
        ("preheat_temperature", "预热温度"),
        ("interpass_temperature", "层间温度"),
        ("post_heat", "后热"),
        ("pwht", "焊后热处理"),
        ("holding_temperature", "保温温度"),
        ("holding_time", "保温时间"),
    ],
}


def initialize_fields() -> dict[str, FieldState]:
    fields: dict[str, FieldState] = {}
    for section, definitions in FIELD_DEFINITIONS.items():
        for field_id, label in definitions:
            fields[field_id] = FieldState(
                field_id=field_id,
                section=section,  # type: ignore[arg-type]
                label=label,
                confirmation={"required": False, "confirmed": False},
            )
    return fields
