# pWPS Agent 架构说明

## 1. 架构总原则

本项目采用：

> **LLM-Centric Supervisor Agent + Domain Skills + Runtime Tools + PWPSState + Knowledge Provider**

第一阶段不采用规则驱动系统，也不采用多 Agent 专家群。LLM 不是兜底模块，而是系统的主角：它负责理解需求、规划动作、选择交互模式、参考 Domain Skill、调用 Runtime Tool、解释证据、回填字段、生成草案和输出风险说明。

LangGraph 不是用来把规则流程写死，而是作为可回放、可中断、可追踪的 Agent 运行时。Schema、State、Domain Skill 和 Tool Contract 用于约束工程边界，不替代 LLM 的核心判断。

概念边界：

- Domain Skill：面向模型的领域经验包，指导如何理解 pWPS 需求、确认字段、使用证据和表达风险。
- Runtime Tool：可执行能力，负责搜索、抽取、字段合并、渲染、持久化等具体动作。
- LangGraph Subflow：状态流转和交互模式，例如 `auto_draft`、`guided_confirmation`、`supplement_update`。

---

## 2. 总体架构图

```text
┌──────────────────────────────────────────┐
│                User Input                │
│ 自然语言需求 / 表单字段 / 文件片段          │
└──────────────────────────────────────────┘
                    ↓
┌──────────────────────────────────────────┐
│          LangGraph Agent Runtime          │
│ LLM Supervisor Action Loop + Checkpoint   │
└──────────────────────────────────────────┘
                    ↓
┌──────────────────────────────────────────┐
│          LLM Supervisor Agent             │
│ 理解 / 规划 / 选择模式 / 使用 Skill / 调工具 │
└──────────────────────────────────────────┘
                    ↓
┌──────────────────────────────────────────┐
│               PWPSState                   │
│ core_fields / fields / evidence / trace   │
└──────────────────────────────────────────┘
                    ↓
┌──────────────────────────────────────────┐
│         Domain Skills + Runtime Tools      │
│ guidance / confirmation / search / extract │
│ field merge / render / persist / export    │
└──────────────────────────────────────────┘
                    ↓
┌──────────────────────────────────────────┐
│            Knowledge Provider             │
│ local docs / web / future DB / future PQR  │
└──────────────────────────────────────────┘
                    ↓
┌──────────────────────────────────────────┐
│                 Outputs                   │
│ pWPS draft / field report / trace          │
└──────────────────────────────────────────┘
```

---

## 3. LLM Action Loop

第一阶段推荐采用 LLM Action Loop，而不是固定线性流程。

```text
START
  ↓
load_or_init_state
  ↓
llm_supervisor
  ↓
action_router
  ├── call_tool
  ├── update_state
  ├── ask_user
  ├── compose_draft
  ├── generate_report
  └── END
  ↓
write_trace
  ↓
llm_supervisor
  ↓
...
```

Supervisor 每一轮读取 `PWPSState`，输出结构化 `AgentAction`。LangGraph 根据 `AgentAction.action_type` 路由到对应节点或工具。Domain Skill 指导 Supervisor 如何选择和组织动作；Runtime Tool 执行具体动作。执行结果写回 State 后，再交给 Supervisor 判断下一步。

---

## 4. 与固定流程的关系

虽然架构是 LLM Action Loop，但典型执行轨迹通常会接近以下流程：

```text
需求理解
  ↓
核心信息判断
  ↓
选择 auto_draft 或 guided_confirmation
  ↓
知识查询规划
  ↓
本地文档检索 / 网络搜索
  ↓
证据阅读与字段推理
  ↓
A/B/C/D/E 分区草案生成
  ↓
草案合成
  ↓
字段来源与风险报告
```

这些不是硬编码规则流程，而是 LLM Supervisor 在大多数任务下自然选择的工作路径。系统通过 Prompt、State Schema、Domain Skill 和 Tool Contract 引导 LLM 做出合理动作。

知识查询规划必须是模型参与的动态过程。系统应避免把查询写死为一个拼接模板；固定查询只允许作为 fallback。`knowledge_planning` 应根据当前 `PWPSState` 判断缺什么、先查什么、每个查询服务哪些目标字段。

---

## 5. 主要组件

### 5.1 LLM Supervisor Agent

Supervisor 是系统主角。

它负责：

1. 理解用户需求。
2. 判断当前状态是否足以生成草案。
3. 选择 `auto_draft` 或 `guided_confirmation` 交互策略。
4. 判断是否需要追问或接受用户补充信息。
5. 规划知识查询。
6. 选择本地文档检索、网络搜索或 LLM 推理。
7. 阅读检索结果并抽取可用证据。
8. 将证据转化为字段候选值。
9. 在需要时向用户解释字段候选并请求确认。
10. 生成 A/B/C/D/E 分区内容。
11. 生成 pWPS 草案。
12. 生成字段来源和风险说明。

Supervisor 不应该做：

