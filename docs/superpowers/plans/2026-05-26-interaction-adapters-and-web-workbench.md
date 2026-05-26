# Interaction Adapters And Web Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor pWPS runtime interaction so `auto_draft` and `guided_confirmation` are product modes, while CLI and React Web are adapters over the same graph pause/resume protocol.

**Architecture:** Keep LangGraph and `PWPSState.pending_interaction` as the runtime authority. Add a shared interaction normalizer for messy user input, move terminal rendering out of `cli.py`, replace the old guided-only embedded Web UI with a mode-neutral API plus a React workbench.

**Tech Stack:** Python 3.14, Pydantic, LangGraph, stdlib HTTP server for the first backend API slice, React + Vite + TypeScript + plain CSS for the workbench.

---

## File Structure

- Create `src/pwps_agent/interaction/__init__.py`: package marker for adapter-neutral interaction helpers.
- Create `src/pwps_agent/interaction/normalizer.py`: parse option numbers, `field=value`, exact option labels, and free-form text into a structured response payload.
- Create `src/pwps_agent/interaction/terminal.py`: render `InteractionRequest` for terminal and read raw user answers.
- Create `src/pwps_agent/interaction/runtime.py`: shared loop that turns `need_user_input` states into adapter calls and resumes through `resume_interaction()`.
- Modify `src/pwps_agent/cli.py`: keep command routing only; delegate interactive behavior to `interaction.runtime` and `interaction.terminal`.
- Create `src/pwps_agent/web/runtime_api.py`: mode-neutral local HTTP API for runs, responses, supplements, and artifacts.
- Modify `src/pwps_agent/web/guided_confirmation.py`: mark as compatibility wrapper and route `guided-confirm-web` into the new runtime API.
- Modify `src/pwps_agent/cli.py`: add or retarget a `web-workbench` command while keeping `guided-confirm-web` as a compatibility alias.
- Create `web/package.json`, `web/index.html`, `web/tsconfig.json`, `web/vite.config.ts`: React workbench project.
- Create `web/src/app/types.ts`, `web/src/app/api.ts`, `web/src/app/App.tsx`: frontend types, API client, and app shell.
- Create `web/src/components/*.tsx`: workbench components for header, interaction panel, field state, draft preview, evidence drawer, event timeline, and confirmation history.
- Create `web/src/styles/app.css`: domain-specific operational UI styling.
- Modify `tests/test_cli.py`: adjust CLI tests to target adapter behavior through new modules.
- Create `tests/test_interaction_normalizer.py`: normalizer contract tests.
- Create `tests/test_cli_interaction_adapter.py`: terminal adapter tests.
- Create `tests/test_web_runtime_api.py`: mode-neutral Web API tests.
- Modify `tests/test_guided_confirmation_web.py`: reduce to compatibility wrapper coverage or delete if fully replaced.
- Modify `AGENTS.md`: update progress and usage notes after implementation.
- Modify `docs/superpowers/plans/2026-05-25-llm-led-dual-mode-hardening.md`: reference this plan as the follow-up structure change.

---

### Task 1: Add Interaction Normalizer Contract

**Files:**
- Create: `src/pwps_agent/interaction/__init__.py`
- Create: `src/pwps_agent/interaction/normalizer.py`
- Test: `tests/test_interaction_normalizer.py`

- [x] **Step 1: Write failing normalizer tests**

Create `tests/test_interaction_normalizer.py`:

```python
from pwps_agent.core.interaction import InteractionOption, InteractionQuestion, InteractionRequest
from pwps_agent.interaction.normalizer import normalize_interaction_response


def _request() -> dict:
    return InteractionRequest(
        request_id="run1:guided_field_confirmation:1",
        interaction_mode="guided_confirmation",
        purpose="guided_field_confirmation",
        title="确认关键焊接选择",
        summary="请选择焊材。",
        questions=[
            InteractionQuestion(
                question_id="confirm_filler_material",
                field_ids=["filler_material"],
                prompt="请选择焊材。",
                input_kind="single_choice",
                options=[
                    InteractionOption(
                        value="ER50-6",
                        label="ER50-6",
                        suitability="适合 Q355B GMAW。",
                        recommended=True,
                        evidence_ids=["ev1"],
                        field_updates={"filler_material": "ER50-6"},
                    )
                ],
            )
        ],
    ).model_dump()


def test_normalizer_accepts_option_number() -> None:
    payload = normalize_interaction_response(_request(), "1")

    assert payload["fields"] == {"filler_material": "ER50-6"}
    assert payload["selected_options"] == ["confirm_filler_material:1"]
    assert payload["evidence_ids_shown"] == ["ev1"]
    assert payload["unresolved_text"] == ""


def test_normalizer_accepts_field_value_pairs() -> None:
    payload = normalize_interaction_response(
        _request(),
        "filler_material=ER50-6, shielding_gas=80% Ar / 20% CO2",
    )

    assert payload["fields"] == {
        "filler_material": "ER50-6",
        "shielding_gas": "80% Ar / 20% CO2",
    }


def test_normalizer_accepts_exact_option_label() -> None:
    payload = normalize_interaction_response(_request(), "ER50-6")

    assert payload["fields"] == {"filler_material": "ER50-6"}
    assert payload["selected_options"] == ["confirm_filler_material:1"]


def test_normalizer_preserves_free_text_for_llm_followup() -> None:
    payload = normalize_interaction_response(
        _request(),
        "我觉得用常规气保焊焊丝就行，但是型号不确定",
    )

    assert payload["fields"] == {}
    assert payload["message"] == "我觉得用常规气保焊焊丝就行，但是型号不确定"
    assert payload["unresolved_text"] == "我觉得用常规气保焊焊丝就行，但是型号不确定"
```

