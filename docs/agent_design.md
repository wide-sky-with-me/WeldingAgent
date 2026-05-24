# pWPS Agent 设计说明

## 1. 设计定位

本项目第一阶段采用 **单 LLM Supervisor Agent + Domain Skills + Runtime Tools**。

它不是多 Agent 专家群，也不是规则系统。系统的核心是一个能够统领全局的 LLM Supervisor。Supervisor 读取 `PWPSState`，参考 Domain Skill，决定下一步动作，调用 Runtime Tool，解释结果，更新状态，并最终生成 pWPS 草案。

一句话概括：

> LLM Supervisor 负责“想清楚和做决策”，Domain Skill 负责“提供领域经验和行为指导”，Runtime Tool 负责“执行具体能力”，PWPSState 负责“沉淀结果”。

---

## 2. 为什么不是多 Agent

第一阶段不采用多 Agent 专家群，原因：

1. 当前目标是跑通工作流，不是模拟专家会审。
2. 数据量和知识库不足，多专家容易变成多个 LLM 重复推理。
3. 多 Agent 会增加调试难度和状态冲突。
4. pWPS 生成的关键是字段状态、证据和草案结构，而不是 Agent 数量。
5. 单 Supervisor + Domain Skill + Runtime Tool 更容易扩展，后续可把复杂工具或子流程拆成子 Agent。

---

## 3. 为什么 LLM 是主角

本项目不希望做成“规则填表系统”。第一阶段没有完整标准规则库，也没有稳定企业数据库。因此系统应充分利用 LLM 的能力：

- 理解自然语言需求。
- 判断用户信息是否足够。
- 在自动草稿和对话确认之间选择合适交互策略。
- 规划检索关键词。
- 阅读网页和本地文档片段。
- 从证据中抽取候选字段。
- 判断字段冲突和不确定性。
- 给用户解释字段候选并请求确认。
- 组织 A/B/C/D/E 草案。
- 生成风险解释和待确认项。

系统中的 Schema 和 Contract 只是工程约束，保证 LLM 的输出可以执行、可以追踪、可以渲染，不是用来替代 LLM 的专业推理。

模型调用层只假设 OpenAI-compatible API，不假设真实供应商一定是 OpenAI。实现时统一读取 `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`，必要时再映射为 SDK 需要的 OpenAI 风格变量。

---

## 4. Supervisor Agent 职责

Supervisor Agent 是全局控制器和任务主角。

### 4.1 输入

Supervisor 每轮读取：

```text
PWPSState
当前用户输入
已有字段
已有证据
历史动作
当前草案
风险项
当前交互模式
用户确认记录
```

### 4.2 输出

Supervisor 输出结构化 `AgentAction`：

```json
{
  "action_type": "CALL_TOOL",
  "tool_name": "web_search",
  "tool_args": {
    "query": "Q355B 12mm GMAW butt joint flat position pWPS WPS"
  },
  "rationale_summary": "核心场景信息基本齐全，需要查找相似案例作为焊材和参数参考。",
  "expected_state_change": "获得相似案例和参数证据"
}
```

### 4.3 Supervisor 可选动作

```text
USE_DOMAIN_SKILL  选择或记录当前使用的 Domain Skill 指导上下文
CALL_TOOL        调用某个 Runtime Tool
UPDATE_STATE     将理解结果或字段推理写入状态
ASK_USER         生成澄清问题
COMPOSE_DRAFT    生成 pWPS 草案
GENERATE_REPORT  生成字段和风险报告
FINISH           结束任务
```

### 4.4 Supervisor 不做的事

1. 不编造项目名、合同号、客户名。
2. 不把网络资料说成正式标准条款。
3. 不把 LLM 建议说成已验证结论。
4. 不绕过状态机直接输出不可追踪文档。
5. 不承诺草案可直接签发。

---

## 5. Domain Skill、Runtime Tool 与子流程

本项目明确区分三个概念：

```text
Domain Skill
  模型指导层：告诉 Supervisor 如何理解需求、确认字段、使用证据、表达风险。

Runtime Tool
  执行能力层：搜索、抽取、字段合并、渲染、持久化。

LangGraph Subflow
  状态流转层：组织 auto_draft、guided_confirmation、supplement_update。
```

### 5.1 Domain Skill 列表

| Domain Skill | 说明 |
|---|---|
| pwps_auto_draft | 指导最小输入下如何自动生成候选草案并保留不确定性 |
| pwps_guided_confirmation | 指导如何逐组给出建议、解释来源、让用户确认字段 |
| pwps_evidence_handling | 指导如何区分用户输入、本地文档、网页、LLM 建议和模板 |
| pwps_risk_review | 指导如何标记缺失、冲突、低置信、热处理/PWHT 等风险 |

Domain Skill 可以是实际 agent skill 包，也可以先以 prompt/reference 文档形式存在。它不直接执行搜索、渲染或状态合并。

### 5.2 Runtime Tool 列表