1. 编造用户未提供的项目名、合同号、客户名。
2. 把网络搜索结果说成正式标准条款。
3. 把 LLM 建议说成已验证结论。
4. 绕过 `PWPSState` 直接输出无法追踪的文档。

模型接入层应使用 OpenAI-compatible client。环境变量使用 provider-neutral 命名：

```text
LLM_API_KEY
LLM_BASE_URL
LLM_MODEL
LLM_TEMPERATURE
LLM_STRUCTURED_OUTPUT_METHOD
LLM_THINKING_TYPE
```

具体模型供应商可以不是 OpenAI，只要兼容 OpenAI API 请求/响应形态。`OPENAI_API_KEY`、`OPENAI_BASE_URL` 等名称只作为 SDK 兼容别名使用，不作为架构假设。

结构化输出优先采用 LangChain `with_structured_output(PydanticModel)`。Pydantic model 和 `Field(description=...)` 是输出契约的主要来源；集中 prompt 只描述任务、边界和安全规则。对于 DeepSeek 这类 OpenAI-compatible provider，默认通过 `langchain_openai.ChatOpenAI` 配置 `base_url`、`api_key` 和 `model`。DeepSeek V4 的 thinking mode 与部分 tool-choice/structured-output 调用可能不兼容，结构化字段抽取默认建议配置 `LLM_THINKING_TYPE=disabled`。

### 5.2 Domain Skills

Domain Skill 是给 LLM Supervisor 使用的指导包，不是运行时子流程，也不是普通工具函数。它提供领域经验、步骤、措辞规范和风险判断边界。

第一阶段 Domain Skill 建议包括：

| Domain Skill | 作用 |
|---|---|
| pwps_auto_draft | 从最小输入生成草案，保留候选/建议/待确认状态 |
| pwps_guided_confirmation | 逐组给用户候选值、推荐理由、风险解释和确认入口 |
| pwps_evidence_handling | 区分用户输入、本地文档、网络资料、LLM 建议和模板来源 |
| pwps_risk_review | 识别缺失、低置信、冲突、热处理/PWHT 等风险 |

Domain Skill 不直接修改状态，不直接执行搜索或渲染。它指导 Supervisor 如何调用工具、如何解释结果、如何写入字段状态。

### 5.3 Runtime Tools

Runtime Tool 是可执行能力，不是独立决策主体。

第一阶段 Runtime Tool 包括：

| Tool | 作用 |
|---|---|
| requirement_understanding | 从用户输入或补充信息抽取核心字段 |
| local_doc_search | 检索本地文档、样例、模板 |
| web_search | 检索公开网络资料和相似案例 |
| knowledge_planning | 根据当前状态规划针对性知识查询 |
| evidence_extract | 从资料中抽取候选字段和证据 |
| field_reasoning | 根据证据生成字段候选和建议 |
| field_merge | 将字段、证据、风险合并进 PWPSState |
| section_generation | 根据字段状态生成 A/B/C/D/E 分区 |
| draft_render | 将结构化状态渲染为 Markdown/HTML |
| risk_report | 生成字段来源、缺失项和风险项 |
| state_persist | 保存 state、trace、输出文件 |

Tool 必须返回结构化 `ToolResult`，不直接修改全局状态。Graph Runtime 或专用 merge 节点负责把 `state_patch` 合并进 `PWPSState`。

LLM-backed Tool 不应在函数体内散落大段 prompt。生产 prompt 统一存放于 `configs/prompts/`，工具通过 prompt loader 读取；返回结构通过 Pydantic schema 校验。

### 5.4 Interaction Subflows

第一阶段核心交互子流程：

```text
auto_draft
  最小输入 → 自动抽取 → 检索/推理 → 候选字段 → 草案 → 风险报告

guided_confirmation
  字段组候选 → 推荐与解释 → 用户确认/修改/跳过 → 状态更新 → 下一个字段组

supplement_update
  用户补充信息 → 解析 patch → 更新受影响字段 → 重新评估草案和风险
```

这三者共享同一个 `PWPSState`、字段 Schema、证据模型和渲染机制。

### 5.5 PWPSState

PWPSState 是系统数据中心。

它存储：

- 用户输入
- 交互模式
- 当前任务目标
- 核心字段
- A/B/C/D/E 字段状态
- 知识查询任务
- 检索结果
- 证据片段
- LLM 决策动作
- 草案内容
- 字段报告
- 用户确认记录
- trace

聊天消息可以存在，但不作为主状态。字段状态比 messages 更重要。

### 5.6 Knowledge Provider

Knowledge Provider 是黑盒知识获取层。

第一阶段：

```text
KnowledgeProvider
├── LocalDocumentProvider
├── WebSearchProvider
└── LLMSemanticReasoning
```

`WebSearchProvider` 必须接入真实联网搜索服务，不使用 mock provider 作为开发路径。第一阶段通过 `.env` 中的 `WEB_SEARCH_PROVIDER` 选择实现，例如：

```text
tavily
brave
openai_compatible_web_search，可选
```

