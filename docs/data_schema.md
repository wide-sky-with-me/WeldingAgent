# pWPS Agent 数据结构说明

## 1. 设计原则

数据结构服务于 LLM 主导的 Agent 工作流，而不是规则引擎。

核心原则：

1. 所有重要信息都必须写入 `PWPSState`。
2. LLM 的动作必须结构化为 `AgentAction`。
3. Domain Skill 使用、Runtime Tool 输入输出必须可序列化、可记录、可回放。
4. 字段值必须携带来源、证据和状态。
5. 检索结果必须转化为 Evidence 后再影响字段。
6. 输出草案必须能追溯到字段和证据。
7. 用户确认必须显式记录，不能和模型候选值混淆。

---

## 2. 顶层状态：PWPSState

`PWPSState` 是 LangGraph 中传递和更新的核心状态。

```python
from typing import Any, Literal, TypedDict

class PWPSState(TypedDict, total=False):
    run_id: str
    user_input: str
    task_goal: str
    interaction_mode: Literal["auto_draft", "guided_confirmation", "supplement_update"]
    messages: list[dict]

    core_fields: dict[str, Any]
    fields: dict[str, dict[str, Any]]
    confirmations: list[dict]

    actions: list[dict]
    pending_action: dict | None

    knowledge_queries: list[dict]
    search_results: list[dict]
    evidence: list[dict]

    sections: dict[str, Any]
    draft_markdown: str
    draft_html: str
    field_report: dict[str, Any]

    clarification_questions: list[dict]
    risks: list[dict]
    trace: list[dict]

    status: str
    step_count: int
```

### 字段说明

| 字段 | 含义 |
|---|---|
| run_id | 单次运行 ID |
| user_input | 用户原始需求 |
| task_goal | 当前任务目标，如 generate_pwps_draft |
| interaction_mode | 当前交互模式，auto_draft / guided_confirmation / supplement_update |
| messages | 可选对话消息，不作为主状态 |
| core_fields | 从用户输入中抽取的核心字段 |
| fields | A/B/C/D/E 全量字段状态 |
| confirmations | 用户确认、修改、跳过字段的记录 |
| actions | Supervisor 历史动作 |
| pending_action | 当前待执行动作 |
| knowledge_queries | 知识查询任务 |
| search_results | 原始检索结果 |
| evidence | 结构化证据 |
| sections | A/B/C/D/E 分区草案 |
| draft_markdown | Markdown 草案 |
| draft_html | HTML 草案，可选 |
| field_report | 字段来源与风险报告 |
| clarification_questions | 追问问题 |
| risks | 风险项 |
| trace | 运行轨迹 |
| status | running / need_user_input / done / failed |
| step_count | 当前循环步数 |

---

## 3. AgentAction

LLM Supervisor 每轮输出一个结构化动作。

```python
from pydantic import BaseModel, Field
from typing import Literal, Any

class AgentAction(BaseModel):
    action_type: Literal[
        "USE_DOMAIN_SKILL",
        "CALL_TOOL",
        "UPDATE_STATE",
        "ASK_USER",
        "COMPOSE_DRAFT",
        "GENERATE_REPORT",
        "FINISH"
    ]
    domain_skill_name: str | None = None
    tool_name: str | None = None
    tool_args: dict[str, Any] = Field(default_factory=dict)
    state_patch: dict[str, Any] = Field(default_factory=dict)
    rationale_summary: str
    expected_state_change: str | None = None
    stop_reason: str | None = None
```

### 说明

- `rationale_summary` 是简要决策理由，用于 trace。
- 不要求保存完整私有推理链。
- `domain_skill_name` 只在 `USE_DOMAIN_SKILL` 时需要，用于记录或加载模型指导上下文。
- `tool_name` 和 `tool_args` 只在 `CALL_TOOL` 时需要。
- `state_patch` 只允许写入 Schema 允许的字段。

---

## 4. CoreFields

核心输入用于判断是否能检索相似案例和生成有参考价值的草案。

```python
class CoreFields(TypedDict, total=False):
    applicable_standard: str | None
    standard_year: str | None
    base_material: str | None
    base_material_standard: str | None
    thickness: str | None
    workpiece_type: str | None
    diameter: str | None
    welding_process: str | None
    joint_type: str | None
    groove_type: str | None
    welding_position: str | None
    service_condition: str | None
    special_requirements: list[str]
```

最小核心集合：

```text
applicable_standard
base_material
thickness
workpiece_type
diameter，管材时需要
welding_process
joint_type
welding_position
```

注意：是否足够继续由 LLM Supervisor 判断，而不是固定规则判死。Schema 只声明字段。

---

## 5. FieldState

