from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from pwps_agent.core.modes import (
    build_confirmation_view,
)
from pwps_agent.core.state import PWPSState
from pwps_agent.config import Settings
from pwps_agent.workflows.guided_confirmation import (
    apply_guided_confirmation_payload,
    resume_guided_confirmation,
)


def web_state_payload(state: PWPSState) -> dict[str, Any]:
    return {
        "run_id": state.run_id,
        "status": state.status,
        "interaction_mode": state.interaction_mode,
        "confirmation_view": build_confirmation_view(state),
        "confirmations": [record.model_dump() for record in state.confirmations],
        "has_draft": bool(state.draft_markdown),
        "field_report": state.field_report,
    }


def apply_confirmation_payload(state: PWPSState, payload: dict[str, Any]) -> PWPSState:
    return apply_guided_confirmation_payload(state, payload)


def apply_resume_payload(state: PWPSState, payload: dict[str, Any]) -> dict[str, Any]:
    settings = Settings()
    if payload.get("output_dir"):
        settings.paths.output_dir = Path(str(payload["output_dir"]))
    result = resume_guided_confirmation(state, payload, settings=settings)
    return {"state": result.state, "output_dir": result.output_dir}


def load_state(path: Path) -> PWPSState:
    return PWPSState.model_validate_json(path.read_text(encoding="utf-8"))


def save_state(path: Path, state: PWPSState) -> None:
    path.write_text(state.model_dump_json(indent=2), encoding="utf-8")


