# Guided Confirmation And Web UI Implementation Plan

> **Status:** Completed for the first guided-confirmation interaction slice.

**Goal:** Add a guided-confirmation flow that can group fields requiring confirmation, show candidate values with evidence and risks, record explicit user decisions, support confirmation rollback/edit history, and expose both CLI and lightweight Web UI entry points.

**Architecture:** Keep the core behavior in pure state services under `core/modes.py`. The CLI and Web UI call those services and persist updated `PWPSState` JSON. The Web UI uses Python stdlib HTTP serving plus a small browser page, avoiding a frontend build pipeline in this stage.

## Implemented Scope

- [x] Build grouped confirmation views by A/B/C/D/E section.
- [x] Include clarification questions, candidate values, evidence snippets, and field-linked risks in the confirmation view.
- [x] Preserve confirmation history with user input, user rationale, shown rationale, shown evidence IDs, previous field snapshots, and edit/rollback linkage.
- [x] Support batch confirmation, single-field confirmation, confirmation edit, and rollback through state service functions.
- [x] Add `pwps-agent guided-confirm` for state-file confirmation/edit/rollback.
- [x] Add `pwps-agent guided-confirm-view` for inspecting grouped confirmation JSON from a real state file.
- [x] Add `pwps-agent guided-confirm-resume` for applying confirmation payloads and continuing through graph compose/finish.
- [x] Add `pwps-agent guided-confirm-web` for local browser-based guided-confirmation review.
- [x] Add JSON API helpers for Web state payloads and confirmation mutation payloads.
- [x] Add a minimal LangGraph `ASK_USER` route and `ask_user` node that pauses with a grouped confirmation view.
- [x] Add Web `/api/resume` to confirm selected fields, resume graph composition, persist artifacts, and return output location.

## Verification

```text
uv run pytest tests/test_guided_confirmation.py tests/test_guided_confirmation_web.py tests/test_cli.py -q
11 passed

uv run pytest tests/test_graph_guided_confirmation.py -q
3 passed, 1 warning

uv run pytest tests/test_guided_confirmation_resume.py tests/test_guided_confirmation_web.py tests/test_cli.py tests/test_graph_guided_confirmation.py -q
14 passed, 1 warning

uv run pytest -q
64 passed, 1 warning

uv run python -m compileall -q src tests
passed

uv run pwps-agent guided-confirm /tmp/pwps-guided-state.json --set filler_material=ER50-6 --message "Confirm filler from smoke" --reason "Smoke test" --evidence-id ev_web_1
confirm_1

uv run pwps-agent guided-confirm-resume /tmp/pwps-guided-resume-state.json --set filler_material=ER50-6 --message "Confirm filler and resume" --reason "CLI resume smoke" --output-dir /tmp/pwps-guided-resume-out
/tmp/pwps-guided-resume-out/guided_resume_smoke

curl -s -D - http://127.0.0.1:8765/api/state
HTTP/1.0 200 OK

curl -s -X POST http://127.0.0.1:8765/api/resume ...
status: done, has_draft: true, output_dir: /tmp/pwps-guided-web-resume-out/web_resume_smoke
```

## Remaining Gaps

- The LangGraph runtime now has a minimal `ASK_USER` pause point and graph-backed resume through compose/finish. It still needs durable multi-turn checkpoint recovery around live user sessions.
- The Web UI is intentionally lightweight and state-file backed; it is not yet a production multi-user app.
