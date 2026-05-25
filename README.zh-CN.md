# pWPS Agent

[English](README.md)

`pWPS Agent` 是一个第一阶段的 **LLM 主导 pWPS 草案生成 Agent**。它面向焊接工艺文件的草案生成，使用单一 LLM Supervisor、Domain Skills、运行时工具、`PWPSState`、LangGraph 编排、本地文档检索、网络搜索和结构化输出契约，把用户的焊接需求整理成可追踪的 pWPS draft。

这个项目的目标是帮助工程人员更快形成草案、整理字段、暴露缺失项和风险项。它不会生成正式批准、签字或保证合规的焊接工艺文件。

## 当前能力

当前阶段已经支持：

- 通过 LangGraph 执行 `auto_draft` CLI 流程。
- 使用 LLM 结构化抽取用户焊接需求。
- 由模型规划检索问题，而不是固定拼接搜索词。
- 检索本地 `.md`、`.markdown`、`.txt` 文档。
- 接入真实网络搜索 provider。
- 将检索结果转换为结构化证据，并建立证据到字段的关联。
- 基于证据推理字段候选值。
- 显式记录 Domain Skill 选择和运行 trace。
- 支持 guided confirmation 的状态服务、CLI 命令和轻量本地 Web UI/API。
- 支持基于 `run_id` 的 checkpoint 恢复 guided confirmation。
- 支持对已保存状态或 checkpoint 做 supplemental update。
- 生成 A/B/C/D/E 结构化草案章节。
- 生成字段来源、缺失项和风险报告。
- 持久化运行产物：
  - `pwps.json`
  - `pwps_draft.md`
  - `field_report.json`
  - `trace.json`
  - `evidence_index.json`

## 安全边界

所有输出都只是草案辅助。

- 未知项目元信息保持空白或 `待确认`。
- 网络来源和 LLM 推理得到的值只能作为候选值、建议值或参考值，除非用户明确确认。
- 预热、层间温度、PWHT、热输入、资质覆盖等高风险字段必须谨慎复核。
- 系统不做 PQR/WPQR 覆盖性判定。
- 系统不能替代焊接工程师审核和正式审批。

## 环境要求

- Python `>=3.14`
- `uv`
- 兼容 OpenAI API 形状的 LLM provider
- 可选：网络搜索 provider 凭据

安装依赖：

```bash
uv sync
```

## 配置

复制 `.env.template` 为仓库根目录下的 `.env`，然后填入真实凭据。不要提交真实密钥。

最小 LLM 配置：

```text
LLM_API_KEY=...
LLM_BASE_URL=https://api.example.com
LLM_MODEL=...
LLM_TEMPERATURE=0.2
LLM_STRUCTURED_OUTPUT_METHOD=function_calling
LLM_THINKING_TYPE=disabled
```

图运行时默认使用 LLM Supervisor 输出结构化 `AgentAction`。确定性动作选择只保留为内部安全辅助，不作为运行模式暴露。

交互模式行为：

- `auto_draft`：自动草稿模式。Supervisor 不应暂停询问用户，而是按配置检索本地/网络来源；模型兜底只能生成低置信度 `suggested` 值，并在不确定性可见的前提下完成草稿。
- `guided_confirmation`：人机协同确认模式。Supervisor 会在关键输入缺失、候选/建议/冲突字段未确认时暂停，给出选项、依据和解释，引导用户确认、修改或暂缓。

网络搜索配置示例：

```text
WEB_SEARCH_PROVIDER=tavily
TAVILY_API_KEY=...
```

或：

```text
WEB_SEARCH_PROVIDER=brave
BRAVE_SEARCH_API_KEY=...
```

运行路径配置：

```text
KNOWLEDGE_SOURCES=local_doc,web
PWPS_LOCAL_DOCS_DIR=data/local_docs
PWPS_OUTPUT_DIR=data/outputs
LOCAL_DOC_MAX_RESULTS=5
LOCAL_DOC_SNIPPET_CHARS=420
```

本地文档可以放在 `data/local_docs`，当前支持 `.md`、`.markdown`、`.txt`。如果暂时没有本地知识库，可以设置 `KNOWLEDGE_SOURCES=web,model`，这样会跳过本地检索，并在网络证据不可用时允许模型知识兜底。

## 快速运行

执行一次真实 auto-draft smoke：

```bash
uv run pwps-agent auto-draft \
  "Q355B 12mm plate GMAW butt joint flat position AWS D1.1 pWPS draft" \
  --output-dir /tmp/pwps-agent-demo \
  --run-id demo_q355b_gmaw
```

成功后会输出运行目录：

```text
/tmp/pwps-agent-demo/demo_q355b_gmaw
```

查看生成文件：

```bash
find /tmp/pwps-agent-demo/demo_q355b_gmaw -maxdepth 1 -type f -print
sed -n '1,180p' /tmp/pwps-agent-demo/demo_q355b_gmaw/pwps_draft.md
```