| Tool | 类型 | 说明 |
|---|---|---|
| requirement_understanding | LLM-backed Tool | 从用户输入或补充信息抽取核心字段和任务意图 |
| local_doc_search | Tool | 检索本地文档、模板、样例 |
| web_search | Tool | 检索公开网络资料 |
| evidence_extract | LLM-backed Tool | 从检索结果抽取证据和候选字段 |
| field_reasoning | LLM-backed Tool | 根据证据生成字段候选和建议 |
| field_merge | Deterministic Tool | 合并字段、证据、风险和用户确认记录 |
| section_generation | LLM-backed Tool | 基于字段状态生成 A/B/C/D/E 分区内容 |
| draft_render | Tool | 渲染 Markdown/HTML |
| risk_report | LLM-backed + Tool | 生成风险和待确认报告 |
| state_persist | Tool | 保存 state、trace、输出文件 |

### 5.3 Tool Contract

所有 Runtime Tool 必须满足：

```python
def tool(state: PWPSState, args: dict) -> ToolResult:
    ...
```

`ToolResult`：

```python
class ToolResult(BaseModel):
    tool_name: str
    success: bool
    state_patch: dict = {}
    artifacts: list[dict] = []
    errors: list[str] = []
    summary: str
```

Runtime Tool 不直接修改全局对象，只返回 `state_patch`，由 Graph Runtime 或 `field_merge` 合并。

`web_search` 必须调用真实搜索 provider。不要实现 mock provider 作为正常开发或测试路径；测试应使用受控真实查询、小型本地夹具或录制的真实响应。

### 5.4 Interaction Subflows

第一阶段只关注三个子流程：

```text
auto_draft
  用户给最小输入，系统尽量生成完整草案。
  字段可为 user_provided / candidate / suggested / missing / need_confirmation。

guided_confirmation
  系统按字段组给建议、解释和风险，由用户确认。
  用户确认后才把字段提升为 user_confirmed。

supplement_update
  用户随时补充信息，系统解析为 state_patch，更新受影响字段、草案和风险。
```

---

## 6. 典型运行过程

用户输入：

```text
请生成 Q355B，12mm 板材，GMAW，对接接头，平焊，按 AWS D1.1 的 pWPS 草案。
```

典型过程：

```text
1. Supervisor 读取原始输入。
2. Supervisor 根据用户意图选择 auto_draft 或 guided_confirmation。
3. Supervisor 参考对应 Domain Skill。
4. Supervisor 调用 requirement_understanding tool。
5. Tool 抽取标准、母材、厚度、焊法、接头、位置。
6. Supervisor 调用 knowledge_planning tool，让模型根据已知字段、缺失字段、风险字段判断下一步需要查什么。
7. Supervisor 按计划调用 local_doc_search 和 web_search tools。
8. Supervisor 调用 evidence_extract tool 阅读结果。
9. Supervisor 调用 field_reasoning tool 将证据转成字段候选值。
10. auto_draft 下，Supervisor 继续生成草案和风险报告。
11. guided_confirmation 下，Supervisor 按字段组向用户解释候选并等待确认。
12. Supervisor FINISH 或等待用户补充信息。
```

注意：该流程不是硬编码线性规则，而是 LLM Supervisor 在典型任务中自然选择的动作序列。

---

## 7. 需求理解策略

`requirement_understanding` 应抽取：

```text
适用标准
标准年份
母材牌号
母材标准
厚度/壁厚
板/管类型
管径
焊接方法
接头类型
坡口形式
焊接位置
工况/特殊要求
```

若用户输入不足，Supervisor 可以选择：

1. 追问。
2. 生成模板草案。
3. 先检索宽泛相似案例。
4. 降级输出“缺失信息清单”。

是否继续由 LLM 判断，不用硬编码为固定规则。

在 `auto_draft` 下，不足信息可以进入“候选草案 + 缺失/风险清单”。在 `guided_confirmation` 下，不足信息应转化为字段级确认问题或可选候选值。

---

## 8. 知识规划策略

Supervisor 应主动生成查询，而不是等待固定模板。查询规划本身是一个模型判断任务：系统应把已知字段、缺失字段、候选字段、风险字段和当前目标交给 `knowledge_planning`，由模型决定下一步查什么、为什么查、目标字段是什么。

禁止把第一阶段实现成“把所有已知字段拼成一个固定搜索字符串”。固定模板只能作为 fallback，不能作为主路径。

查询类型包括：

```text
similar_case          相似 pWPS/WPS 案例
material_reference    母材和材料标准参考
filler_reference      焊材参考
parameter_reference   电流、电压、焊速、热输入参考
thermal_reference     预热、层间温度、PWHT 参考
standard_background   标准背景或术语
```

示例查询：

```text
Q355B 12mm GMAW butt joint flat position pWPS WPS filler current voltage
Q355B GMAW plate common welding positions AWS D1.1 WPS
Q355B 12mm GMAW butt joint shielding gas filler wire reference
```

示例规划逻辑：

```text
已知：base_material=Q355B, welding_process=GMAW
缺失：welding_position
计划：查询 "Q355B GMAW plate common welding positions WPS"
原因：先确认该材料和焊接方法在相似 pWPS/WPS 中常见的焊接位置，再决定是否需要追问用户。
```

知识源优先级不应作为硬规则写死。可以通过 Prompt 建议：