所有 provider 必须输出统一的 `SearchResult`，保留 query、provider、URL、title、snippet、raw_content、score 和检索时间等信息，便于后续转为 Evidence。

未来可扩展：

```text
KnowledgeProvider
├── StandardDocumentProvider
├── MaterialDatabaseProvider
├── FillerDatabaseProvider
├── EnterpriseTemplateProvider
├── PQRProvider
└── WPQProvider
```

Supervisor、Domain Skill 和 Runtime Tool 不依赖具体实现，只依赖统一返回结构。

---

## 6. LangGraph 结构建议

目录中的 `graph` 层主要实现运行时和路由：

```text
src/pwps_agent/graph/
├── builder.py        # 构建 LangGraph
├── state.py          # PWPSState 类型
├── supervisor.py     # LLM Supervisor Node
├── router.py         # AgentAction 路由
├── subflows.py       # auto_draft / guided_confirmation / supplement_update
└── checkpoints.py    # checkpoint 和状态恢复
```

推荐的 graph 节点：

```text
START
  ↓
supervisor
  ↓
route_action
  ├── tool_node
  ├── ask_user_node
  ├── compose_node
  ├── report_node
  └── END
```

所有执行节点完成后返回 Supervisor，形成 LLM 主导的循环。

---

## 7. AgentAction 机制

Supervisor 每轮输出结构化动作：

```json
{
  "action_type": "CALL_TOOL",
  "tool_name": "web_search",
  "tool_args": {
    "query": "Q355B 12mm GMAW butt joint flat position pWPS WPS"
  },
  "state_update_intent": "retrieve_similar_case",
  "rationale_summary": "用户核心信息基本齐全，需要查找相似案例和参数参考。"
}
```

动作类型建议：

```text
USE_DOMAIN_SKILL
CALL_TOOL
UPDATE_STATE
ASK_USER
COMPOSE_DRAFT
GENERATE_REPORT
FINISH
```

`USE_DOMAIN_SKILL` 只用于记录或选择 Domain Skill 指导上下文；执行具体能力应使用 `CALL_TOOL`。`rationale_summary` 是可记录的简要理由，不要求保存私有推理链。

---

## 8. 字段分区

系统重点覆盖 pWPS 的 A/B/C/D/E：

```text
A. 文件与项目元信息
B. 焊接适用范围
C. 焊材与辅助材料
D. 焊接参数
E. 热处理与温控
```

所有字段都必须进入 `PWPSState.fields`，即使缺失也应存在状态：

```text
missing / candidate / filled / suggested / user_confirmed / conflict / need_confirmation
```

---

## 9. 项目目录结构

```text
pwps-agent/
├── configs/
│   ├── agent.yaml
│   ├── model.yaml
│   ├── workflow.yaml
│   ├── state_schema.yaml
│   ├── fields_schema.yaml
│   ├── knowledge.yaml
│   └── prompts/
│       ├── supervisor.md
│       ├── auto_draft.md
│       ├── guided_confirmation.md
│       ├── requirement_understanding.md
│       ├── knowledge_planning.md
│       ├── evidence_reading.md
│       ├── field_reasoning.md
│       ├── section_generation.md
│       └── risk_report.md
│
├── data/
│   ├── local_docs/
│   ├── index/
│   └── outputs/
│
├── src/
│   └── pwps_agent/
│       ├── graph/
│       ├── agent/
│       ├── domain_skills/
│       ├── tools/
│       ├── core/
│       ├── knowledge/
│       ├── retrieval/
│       ├── llm/
│       ├── render/
│       ├── storage/
│       └── utils/
│
├── scripts/
└── tests/
```

---

## 10. 输出文件

系统输出：

```text
pwps.json
pwps_draft.md
pwps_draft.html，可选
field_report.json
field_report.md，可选
trace.json
```

`pWPS 草案`应包含：

1. 文件与项目元信息。
2. 焊接适用范围。
3. 焊材与辅助材料。
4. 焊接参数。
5. 热处理与温控。
6. 缺失字段。
7. 候选值和建议值。
8. 风险提示。

---

## 11. 架构原则

1. LLM Supervisor 是工作流主角。
2. LangGraph 负责状态流转、可回放、工具执行和中断恢复。
3. Domain Skill 是模型指导经验包，不是运行时工具，也不是决策主体。
4. Runtime Tool 是执行能力，不替代 Supervisor 做总体决策。
5. 第一阶段不预编码复杂焊接业务规则，不构建规则引擎。
6. Schema 约束数据结构，但不替代 LLM 的专业判断。
7. Knowledge Provider 黑盒化，当前接本地文档和网络搜索，未来可接数据库。
8. 所有中间结果必须进入 PWPSState。
9. 字段必须记录来源、证据、置信度、候选状态、确认状态和待确认说明。
10. 草案不是正式结论，输出必须标明 draft 属性。
11. LLM 可以主动决定是否继续检索、是否追问、是否生成草案、是否结束。