验证持久化状态可以重新加载：

```bash
uv run python -c "from pathlib import Path; from pwps_agent.core.state import PWPSState; PWPSState.model_validate_json(Path('/tmp/pwps-agent-demo/demo_q355b_gmaw/pwps.json').read_text(encoding='utf-8')); print('state reload ok')"
```

## CLI 命令

### 自动生成草案

```bash
uv run pwps-agent auto-draft \
  "Q355B 12mm plate GMAW butt joint flat position AWS D1.1 pWPS draft" \
  --output-dir /tmp/pwps-agent-demo \
  --run-id demo_auto
```

### 查看待确认字段

```bash
uv run pwps-agent guided-confirm-view /path/to/pwps.json
```

### 在状态文件中确认字段

```bash
uv run pwps-agent guided-confirm /path/to/pwps.json \
  --set filler_material=ER50-6 \
  --message "Confirm filler material" \
  --reason "Engineer accepted for draft"
```

### 确认字段并从状态文件继续生成

```bash
uv run pwps-agent guided-confirm-resume /path/to/pwps.json \
  --set filler_material=ER50-6 \
  --message "Confirm and resume" \
  --output-dir /tmp/pwps-guided-out
```

### 从最新 checkpoint 确认并继续

```bash
uv run pwps-agent guided-confirm-resume-run demo_auto \
  --set filler_material=ER50-6 \
  --message "Confirm from checkpoint" \
  --output-dir /tmp/pwps-agent-demo
```

该命令会读取：

```text
<output_dir>/<run_id>/checkpoints/latest.json
```

### 对保存的状态补充信息

```bash
uv run pwps-agent supplement-state /path/to/pwps.json \
  --message "Base material standard is GB/T 1591." \
  --set base_material_standard="GB/T 1591" \
  --output-dir /tmp/pwps-supplement-out
```

### 从 checkpoint 补充信息

```bash
uv run pwps-agent supplement-run demo_auto \
  --message "Shielding gas is 80% Ar / 20% CO2." \
  --set shielding_gas="80% Ar / 20% CO2" \
  --output-dir /tmp/pwps-agent-demo
```

### 本地 guided confirmation Web UI

```bash
uv run pwps-agent guided-confirm-web /path/to/pwps.json --host 127.0.0.1 --port 8765
```

浏览器打开：

```text
http://127.0.0.1:8765
```

## 输出文件

每次成功运行会写出：

```text
pwps.json
pwps_draft.md
field_report.json
trace.json
evidence_index.json
```

`pwps.json` 是结构化状态。`pwps_draft.md` 是可读草案。`field_report.json` 记录缺失字段、候选字段、已确认字段、冲突、保留候选、证据和风险信息。`trace.json` 记录图运行、Supervisor 动作和工具结果。`evidence_index.json` 记录证据到字段、字段到证据的映射。

## 架构

高层结构：

```text
LLM Supervisor Agent
  + Domain Skills
  + Runtime Tools
  + PWPSState
  + Knowledge Providers
  + LangGraph Runtime
```

主要模块：

- `src/pwps_agent/graph/`：LangGraph 运行时、路由、checkpoint、节点。
- `src/pwps_agent/core/`：数据契约、字段状态、状态合并、交互服务。
- `src/pwps_agent/tools/`：需求抽取、知识规划、证据处理、本地文档、章节生成、风险报告等运行时工具。
- `src/pwps_agent/knowledge/`：本地文档和网络搜索 provider。
- `src/pwps_agent/domain_skills/`：给 Supervisor 使用的 Markdown 指导包。
- `src/pwps_agent/render/`：Markdown 渲染。
- `src/pwps_agent/storage/`：运行产物持久化。
- `src/pwps_agent/web/`：轻量 guided confirmation Web UI/API。

设计文档：

- `docs/architecture.md`
- `docs/agent_design.md`
- `docs/requirements.md`
- `docs/data_schema.md`
- `docs/superpowers/plans/2026-05-24-stage-one-completion-roadmap.md`

## 开发与验证

运行重点测试：

```bash
uv run pytest tests/test_graph_auto_draft.py -q
uv run pytest tests/test_guided_confirmation_resume.py -q
uv run pytest tests/test_graph_supplement_update.py -q
```

运行完整验证：

```bash
uv run pytest -q
uv run python -m compileall -q src tests
git diff --check
```

当前完整测试基线：

```text
97 passed, 1 warning
```

## 项目状态

Stage one 已经基本可运行，但仍处于活跃开发阶段。

剩余计划：

- Phase 8：确定性 smoke harness 和 sample run scripts。
- Phase 9：生产化加固，包括错误处理、文档、配置和 CLI 打磨。

路线图见：

```text
docs/superpowers/plans/2026-05-24-stage-one-completion-roadmap.md
```