1. 用户输入最可信。
2. 本地文档通常比网络资料更贴近项目。
3. 网络资料只能作为公开参考。
4. LLM 建议必须标记 suggested。

最终如何使用由 LLM Supervisor 根据上下文判断。

---

## 9. 字段推理策略

`field_reasoning` 的任务是把证据转成字段状态。

例如证据：

```text
GMAW 焊接低合金钢常用 ER50-6 焊丝，保护气体可采用 Ar+CO2 混合气体。
```

字段推理结果：

```json
{
  "field_id": "filler_material",
  "value": "ER50-6",
  "status": "candidate",
  "source": "web",
  "confidence": "medium",
  "note": "由公开资料推断，待确认"
}
```

字段状态不是简单填空，而是表达：

- 值是什么
- 从哪里来
- 是否只是候选
- 是否有冲突
- 是否需要确认
- 是否已经由用户确认

在 `auto_draft` 模式下，系统生成的值一般保持为 `candidate` 或 `suggested`。在 `guided_confirmation` 模式下，只有用户明确接受或修改后的字段才能标记为 `user_confirmed`。

---

## 10. 用户确认策略

`guided_confirmation` 不应做成普通闲聊，而应围绕字段组推进。

每轮确认应包含：

```text
当前字段组
推荐值
备选值
推荐原因
来源和证据摘要
风险或待确认说明
用户可选动作：接受 / 修改 / 跳过 / 暂不确认
```

推荐确认顺序：

```text
1. 核心适用范围：标准、母材、厚度、板管类型、焊法、接头、位置
2. 焊材与辅助材料：焊材型号、直径、保护气、流量
3. 焊接参数：电流、电压、速度、热输入、层道
4. 热处理与温控：预热、层间、后热、PWHT
5. A 类项目元信息：只确认用户提供或明确补充的信息
```

---

## 11. 草案生成策略

`section_generation` 负责生成：

```text
A 文件与项目元信息
B 焊接适用范围
C 焊材与辅助材料
D 焊接参数
E 热处理与温控
```

生成原则：

1. 先基于字段状态生成，不直接凭空写。
2. 缺失字段保留“待确认”。
3. 候选字段标注“候选/建议”。
4. 高风险字段如预热、PWHT、热输入要谨慎表达。
5. A 类项目元信息不得编造。

---

## 12. 风险报告策略

风险报告应指出：

```text
缺失字段
候选字段
LLM 建议字段
网络参考字段
冲突字段
温控/PWHT 高敏感字段
未经过正式校验的说明
```

风险报告不是拒绝生成，而是让草案透明。

---

## 13. Prompt 与 Domain Skill 设计建议

### 13.1 Supervisor Prompt 核心要求

Supervisor Prompt 应强调：

1. 你是 pWPS Agent 的全局主控。
2. 你负责规划和决策，不是规则执行器。
3. 你可以参考 Domain Skill 来获得领域流程指导。
4. 你可以调用 Runtime Tool 来获取执行能力。
5. 你必须把结果写入 PWPSState。
6. 你不能伪造项目元信息。
7. 你不能把网络资料或 LLM 建议说成正式标准结论。
8. 你每轮必须输出结构化 AgentAction。

### 13.2 Domain Skill 要求

Domain Skill 应保持精简，重点放在：

- 何时使用
- 字段确认顺序
- 推荐值解释格式
- 证据和风险措辞
- 禁止事项
- 简短示例

### 13.3 LLM-backed Tool 要求

每个 LLM-backed Tool 应使用结构化输出：

- Pydantic model
- `Field(description=...)` 描述字段语义、来源约束和不确定性表达
- LangChain `with_structured_output(PydanticModel)` 作为优先实现路径
- 明确字段名
- 不输出无关自然语言

Prompt 必须统一放在 `configs/prompts/`，工具函数只负责加载 prompt、准备上下文、调用结构化模型和校验结果。输出结构不要主要靠 prompt 描述，应放在 Pydantic schema 中；prompt 只保留角色、任务边界、安全规则和领域约束。

---

## 14. 后续演进

### 阶段一

```text
Single LLM Supervisor + Domain Skills + Runtime Tools + local/web search
```

### 阶段二

```text
增强 Knowledge Provider
接入企业文档、模板库、材料库、焊材库
```

### 阶段三

```text
复杂 Tool 或 Subflow 拆成子 Agent
例如 Evidence Agent、Draft Agent、Risk Agent
```

### 阶段四

```text
接入人工审核、PQR/WPQR、正式签发流程
```

---

## 15. 最小实现建议

第一版只需要实现：

```text
1. PWPSState
2. AgentAction
3. LLM Supervisor Node
4. interaction_mode: auto_draft / guided_confirmation / supplement_update
5. requirement_understanding Tool
6. field_merge Tool
7. local_doc_search Tool
8. web_search Tool
9. evidence_extract Tool
10. field_reasoning Tool
11. draft_render Tool
12. risk_report Tool
13. pwps_auto_draft Domain Skill
14. pwps_guided_confirmation Domain Skill
```

不要先写复杂规则，也不要先实现多 Agent。