每个 pWPS 字段都用 `FieldState` 表示。

```python
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
        "not_applicable"
    ] = "missing"

    note: str | None = None
```

### status 语义

| 状态 | 含义 |
|---|---|
| missing | 当前无值 |
| filled | 值较明确，通常来自用户或高置信来源 |
| candidate | 候选值，来自检索或相似案例 |
| suggested | LLM 建议值或低依据建议 |
| user_confirmed | 用户已经明确接受或修改确认的值 |
| conflict | 多个来源冲突 |
| need_confirmation | 需要用户或后续知识库确认 |
| not_applicable | 当前场景不适用 |

### confirmation 语义

`confirmation` 用于表达字段确认权：

```python
confirmation = {
    "required": True,
    "confirmed": False,
    "confirmed_by": None,
    "confirmed_at": None,
    "user_note": None
}
```

在 `auto_draft` 模式下，模型生成的字段通常保持 `candidate` 或 `suggested`，并可设置 `required=True`。在 `guided_confirmation` 模式下，只有用户明确接受或修改后的字段才能设置为 `status="user_confirmed"`。

---

## 6. 字段分区 Schema

系统字段分为 A/B/C/D/E。

### A. 文件与项目元信息

```yaml
A:
  - field_id: pwps_no
    label: pWPS编号
  - field_id: revision_no
    label: 修订号
  - field_id: date
    label: 编制日期
  - field_id: applicable_standard
    label: 适用标准
  - field_id: standard_year
    label: 标准年份
  - field_id: company
    label: 编制单位
  - field_id: project_name
    label: 项目名称
  - field_id: client
    label: 客户名称
  - field_id: contract_no
    label: 合同号
```

### B. 焊接适用范围

```yaml
B:
  - field_id: base_material
    label: 母材牌号
  - field_id: base_material_standard
    label: 母材标准
  - field_id: workpiece_type
    label: 板/管类型
  - field_id: thickness
    label: 厚度/壁厚
  - field_id: diameter
    label: 管径/外径
  - field_id: welding_process
    label: 焊接方法
  - field_id: joint_type
    label: 接头类型
  - field_id: groove_type
    label: 坡口形式
  - field_id: weld_type
    label: 焊缝类型
  - field_id: welding_position
    label: 焊接位置
```

### C. 焊材与辅助材料

```yaml
C:
  - field_id: filler_material
    label: 焊材型号/分类号
  - field_id: filler_trade_name
    label: 焊材牌号
  - field_id: filler_diameter
    label: 焊丝/焊条直径
  - field_id: shielding_gas
    label: 保护气体
  - field_id: gas_flow_rate
    label: 气体流量
  - field_id: flux
    label: 焊剂
  - field_id: backing_gas
    label: 背面保护气
  - field_id: drying_requirement
    label: 焊材烘干要求
```

### D. 焊接参数

```yaml
D:
  - field_id: polarity
    label: 电流类型/极性
  - field_id: current_range
    label: 电流范围
  - field_id: voltage_range
    label: 电压范围
  - field_id: travel_speed
    label: 焊接速度
  - field_id: heat_input
    label: 热输入范围
  - field_id: pass_count
    label: 层道数
  - field_id: bead_sequence
    label: 焊道/层道安排
  - field_id: weaving
    label: 摆动方式
```

### E. 热处理与温控

```yaml
E:
  - field_id: preheat_temperature
    label: 预热温度
  - field_id: interpass_temperature
    label: 层间温度
  - field_id: post_heat
    label: 后热
  - field_id: pwht
    label: 焊后热处理
  - field_id: holding_temperature
    label: 保温温度
  - field_id: holding_time
    label: 保温时间
```

---

## 7. KnowledgeQuery

LLM Supervisor 或知识规划 Runtime Tool 生成查询任务。

```python
class KnowledgeQuery(BaseModel):
    query_id: str
    purpose: Literal[
        "similar_case",
        "material_reference",
        "filler_reference",
        "parameter_reference",
        "thermal_reference",
        "standard_background",
        "other"
    ]
    query_text: str
    context: dict[str, Any] = Field(default_factory=dict)
    preferred_sources: list[str] = Field(default_factory=list)
    target_fields: list[str] = Field(default_factory=list)
```

示例：

```json
{
  "query_id": "kq_001",
  "purpose": "similar_case",
  "query_text": "Q355B 12mm GMAW butt joint flat position pWPS WPS",
  "preferred_sources": ["local_doc", "web"],
  "target_fields": ["filler_material", "current_range", "voltage_range"]
}
```

---

## 8. SearchResult

检索工具返回原始结果。