- [x] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/test_interaction_normalizer.py -q
```

Expected: fail because `pwps_agent.interaction.normalizer` does not exist.

- [x] **Step 3: Implement deterministic normalizer**

Create `src/pwps_agent/interaction/__init__.py`:

```python
"""Adapter-neutral interaction helpers."""
```

Create `src/pwps_agent/interaction/normalizer.py`:

```python
from __future__ import annotations

from typing import Any


def normalize_interaction_response(
    interaction: dict[str, Any],
    raw_text: str,
    explicit_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    text = raw_text.strip()
    fields = dict(explicit_fields or {})
    selected_options: list[str] = []
    evidence_ids: list[str] = []

    if text and not fields:
        fields, selected_options, evidence_ids = _parse_against_questions(interaction, text)

    unresolved_text = "" if fields else text
    return {
        "request_id": interaction.get("request_id"),
        "fields": fields,
        "selected_options": selected_options,
        "message": text or "User runtime interaction response.",
        "reason": "Normalized from user interaction response.",
        "evidence_ids_shown": evidence_ids,
        "action": "accepted",
        "unresolved_text": unresolved_text,
    }


def _parse_against_questions(
    interaction: dict[str, Any],
    text: str,
) -> tuple[dict[str, Any], list[str], list[str]]:
    if "=" in text:
        return _parse_field_pairs(text), [], []

    questions = list(interaction.get("questions") or [])
    if text.isdigit():
        option_index = int(text)
        if option_index >= 1:
            return _option_payload(questions, option_index)

    for question in questions:
        for index, option in enumerate(question.get("options") or [], start=1):
            values = {str(option.get("value") or ""), str(option.get("label") or "")}
            if text in values:
                fields = _field_updates(question, option)
                return fields, [f"{question.get('question_id')}:{index}"], _evidence_ids(option)

    return {}, [], []


def _parse_field_pairs(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for part in text.split(","):
        if "=" not in part:
            return {}
        field_id, value = part.split("=", 1)
        field_id = field_id.strip()
        value = value.strip()
        if not field_id or not value:
            return {}
        fields[field_id] = value
    return fields


def _option_payload(
    questions: list[dict[str, Any]],
    option_index: int,
) -> tuple[dict[str, Any], list[str], list[str]]:
    for question in questions:
        options = list(question.get("options") or [])
        if option_index <= len(options):
            option = options[option_index - 1]
            return (
                _field_updates(question, option),
                [f"{question.get('question_id')}:{option_index}"],
                _evidence_ids(option),
            )
    return {}, [], []


def _field_updates(question: dict[str, Any], option: dict[str, Any]) -> dict[str, Any]:
    updates = {
        str(field_id): value
        for field_id, value in dict(option.get("field_updates") or {}).items()
        if value not in (None, "")
    }
    if updates:
        return updates
    field_ids = [str(field_id) for field_id in question.get("field_ids") or []]
    if field_ids and option.get("value") not in (None, ""):
        return {field_ids[0]: option.get("value")}
    return {}


def _evidence_ids(option: dict[str, Any]) -> list[str]:
    return [str(evidence_id) for evidence_id in option.get("evidence_ids") or []]
```

- [x] **Step 4: Run normalizer tests**

Run:

```bash
uv run pytest tests/test_interaction_normalizer.py -q
```

Expected: pass.

- [x] **Step 5: Commit**

```bash
git add src/pwps_agent/interaction tests/test_interaction_normalizer.py
git commit -m "feat: add interaction response normalizer"
```

Task 1 completed with follow-up quality fixes:

```bash
uv run pytest tests/test_interaction_normalizer.py -q
9 passed

uv run pytest tests/test_interaction_normalizer.py tests/test_interaction_resume.py tests/test_guided_confirmation_resume.py -q
17 passed

uv run pytest -q
181 passed
```

Review notes resolved:
- Normalizer emits resume-compatible `accepted` / `modified` actions.
- Numeric shorthand resolves only when one option-bearing question exists.
- Exact option label/value resolves only when the match is unique.
- Exact numeric option values are preferred over numeric index shorthand.

---

### Task 2: Extract Terminal Adapter From CLI

**Files:**
- Create: `src/pwps_agent/interaction/terminal.py`
- Create: `src/pwps_agent/interaction/runtime.py`
- Modify: `src/pwps_agent/cli.py`
- Test: `tests/test_cli_interaction_adapter.py`
- Modify: `tests/test_cli.py`

- [x] **Step 1: Write failing terminal adapter tests**

Create `tests/test_cli_interaction_adapter.py`:

```python
from io import StringIO

from pwps_agent.core.interaction import InteractionOption, InteractionQuestion, InteractionRequest
from pwps_agent.interaction.terminal import collect_terminal_response, render_terminal_interaction


def _request() -> dict:
    return InteractionRequest(
        request_id="run1:guided_field_confirmation:1",
        interaction_mode="guided_confirmation",
        purpose="guided_field_confirmation",
        title="确认关键焊接选择",
        summary="agent 已整理候选。",
        questions=[
            InteractionQuestion(
                question_id="confirm_filler_material",
                field_ids=["filler_material"],
                prompt="请选择焊材。",
                input_kind="single_choice",
                options=[
                    InteractionOption(
                        value="ER50-6",
                        label="ER50-6",
                        suitability="适合 Q355B GMAW。",
                        risk_note="需核对适用标准。",
                        recommended=True,
                        evidence_ids=["ev1"],
                        field_updates={"filler_material": "ER50-6"},
                    )
                ],
            )
        ],
    ).model_dump()


def test_render_terminal_interaction_is_ordered_and_user_friendly() -> None:
    text = render_terminal_interaction(_request())

    assert "[需要用户输入] 确认关键焊接选择" in text
    assert "agent 已整理候选。" in text
    assert "1. ER50-6 [推荐]" in text
    assert "适用性: 适合 Q355B GMAW。" in text
    assert "风险: 需核对适用标准。" in text


def test_collect_terminal_response_returns_raw_text() -> None:
    stdout = StringIO()
    raw = collect_terminal_response(_request(), stdin=StringIO("1\n"), stdout=stdout)

    assert raw == "1"
    assert "请选择焊材。" in stdout.getvalue()
```

- [x] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/test_cli_interaction_adapter.py -q
```

Expected: fail because `terminal.py` does not exist.

- [x] **Step 3: Implement terminal adapter**

Create `src/pwps_agent/interaction/terminal.py`:

```python
from __future__ import annotations

from typing import Any, TextIO


def render_terminal_interaction(interaction: dict[str, Any]) -> str:
    lines = [
        "",
        f"[需要用户输入] {interaction.get('title', 'Runtime interaction')}",
    ]
    summary = interaction.get("summary")
    if summary:
        lines.append(str(summary))
    assistant_message = interaction.get("assistant_message")
    if assistant_message:
        lines.extend(["", str(assistant_message)])

    for question in interaction.get("questions") or []:
        lines.extend(["", str(question.get("prompt") or "请补充信息。")])
        for index, option in enumerate(question.get("options") or [], start=1):
            marker = " [推荐]" if option.get("recommended") else ""
            label = option.get("label") or option.get("value")
            lines.append(f"{index}. {label}{marker}")
            if option.get("suitability"):
                lines.append(f"   适用性: {option['suitability']}")
            if option.get("risk_note"):
                lines.append(f"   风险: {option['risk_note']}")
    return "\n".join(lines)


def collect_terminal_response(
    interaction: dict[str, Any],
    *,
    stdin: TextIO,
    stdout: TextIO,
) -> str:
    stdout.write(render_terminal_interaction(interaction))
    stdout.write("\n\n输入编号、字段值或自然语言补充: ")
    stdout.flush()
    value = stdin.readline()
    if value == "":
        raise EOFError("Input ended while waiting for runtime interaction response.")
    value = value.strip()
    if not value:
        raise ValueError("Runtime interaction response cannot be empty.")
    return value
```

- [x] **Step 4: Implement shared interactive runtime loop**

Create `src/pwps_agent/interaction/runtime.py`:

```python
from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any, TextIO

from pwps_agent.config import Settings
from pwps_agent.core.state import PWPSState
from pwps_agent.interaction.normalizer import normalize_interaction_response
from pwps_agent.interaction.terminal import collect_terminal_response
from pwps_agent.workflows.auto_draft import AutoDraftResult
from pwps_agent.workflows.interaction_resume import resume_interaction


RawResponseCollector = Callable[[dict[str, Any], TextIO, TextIO], str]


def continue_interactive_run(
    result: AutoDraftResult,
    settings: Settings,
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    collector: RawResponseCollector | None = None,
) -> AutoDraftResult:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    collector = collector or _collect

    current = result
    while should_prompt_inline(current.state, stdin=stdin):
        interaction = current.state.pending_interaction or {}
        raw_text = collector(interaction, stdin, stdout)
        payload = normalize_interaction_response(interaction, raw_text)
        current = resume_interaction(current.state, payload, settings=settings)
    return AutoDraftResult(state=current.state, output_dir=current.output_dir)


def should_prompt_inline(state: PWPSState, *, stdin: TextIO | None = None) -> bool:
    stdin = stdin or sys.stdin
    return (
        state.status == "need_user_input"
        and bool(state.pending_interaction)
        and stdin.isatty()
    )


def _collect(interaction: dict[str, Any], stdin: TextIO, stdout: TextIO) -> str:
    return collect_terminal_response(interaction, stdin=stdin, stdout=stdout)
```

- [x] **Step 5: Slim `cli.py`**

Modify `src/pwps_agent/cli.py`:

```python
from pwps_agent.interaction.runtime import continue_interactive_run
```

Replace each call to `_continue_interactive_run(result, settings)` with:

```python
result = continue_interactive_run(result, settings)
```

Delete `_continue_interactive_run`, `_should_prompt_inline`,
`_read_interaction_payload`, `_prompt_for_question`, `_print_options`,
`_fields_from_option_input`, `_parse_inline_field_values`, and
`_read_required_line` from `src/pwps_agent/cli.py`.

- [x] **Step 6: Run CLI tests**

Run:

```bash
uv run pytest tests/test_cli_interaction_adapter.py tests/test_cli.py -q
```

Expected: pass.

- [x] **Step 7: Commit**

```bash
git add src/pwps_agent/interaction src/pwps_agent/cli.py tests/test_cli.py tests/test_cli_interaction_adapter.py
git commit -m "refactor: move terminal interaction into adapter"
```

Task 2 completed with follow-up quality fixes:

```bash
uv run pytest tests/test_cli_interaction_adapter.py tests/test_cli.py tests/test_interaction_normalizer.py -q
33 passed

uv run pytest tests/test_interaction_resume.py tests/test_guided_confirmation_resume.py -q
8 passed

uv run pytest tests/test_cli_interaction_adapter.py tests/test_cli.py tests/test_interaction_normalizer.py tests/test_interaction_resume.py tests/test_guided_confirmation_resume.py -q
41 passed
```

Review notes resolved:
- Multi-question option prompts are collected per question before normalization.
- Required terminal free-text answers map to requested fields instead of empty payloads.
- `src/pwps_agent/cli.py` delegates draft interaction handling to `pwps_agent.interaction.runtime`.

---

### Task 3: Add Mode-Neutral Web Runtime API

**Files:**
- Create: `src/pwps_agent/web/runtime_api.py`
- Modify: `src/pwps_agent/web/__init__.py`
- Modify: `src/pwps_agent/web/guided_confirmation.py`
- Modify: `src/pwps_agent/cli.py`
- Test: `tests/test_web_runtime_api.py`
- Modify: `tests/test_guided_confirmation_web.py`

- [ ] **Step 1: Write failing Web API tests**

Create `tests/test_web_runtime_api.py`:

```python
from pathlib import Path

from pwps_agent.core.interaction import attach_interaction_request, build_initial_info_request
from pwps_agent.core.state import create_initial_state
from pwps_agent.web.runtime_api import (
    apply_run_response,
    build_run_snapshot,
    load_run_state,
    save_run_state,
)


def test_run_snapshot_is_mode_neutral(tmp_path: Path) -> None:
    state = create_initial_state("Need pWPS", "auto_draft", run_id="api_auto")
    state.status = "need_user_input"
    attach_interaction_request(state, build_initial_info_request(state))

    snapshot = build_run_snapshot(state, output_dir=tmp_path / "api_auto")

    assert snapshot["run_id"] == "api_auto"
    assert snapshot["mode"] == "auto_draft"
    assert snapshot["status"] == "need_user_input"
    assert snapshot["pending_interaction"]["purpose"] == "initial_minimum_context"
    assert "fields" in snapshot


def test_run_state_round_trip(tmp_path: Path) -> None:
    state = create_initial_state("Need pWPS", "auto_draft", run_id="api_roundtrip")
    save_run_state(tmp_path, state)

    loaded = load_run_state(tmp_path, "api_roundtrip")

    assert loaded.run_id == "api_roundtrip"


def test_apply_run_response_normalizes_raw_text(monkeypatch, tmp_path: Path) -> None:
    state = create_initial_state("Need pWPS", "auto_draft", run_id="api_response")
    state.status = "need_user_input"
    attach_interaction_request(state, build_initial_info_request(state))
    save_run_state(tmp_path, state)

    def fake_resume_interaction(state, payload, settings):
        updated = state.model_copy(deep=True)
        updated.status = "done"
        updated.pending_interaction = None
        updated.fields["base_material"].value = payload["fields"]["base_material"]
        return type("Result", (), {"state": updated, "output_dir": str(tmp_path / state.run_id)})()

    monkeypatch.setattr("pwps_agent.web.runtime_api.resume_interaction", fake_resume_interaction)

    snapshot = apply_run_response(
        tmp_path,
        "api_response",
        {"message": "base_material=Q355B"},
    )

    assert snapshot["status"] == "done"
    assert snapshot["fields"]["base_material"]["value"] == "Q355B"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/test_web_runtime_api.py -q
```

Expected: fail because `runtime_api.py` does not exist.

- [ ] **Step 3: Implement Web runtime API helpers**

Create `src/pwps_agent/web/runtime_api.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

from pwps_agent.config import Settings
from pwps_agent.core.state import PWPSState
from pwps_agent.interaction.normalizer import normalize_interaction_response
from pwps_agent.render.markdown import render_field_report
from pwps_agent.workflows.interaction_resume import resume_interaction


def build_run_snapshot(state: PWPSState, output_dir: Path) -> dict[str, Any]:
    return {
        "run_id": state.run_id,
        "mode": state.interaction_mode,
        "status": state.status,
        "pending_interaction": state.pending_interaction,
        "interaction_requests": state.interaction_requests,
        "fields": {
            field_id: field.model_dump()
            for field_id, field in state.fields.items()
        },
        "field_report": state.field_report or render_field_report(state),
        "quality_report": state.quality_report,
        "confirmations": [record.model_dump() for record in state.confirmations],
        "trace": state.trace,
        "has_draft": bool(state.draft_markdown),
        "draft_markdown": state.draft_markdown,
        "output_dir": str(output_dir),
    }


def save_run_state(base_output_dir: Path, state: PWPSState) -> Path:
    run_dir = base_output_dir / state.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    state_path = run_dir / "pwps.json"
    state_path.write_text(state.model_dump_json(indent=2), encoding="utf-8")
    return state_path


def load_run_state(base_output_dir: Path, run_id: str) -> PWPSState:
    state_path = base_output_dir / run_id / "pwps.json"
    return PWPSState.model_validate_json(state_path.read_text(encoding="utf-8"))


def apply_run_response(
    base_output_dir: Path,
    run_id: str,
    payload: dict[str, Any],
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or Settings()
    settings.paths.output_dir = base_output_dir
    state = load_run_state(base_output_dir, run_id)
    interaction = state.pending_interaction or {}
    response = normalize_interaction_response(
        interaction,
        str(payload.get("message") or ""),
        explicit_fields=payload.get("fields"),
    )
    result = resume_interaction(state, response, settings=settings)
    save_run_state(base_output_dir, result.state)
    return build_run_snapshot(result.state, Path(result.output_dir))
```

- [ ] **Step 4: Convert legacy guided Web module to compatibility wrapper**

Modify `src/pwps_agent/web/guided_confirmation.py` so public helpers delegate
where possible:

```python
from pwps_agent.web.runtime_api import build_run_snapshot


def web_state_payload(state: PWPSState) -> dict[str, Any]:
    return {
        **build_run_snapshot(state, Path(".")),
        "confirmation_view": build_confirmation_view(state),
    }
```

Keep `apply_confirmation_payload()` and existing tests temporarily if needed,
but mark `render_guided_confirmation_html()` as legacy in its docstring.

- [ ] **Step 5: Add CLI command for new workbench**

Modify `src/pwps_agent/cli.py` parser:

```python
web_workbench = subparsers.add_parser("web-workbench")
web_workbench.add_argument("--output-dir", type=Path, default=None)
web_workbench.add_argument("--host", default="127.0.0.1")
web_workbench.add_argument("--port", type=int, default=8765)
```

Wire command to the new server entrypoint added in Task 4. Keep
`guided-confirm-web` as compatibility for a state path until Task 5 removes the
embedded UI.

- [ ] **Step 6: Run Web API tests**

Run:

```bash
uv run pytest tests/test_web_runtime_api.py tests/test_guided_confirmation_web.py -q
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add src/pwps_agent/web src/pwps_agent/cli.py tests/test_web_runtime_api.py tests/test_guided_confirmation_web.py
git commit -m "feat: add mode-neutral web runtime api"
```

---

### Task 4: Add React Workbench Project

**Files:**
- Create: `web/package.json`
- Create: `web/index.html`
- Create: `web/tsconfig.json`
- Create: `web/vite.config.ts`
- Create: `web/src/app/types.ts`
- Create: `web/src/app/api.ts`
- Create: `web/src/app/App.tsx`
- Create: `web/src/components/RunHeader.tsx`
- Create: `web/src/components/InteractionPanel.tsx`
- Create: `web/src/components/FieldStatusPanel.tsx`
- Create: `web/src/components/DraftPreview.tsx`
- Create: `web/src/components/EvidenceDrawer.tsx`
- Create: `web/src/components/EventTimeline.tsx`
- Create: `web/src/components/ConfirmationHistory.tsx`
- Create: `web/src/styles/app.css`

- [ ] **Step 1: Create frontend package**

Create `web/package.json`:

```json
{
  "scripts": {
    "dev": "vite --host 127.0.0.1",
    "build": "tsc --noEmit && vite build",
    "test": "tsc --noEmit"
  },
  "dependencies": {
    "@vitejs/plugin-react": "^5.0.0",
    "vite": "^7.0.0",
    "typescript": "^5.8.0",
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "lucide-react": "^0.468.0"
  },
  "devDependencies": {}
}
```

Create `web/index.html`:

```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>pWPS Workbench</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/app/App.tsx"></script>
  </body>
</html>
```

Create `web/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "useDefineForClassFields": true,
    "lib": ["DOM", "DOM.Iterable", "ES2022"],
    "allowJs": false,
    "skipLibCheck": true,
    "esModuleInterop": true,
    "allowSyntheticDefaultImports": true,
    "strict": true,
    "forceConsistentCasingInFileNames": true,
    "module": "ESNext",
    "moduleResolution": "Node",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx"
  },
  "include": ["src"]
}
```

Create `web/vite.config.ts`:

```ts
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8765"
    }
  }
});
```

- [ ] **Step 2: Create frontend types**

Create `web/src/app/types.ts`:

```ts
export type FieldState = {
  field_id: string;
  section: "A" | "B" | "C" | "D" | "E";
  label: string;
  value: string | number | null;
  status: string;
  confidence: string;
  source?: Record<string, unknown> | null;
  evidence_ids: string[];
  candidates: Array<Record<string, unknown>>;
  note?: string | null;
};

export type InteractionOption = {
  value: unknown;
  label?: string | null;
  suitability?: string | null;
  risk_note?: string | null;
  recommended?: boolean;
  evidence_ids?: string[];
  field_updates?: Record<string, unknown>;
};

export type InteractionQuestion = {
  question_id: string;
  field_ids: string[];
  prompt: string;
  input_kind: string;
  required: boolean;
  options: InteractionOption[];
};

export type InteractionRequest = {
  request_id: string;
  interaction_mode: string;
  purpose: string;
  title: string;
  summary: string;
  assistant_message?: string;
  questions: InteractionQuestion[];
};

export type RunSnapshot = {
  run_id: string;
  mode: string;
  status: string;
  pending_interaction?: InteractionRequest | null;
  fields: Record<string, FieldState>;
  trace: Array<Record<string, unknown>>;
  confirmations: Array<Record<string, unknown>>;
  field_report: Record<string, unknown>;
  draft_markdown: string;
  output_dir: string;
};
```

- [ ] **Step 3: Create API client**

Create `web/src/app/api.ts`:

```ts
import type { RunSnapshot } from "./types";

export async function fetchRun(runId: string): Promise<RunSnapshot> {
  const response = await fetch(`/api/runs/${encodeURIComponent(runId)}`);
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

export async function respondToRun(runId: string, message: string): Promise<RunSnapshot> {
  const response = await fetch(`/api/runs/${encodeURIComponent(runId)}/respond`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ message })
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}
```

- [ ] **Step 4: Create app shell and components**

Create `web/src/app/App.tsx`:

```tsx
import { useEffect, useState } from "react";
import { fetchRun, respondToRun } from "./api";
import type { RunSnapshot } from "./types";
import { RunHeader } from "../components/RunHeader";
import { InteractionPanel } from "../components/InteractionPanel";
import { FieldStatusPanel } from "../components/FieldStatusPanel";
import { DraftPreview } from "../components/DraftPreview";
import { EvidenceDrawer } from "../components/EvidenceDrawer";
import { EventTimeline } from "../components/EventTimeline";
import { ConfirmationHistory } from "../components/ConfirmationHistory";
import "../styles/app.css";

const initialRunId = new URLSearchParams(window.location.search).get("run_id") || "run_cli";

export default function App() {
  const [runId, setRunId] = useState(initialRunId);
  const [snapshot, setSnapshot] = useState<RunSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refresh(nextRunId = runId) {
    try {
      setError(null);
      setSnapshot(await fetchRun(nextRunId));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function respond(message: string) {
    if (!snapshot) return;
    setSnapshot(await respondToRun(snapshot.run_id, message));
  }

  useEffect(() => {
    void refresh(runId);
  }, [runId]);

  return (
    <main className="workbench">
      <RunHeader runId={runId} onRunIdChange={setRunId} snapshot={snapshot} onRefresh={() => refresh()} />
      {error ? <div className="error">{error}</div> : null}
      <section className="workbench-grid">
        <EventTimeline trace={snapshot?.trace ?? []} />
        <InteractionPanel interaction={snapshot?.pending_interaction ?? null} onRespond={respond} />
        <FieldStatusPanel fields={snapshot?.fields ?? {}} />
        <DraftPreview markdown={snapshot?.draft_markdown ?? ""} />
        <EvidenceDrawer report={snapshot?.field_report ?? {}} />
        <ConfirmationHistory confirmations={snapshot?.confirmations ?? []} />
      </section>
    </main>
  );
}
```

Create each component as a focused presentational component. Keep the first
version simple and typed. Example for `InteractionPanel.tsx`:

```tsx
import { useState } from "react";
import type { InteractionRequest } from "../app/types";

export function InteractionPanel({
  interaction,
  onRespond
}: {
  interaction: InteractionRequest | null;
  onRespond: (message: string) => Promise<void>;
}) {
  const [message, setMessage] = useState("");
  if (!interaction) return <section className="panel primary"><h2>当前无需输入</h2></section>;

  return (
    <section className="panel primary">
      <h2>{interaction.title}</h2>
      <p>{interaction.summary}</p>
      {interaction.assistant_message ? <div className="assistant-message">{interaction.assistant_message}</div> : null}
      {interaction.questions.map((question) => (
        <div className="question" key={question.question_id}>
          <h3>{question.prompt}</h3>
          <div className="options">
            {question.options.map((option, index) => (
              <button key={index} type="button" onClick={() => setMessage(String(index + 1))}>
                {index + 1}. {String(option.label ?? option.value)}
                {option.recommended ? " 推荐" : ""}
              </button>
            ))}
          </div>
        </div>
      ))}
      <textarea value={message} onChange={(event) => setMessage(event.target.value)} placeholder="可以输入编号、字段值，或直接用自然语言补充。" />
      <button type="button" onClick={() => onRespond(message)}>提交并继续</button>
    </section>
  );
}
```

- [ ] **Step 5: Add operational CSS**

Create `web/src/styles/app.css` with stable layout:

```css
:root {
  color: #1b1f1d;
  background: #f4f0e8;
  font-family: "Noto Sans SC", "Source Han Sans SC", system-ui, sans-serif;
}

* { box-sizing: border-box; }
body { margin: 0; }
.workbench { min-height: 100vh; }
.run-header {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) auto auto;
  gap: 12px;
  align-items: center;
  padding: 14px 18px;
  border-bottom: 1px solid #c9c4b8;
  background: #fffaf0;
}
.workbench-grid {
  display: grid;
  grid-template-columns: 260px minmax(360px, 1.1fr) minmax(320px, .9fr);
  grid-template-rows: minmax(280px, auto) minmax(260px, 1fr);
  gap: 12px;
  padding: 12px;
}
.panel {
  background: #fffdf7;
  border: 1px solid #d7d0c2;
  border-radius: 8px;
  padding: 14px;
  min-width: 0;
}
.primary { grid-column: 2; grid-row: 1; }
.field-panel { grid-column: 3; grid-row: 1 / span 2; }
.draft-panel { grid-column: 2; grid-row: 2; }
.timeline-panel { grid-column: 1; grid-row: 1; }
.history-panel { grid-column: 1; grid-row: 2; }
.evidence-panel { grid-column: 2; grid-row: 2; align-self: end; max-height: 220px; overflow: auto; }
.error { margin: 12px; padding: 10px; border: 1px solid #b34840; background: #fff4f2; }
textarea { width: 100%; min-height: 96px; resize: vertical; }
button { border: 0; border-radius: 6px; padding: 8px 10px; background: #176b5d; color: white; cursor: pointer; }
@media (max-width: 980px) {
  .workbench-grid { grid-template-columns: 1fr; }
  .primary, .field-panel, .draft-panel, .timeline-panel, .history-panel, .evidence-panel {
    grid-column: 1;
    grid-row: auto;
  }
}
```

- [ ] **Step 6: Install and build frontend**

Run:

```bash
pnpm install
pnpm test
pnpm build
```

Expected: TypeScript and Vite build pass.

- [ ] **Step 7: Commit**

```bash
git add web
git commit -m "feat: add react pwps workbench"
```

---

### Task 5: Serve React Workbench From Python API

**Files:**
- Modify: `src/pwps_agent/web/runtime_api.py`
- Modify: `src/pwps_agent/cli.py`
- Modify: `tests/test_web_runtime_api.py`

- [ ] **Step 1: Write server behavior tests**

Append to `tests/test_web_runtime_api.py`:

```python
from pwps_agent.web.runtime_api import static_asset_path


def test_static_asset_path_serves_react_index() -> None:
    path = static_asset_path("/")

    assert path.name == "index.html"
```

- [ ] **Step 2: Implement static asset resolver and server entrypoint**

Modify `src/pwps_agent/web/runtime_api.py`:

```python
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def static_asset_path(request_path: str) -> Path:
    root = Path(__file__).resolve().parents[3] / "web"
    if request_path in {"/", "/index.html"}:
        return root / "index.html"
    cleaned = request_path.lstrip("/")
    return root / cleaned


def serve_workbench(base_output_dir: Path, host: str = "127.0.0.1", port: int = 8765) -> None:
    handler = _make_handler(base_output_dir)
    server = ThreadingHTTPServer((host, port), handler)
    print(f"pWPS workbench: http://{host}:{port}")  # noqa: T201
    server.serve_forever()


def _make_handler(base_output_dir: Path):
    class RuntimeApiHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path.startswith("/api/runs/"):
                run_id = self.path.split("/")[3]
                state = load_run_state(base_output_dir, run_id)
                self._send_json(build_run_snapshot(state, base_output_dir / run_id))
                return
            path = static_asset_path(self.path)
            if path.exists() and path.is_file():
                self._send_bytes(path.read_bytes(), _content_type(path))
                return
            self.send_error(404)

        def do_POST(self) -> None:  # noqa: N802
            if self.path.startswith("/api/runs/") and self.path.endswith("/respond"):
                run_id = self.path.split("/")[3]
                self._send_json(apply_run_response(base_output_dir, run_id, self._read_json()))
                return
            self.send_error(404)

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("content-length", "0"))
            return json.loads(self.rfile.read(length).decode("utf-8") or "{}")

        def _send_json(self, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self._send_bytes(body, "application/json; charset=utf-8")

        def _send_bytes(self, body: bytes, content_type: str) -> None:
            self.send_response(200)
            self.send_header("content-type", content_type)
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:
            return

    return RuntimeApiHandler


def _content_type(path: Path) -> str:
    if path.suffix == ".html":
        return "text/html; charset=utf-8"
    if path.suffix == ".js":
        return "text/javascript; charset=utf-8"
    if path.suffix == ".css":
        return "text/css; charset=utf-8"
    return "application/octet-stream"
```

- [ ] **Step 3: Wire CLI command**

Modify `src/pwps_agent/cli.py`:

```python
from pwps_agent.web.runtime_api import serve_workbench
```

In parser:

```python
web_workbench = subparsers.add_parser("web-workbench")
web_workbench.add_argument("--output-dir", type=Path, default=None)
web_workbench.add_argument("--host", default="127.0.0.1")
web_workbench.add_argument("--port", type=int, default=8765)
```

In `main()`:

```python
if args.command == "web-workbench":
    settings = load_settings()
    if args.output_dir is not None:
        settings.paths.output_dir = args.output_dir
    try:
        serve_workbench(settings.paths.output_dir, host=args.host, port=args.port)
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        print(f"pwps-agent: {exc}", file=sys.stderr)
        return 1
```

- [ ] **Step 4: Run server/API tests**

Run:

```bash
uv run pytest tests/test_web_runtime_api.py tests/test_cli.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/pwps_agent/web/runtime_api.py src/pwps_agent/cli.py tests/test_web_runtime_api.py tests/test_cli.py
git commit -m "feat: serve react workbench from runtime api"
```

---

### Task 6: Retire Embedded Guided Web UI

**Files:**
- Modify: `src/pwps_agent/web/guided_confirmation.py`
- Modify: `tests/test_guided_confirmation_web.py`
- Modify: `docs/architecture.md`
- Modify: `AGENTS.md`
- Modify: `docs/superpowers/plans/2026-05-25-llm-led-dual-mode-hardening.md`

- [ ] **Step 1: Replace embedded HTML tests**

Modify `tests/test_guided_confirmation_web.py`:

```python
from pwps_agent.web.guided_confirmation import web_state_payload


def test_legacy_guided_web_payload_keeps_confirmation_view() -> None:
    state = create_initial_state("Q355B 12mm plate GMAW", "guided_confirmation")
    payload = web_state_payload(state)

    assert payload["mode"] == "guided_confirmation"
    assert "confirmation_view" in payload
```

Remove tests that assert `render_guided_confirmation_html()` contains old page
text.

- [ ] **Step 2: Remove embedded HTML renderer**

Modify `src/pwps_agent/web/guided_confirmation.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

from pwps_agent.core.modes import build_confirmation_view
from pwps_agent.core.state import PWPSState
from pwps_agent.web.runtime_api import build_run_snapshot, serve_workbench


def web_state_payload(state: PWPSState) -> dict[str, Any]:
    return {
        **build_run_snapshot(state, Path(".") / state.run_id),
        "confirmation_view": build_confirmation_view(state),
    }


def serve_guided_confirmation(
    state_path: Path,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> None:
    base_output_dir = state_path.parent.parent if state_path.name == "pwps.json" else state_path.parent
    serve_workbench(base_output_dir, host=host, port=port)
```

Keep `load_state()` and `save_state()` if CLI resume commands still import them.

- [ ] **Step 3: Update docs**

In `docs/architecture.md`, add a short section under Interaction Subflows:

```markdown
CLI and Web are interaction adapters, not additional runtime modes. Both consume
`PWPSState.pending_interaction` and resume through the shared interaction
normalizer plus `resume_interaction()`.
```

In `AGENTS.md`, update Current Implementation Progress with:

```markdown
- CLI terminal and React Web workbench are treated as adapters over the same runtime interaction protocol ✅
- Legacy embedded guided-confirmation HTML has been replaced by a mode-neutral runtime Web API and React workbench ✅
```

- [ ] **Step 4: Run Web and docs-related tests**

Run:

```bash
uv run pytest tests/test_guided_confirmation_web.py tests/test_web_runtime_api.py tests/test_cli.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/pwps_agent/web/guided_confirmation.py tests/test_guided_confirmation_web.py docs/architecture.md AGENTS.md docs/superpowers/plans/2026-05-25-llm-led-dual-mode-hardening.md
git commit -m "refactor: retire embedded guided web ui"
```

---

### Task 7: Full Verification And Smoke

**Files:**
- Modify: `docs/superpowers/plans/2026-05-26-interaction-adapters-and-web-workbench.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: Run Python verification**

Run:

```bash
uv run pytest -q
uv run python -m compileall -q src tests
git diff --check
```

Expected:

```text
all tests pass
compileall exits 0
git diff --check exits 0
```

- [ ] **Step 2: Run frontend verification**

Run:

```bash
pnpm --dir web test
pnpm --dir web build
```

Expected: TypeScript and Vite build pass.

- [ ] **Step 3: Run CLI smoke with inline interaction**

Run in an interactive terminal:

```bash
uv run pwps-agent auto-draft "生成一个 pWPS 草稿" --output-dir /tmp/pwps-interaction-smoke --run-id cli_inline_smoke
```

Expected:

```text
CLI asks for missing startup context inside the same command.
After user input, the graph continues and prints /tmp/pwps-interaction-smoke/cli_inline_smoke.
```

- [ ] **Step 4: Run Web workbench smoke**

Run:

```bash
uv run pwps-agent web-workbench --output-dir /tmp/pwps-interaction-smoke --host 127.0.0.1 --port 8765
```

Open:

```text
http://127.0.0.1:8765/?run_id=cli_inline_smoke
```

Expected:

```text
Workbench loads run snapshot, field state, draft panel, timeline, and current interaction if present.
```

- [ ] **Step 5: Record verification**

Append verification results to this plan and update `AGENTS.md` Recent
Verification.

- [ ] **Step 6: Commit verification docs**

```bash
git add docs/superpowers/plans/2026-05-26-interaction-adapters-and-web-workbench.md AGENTS.md
git commit -m "docs: record interaction workbench verification"
```

---

## Self-Review

- Spec coverage: This plan covers protocol normalization, CLI adapter extraction,
  mode-neutral Web API, React workbench, legacy Web retirement, and verification.
- Placeholder scan: No task relies on `TBD`, `TODO`, or unspecified behavior.
- Type consistency: Python payloads use existing `InteractionRequest`,
  `PWPSState`, and `resume_interaction()` contracts; frontend types mirror the
  planned Web snapshot shape.