def serve_guided_confirmation(
    state_path: Path,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> None:
    handler = _make_handler(state_path)
    server = ThreadingHTTPServer((host, port), handler)
    print(f"guided_confirmation web UI: http://{host}:{port}")  # noqa: T201
    server.serve_forever()


def render_guided_confirmation_html() -> str:
    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>pWPS guided_confirmation</title>
  <style>
    :root {
      color-scheme: light;
      --ink: #17211b;
      --muted: #65736b;
      --line: #c9d4ca;
      --paper: #f5f2ea;
      --panel: #fffdf7;
      --accent: #0d7667;
      --warn: #9a5b12;
      --risk: #a13131;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: linear-gradient(90deg, rgba(13,118,103,.08), transparent 34%), var(--paper);
      color: var(--ink);
      font: 15px/1.45 "IBM Plex Sans", "Noto Sans", sans-serif;
    }
    header {
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 24px;
      padding: 28px 32px 16px;
      border-bottom: 1px solid var(--line);
    }
    h1 { margin: 0; font-size: 28px; letter-spacing: 0; }
    main { display: grid; grid-template-columns: minmax(0, 1fr) 360px; gap: 18px; padding: 18px 32px 32px; }
    section, aside { min-width: 0; }
    .group {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      margin-bottom: 14px;
      overflow: hidden;
    }
    .group h2 { margin: 0; padding: 12px 14px; font-size: 16px; border-bottom: 1px solid var(--line); }
    .field { padding: 14px; border-top: 1px solid #e6ded0; }
    .field:first-of-type { border-top: 0; }
    .meta { color: var(--muted); font-size: 12px; }
    .candidate, .evidence, .risk, .question, .history {
      margin-top: 8px;
      padding: 8px 10px;
      border-radius: 6px;
      background: #f7faf6;
      border: 1px solid #dbe4dc;
    }
    .risk { border-color: #e3b1a8; color: var(--risk); background: #fff7f5; }
    input, textarea {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px 9px;
      background: #fff;
      color: var(--ink);
      font: inherit;
    }
    button {
      border: 0;
      border-radius: 6px;
      padding: 8px 11px;
      background: var(--accent);
      color: white;
      font: inherit;
      cursor: pointer;
    }
    button.secondary { background: #44524a; }
    button.warning { background: var(--warn); }
    .actions { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 8px; }
    aside {
      background: #ede7da;
      border-left: 1px solid var(--line);
      padding: 14px;
      border-radius: 8px;
      align-self: start;
    }
    @media (max-width: 900px) {
      main { grid-template-columns: 1fr; padding: 14px; }
      header { padding: 20px 14px 12px; display: block; }
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>guided_confirmation</h1>
      <div class="meta" id="runMeta"></div>
    </div>
    <button class="secondary" onclick="refresh()">刷新</button>
  </header>
  <main>
    <section>
      <div id="questions"></div>
      <div class="group">
        <h2>批量操作</h2>
        <div class="field">
          <input id="outputDir" placeholder="输出目录，可选">
          <textarea id="batchReason" placeholder="批量确认理由/备注"></textarea>
          <div class="actions">
            <button onclick="confirmSelected()">确认选中字段</button>
            <button class="secondary" onclick="resumeSelected()">生成草案</button>
          </div>
        </div>
      </div>
      <div id="groups"></div>
    </section>
    <aside>
      <h2>确认记录</h2>
      <div id="history"></div>
    </aside>
  </main>
  <script>
    let state = null;
    async function refresh() {
      const response = await fetch('/api/state');
      state = await response.json();
      render();
    }
    function render() {
      document.getElementById('runMeta').textContent = `${state.run_id} · ${state.status}`;
      renderQuestions(state.confirmation_view.clarification_questions || []);
      renderGroups(state.confirmation_view.groups || []);
      renderHistory(state.confirmations || []);
    }
    function renderQuestions(questions) {
      const root = document.getElementById('questions');
      root.innerHTML = questions.map(q => `<div class="question"><b>clarification_questions</b><br>${escapeHtml(q.question || JSON.stringify(q))}</div>`).join('');
    }
    function renderGroups(groups) {
      const root = document.getElementById('groups');
      root.innerHTML = groups.map(group => `
        <div class="group">
          <h2>${group.section}. ${escapeHtml(group.title)}</h2>
          ${group.fields.map(renderField).join('')}
        </div>`).join('');
    }
    function renderField(field) {
      const inputId = `value-${field.field_id}`;
      return `<div class="field">
        <label><input type="checkbox" class="field-select" value="${field.field_id}"> <b>${escapeHtml(field.label)}</b> <span class="meta">${field.field_id} · ${field.status}</span></label>
        <input id="${inputId}" value="${escapeAttr(firstCandidateValue(field))}" placeholder="输入确认或修改后的值">
        ${(field.candidates || []).map(c => `<div class="candidate"><b>候选</b>: ${escapeHtml(String(c.value ?? ''))}<br><span class="meta">${escapeHtml(c.note || '')}</span></div>`).join('')}
        ${(field.evidence || []).map(e => `<div class="evidence"><b>证据</b> ${e.evidence_id}<br>${escapeHtml(e.content || '')}</div>`).join('')}
        ${(field.risks || []).map(r => `<div class="risk"><b>风险</b><br>${escapeHtml(r.message || JSON.stringify(r))}</div>`).join('')}
        <textarea id="reason-${field.field_id}" placeholder="理由/备注"></textarea>
        <div class="actions">
          <button onclick="confirmOne('${field.field_id}')">确认单字段</button>
        </div>
      </div>`;
    }
    function renderHistory(records) {
      const root = document.getElementById('history');
      root.innerHTML = records.map(r => `<div class="history">
        <b>${r.confirmation_id}</b> ${r.action}<br>
        <span class="meta">${(r.field_ids || []).join(', ')}</span>
        <div class="actions">
          <button class="warning" onclick="rollback('${r.confirmation_id}')">回滚</button>
          <button class="secondary" onclick="editFromCurrentInputs('${r.confirmation_id}', ${(JSON.stringify(r.field_ids || [])).replace(/"/g, '&quot;')})">编辑</button>
        </div>
      </div>`).join('');
    }
    async function confirmSelected() {
      const fields = {};
      document.querySelectorAll('.field-select:checked').forEach(box => {
        fields[box.value] = document.getElementById(`value-${box.value}`).value;
      });
      if (Object.keys(fields).length === 0) return alert('请选择至少一个字段');
      await post('/api/confirm', {
        fields,
        reason: document.getElementById('batchReason').value,
        message: 'Batch confirmed from web UI.',
        evidence_ids_shown: selectedEvidenceIds(Object.keys(fields)),
        action: 'accepted'
      });
    }
    async function resumeSelected() {
      const fields = {};
      document.querySelectorAll('.field-select:checked').forEach(box => {
        fields[box.value] = document.getElementById(`value-${box.value}`).value;
      });
      if (Object.keys(fields).length === 0) return alert('请选择至少一个字段');
      await post('/api/resume', {
        fields,
        reason: document.getElementById('batchReason').value,
        message: 'Batch confirmed and resumed from web UI.',
        evidence_ids_shown: selectedEvidenceIds(Object.keys(fields)),
        action: 'accepted',
        output_dir: document.getElementById('outputDir').value
      });
    }
    async function confirmOne(fieldId) {
      await post('/api/confirm', {
        fields: {[fieldId]: document.getElementById(`value-${fieldId}`).value},
        reason: document.getElementById(`reason-${fieldId}`).value,
        message: 'Confirmed from web UI.',
        evidence_ids_shown: evidenceIdsFor(fieldId),
        action: 'modified'
      });
    }
    async function rollback(confirmationId) {
      await post('/api/rollback', {operation: 'rollback', confirmation_id: confirmationId, message: 'Rollback from web UI.'});
    }
    async function editFromCurrentInputs(confirmationId, fieldIds) {
      const fields = {};
      fieldIds.forEach(fieldId => {
        const input = document.getElementById(`value-${fieldId}`);
        if (input) fields[fieldId] = input.value;
      });
      if (Object.keys(fields).length === 0) return alert('没有可编辑的当前字段输入');
      await post('/api/edit', {operation: 'edit', confirmation_id: confirmationId, fields, message: 'Edited from web UI.'});
    }
    async function post(url, payload) {
      const response = await fetch(url, {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify(payload)});
      if (!response.ok) alert(await response.text());
      await refresh();
    }
    function firstCandidateValue(field) {
      if (field.current_value !== null && field.current_value !== undefined) return field.current_value;
      const candidate = (field.candidates || [])[0];
      return candidate ? candidate.value : '';
    }
    function evidenceIdsFor(fieldId) {
      for (const group of state.confirmation_view.groups || []) {
        for (const field of group.fields || []) {
          if (field.field_id === fieldId) return (field.evidence || []).map(e => e.evidence_id);
        }
      }
      return [];
    }
    function selectedEvidenceIds(fieldIds) {
      const ids = new Set();
      fieldIds.forEach(fieldId => evidenceIdsFor(fieldId).forEach(id => ids.add(id)));
      return Array.from(ids);
    }
    function escapeHtml(value) {
      return String(value).replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
    }
    function escapeAttr(value) { return escapeHtml(value).replace(/"/g, '&quot;'); }
    refresh();
  </script>
</body>
</html>"""


def _make_handler(state_path: Path):
    class GuidedConfirmationHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
            if self.path == "/" or self.path == "/index.html":
                self._send_text(render_guided_confirmation_html(), "text/html; charset=utf-8")
                return
            if self.path == "/api/state":
                self._send_json(web_state_payload(load_state(state_path)))
                return
            self.send_error(404)

        def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
            try:
                payload = self._read_json()
                state = load_state(state_path)
                if self.path == "/api/rollback":
                    payload["operation"] = "rollback"
                elif self.path == "/api/edit":
                    payload["operation"] = "edit"
                elif self.path == "/api/resume":
                    result = apply_resume_payload(state, payload)
                    save_state(state_path, result["state"])
                    self._send_json(
                        {
                            **web_state_payload(result["state"]),
                            "output_dir": result["output_dir"],
                        }
                    )
                    return
                elif self.path != "/api/confirm":
                    self.send_error(404)
                    return
                updated = apply_confirmation_payload(state, payload)
                save_state(state_path, updated)
                self._send_json(web_state_payload(updated))
            except Exception as exc:  # noqa: BLE001 - web API returns readable local errors
                self.send_response(400)
                self.send_header("content-type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(str(exc).encode("utf-8"))

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("content-length", "0"))
            return json.loads(self.rfile.read(length).decode("utf-8") or "{}")

        def _send_json(self, payload: dict[str, Any]) -> None:
            self._send_text(json.dumps(payload, ensure_ascii=False), "application/json; charset=utf-8")

        def _send_text(self, text: str, content_type: str) -> None:
            body = text.encode("utf-8")
            self.send_response(200)
            self.send_header("content-type", content_type)
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:
            return

    return GuidedConfirmationHandler