```python
class SearchResult(BaseModel):
    result_id: str
    query_id: str
    source_type: Literal["local_doc", "web", "llm", "future_db"]
    source_name: str | None = None
    title: str | None = None
    url: str | None = None
    path: str | None = None
    snippet: str
    raw_content: str | None = None
    score: float | None = None
```

---

## 9. Evidence

Evidence 是可用于字段推理的结构化证据。

```python
class Evidence(BaseModel):
    evidence_id: str
    query_id: str | None = None
    result_id: str | None = None
    source_type: Literal[
        "user_input",
        "user_confirmation",
        "local_doc",
        "web",
        "llm",
        "template",
        "future_db"
    ]
    source_ref: str | None = None
    content: str
    extracted_claims: list[str] = Field(default_factory=list)
    related_fields: list[str] = Field(default_factory=list)
    reliability: Literal["high", "medium", "low", "unknown"] = "unknown"
    note: str | None = None
```

### 证据来源约定

| source_type | 说明 |
|---|---|
| user_input | 用户明确给出的信息 |
| user_confirmation | 用户在 guided_confirmation 中确认或修改的信息 |
| local_doc | 本地文档检索 |
| web | 网络搜索资料 |
| llm | LLM 推理或建议 |
| template | 内置模板 |
| future_db | 未来数据库/规则库/企业库 |

---

## 10. SectionDraft

A/B/C/D/E 分区草案。

```python
class SectionDraft(BaseModel):
    section: Literal["A", "B", "C", "D", "E"]
    title: str
    fields: list[FieldState]
    narrative: str | None = None
    warnings: list[str] = Field(default_factory=list)
```

---

## 11. ConfirmationRecord

用户确认记录。

```python
class ConfirmationRecord(BaseModel):
    confirmation_id: str
    field_ids: list[str]
    action: Literal["accepted", "modified", "skipped", "deferred"]
    values: dict[str, Any] = Field(default_factory=dict)
    user_message: str | None = None
    rationale_shown: str | None = None
    evidence_ids_shown: list[str] = Field(default_factory=list)
    created_at: str | None = None
```

---

## 12. ToolResult

Runtime Tool 返回结构。

```python
class ToolResult(BaseModel):
    tool_name: str
    success: bool
    state_patch: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    summary: str
```

Tool 不直接修改全局状态。状态合并由 Graph Runtime 或 `field_merge` 工具负责。

---

## 13. RiskItem

风险项用于报告。

```python
class RiskItem(BaseModel):
    risk_id: str
    field_id: str | None = None
    level: Literal["low", "medium", "high"]
    category: Literal[
        "missing_information",
        "low_confidence",
        "web_reference_only",
        "llm_suggestion",
        "conflict",
        "thermal_or_pwht_sensitive",
        "not_formal_validation"
    ]
    message: str
    suggested_action: str | None = None
```

---

## 14. FieldReport

字段报告结构。

```python
class FieldReport(BaseModel):
    summary: dict[str, Any]
    missing_fields: list[str]
    candidate_fields: list[str]
    suggested_fields: list[str]
    user_confirmed_fields: list[str]
    conflict_fields: list[str]
    evidence_map: dict[str, list[str]]
    risks: list[RiskItem]
    notes: list[str]
```

---

## 15. TraceEvent

每个关键步骤都记录 trace。

```python
class TraceEvent(BaseModel):
    step: int
    node: str
    event_type: Literal[
        "llm_action",
        "domain_skill_used",
        "tool_call",
        "tool_result",
        "state_update",
        "user_confirmation",
        "draft_generated",
        "report_generated",
        "error"
    ]
    summary: str
    payload: dict[str, Any] = Field(default_factory=dict)
```

---

## 16. 输出文件结构

### pwps.json

```json
{
  "run_id": "...",
  "interaction_mode": "auto_draft",
  "core_fields": {},
  "fields": {},
  "confirmations": [],
  "sections": {},
  "risks": [],
  "evidence": []
}
```

### pwps_draft.md

```markdown
# pWPS 草案

## 1. 文件与项目元信息
...

## 2. 焊接适用范围
...

## 3. 焊材与辅助材料
...

## 4. 焊接参数
...

## 5. 热处理与温控
...

## 6. 待确认项与风险提示
...
```

### field_report.json

```json
{
  "summary": {},
  "missing_fields": [],
  "candidate_fields": [],
  "suggested_fields": [],
  "user_confirmed_fields": [],
  "conflict_fields": [],
  "risks": [],
  "notes": []
}
```

### trace.json

```json
[
  {
    "step": 1,
    "node": "supervisor",
    "event_type": "llm_action",
    "summary": "决定检索相似案例",
    "payload": {}
  }
]
```
