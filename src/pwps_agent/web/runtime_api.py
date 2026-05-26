from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
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
        "interaction_mode": state.interaction_mode,
        "status": state.status,
        "pending_interaction": state.pending_interaction,
        "interaction_requests": list(state.interaction_requests),
        "fields": {
            field_id: field.model_dump()
            for field_id, field in state.fields.items()
        },
        "field_report": state.field_report or render_field_report(state),
        "quality_report": state.quality_report,
        "confirmations": [record.model_dump() for record in state.confirmations],
        "trace": list(state.trace),
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
    response = normalize_interaction_response(
        state.pending_interaction or {},
        str(payload.get("message") or ""),
        explicit_fields=payload.get("fields"),
    )
    result = resume_interaction(state, response, settings=settings)
    save_run_state(base_output_dir, result.state)
    return build_run_snapshot(result.state, Path(result.output_dir))


def static_asset_path(request_path: str) -> Path:
    web_root = Path(__file__).resolve().parents[3] / "web"
    dist_root = web_root / "dist"
    root = dist_root if dist_root.exists() else web_root
    parsed_path = urlparse(request_path).path
    if parsed_path in {"", "/", "/index.html"}:
        return root / "index.html"
    return root / parsed_path.lstrip("/")


def serve_workbench(
    base_output_dir: Path,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> None:
    handler = _make_handler(base_output_dir)
    server = ThreadingHTTPServer((host, port), handler)
    print(f"pWPS workbench: http://{host}:{port}")  # noqa: T201
    server.serve_forever()


def _make_handler(base_output_dir: Path):
    class RuntimeApiHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
            path = urlparse(self.path).path
            if path.startswith("/api/runs/"):
                self._handle_api_get(path)
                return

            asset_path = static_asset_path(path)
            if asset_path.exists() and asset_path.is_file():
                self._send_bytes(asset_path.read_bytes(), _content_type(asset_path))
                return
            self.send_error(404)

        def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
            path = urlparse(self.path).path
            if path.startswith("/api/runs/") and path.endswith("/respond"):
                run_id = _run_id_from_path(path)
                self._send_json(apply_run_response(base_output_dir, run_id, self._read_json()))
                return
            self.send_error(404)

        def _handle_api_get(self, path: str) -> None:
            parts = [part for part in path.split("/") if part]
            if len(parts) == 3:
                run_id = parts[2]
                state = load_run_state(base_output_dir, run_id)
                self._send_json(build_run_snapshot(state, base_output_dir / run_id))
                return
            if len(parts) == 5 and parts[3] == "artifacts":
                self._send_artifact(parts[2], parts[4])
                return
            self.send_error(404)

        def _send_artifact(self, run_id: str, filename: str) -> None:
            if filename not in {"pwps.json", "pwps_draft.md"}:
                self.send_error(404)
                return
            artifact_path = base_output_dir / run_id / filename
            if not artifact_path.exists():
                self.send_error(404)
                return
            self._send_bytes(artifact_path.read_bytes(), _content_type(artifact_path))

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


def _run_id_from_path(path: str) -> str:
    parts = [part for part in path.split("/") if part]
    if len(parts) < 3:
        raise ValueError(f"Invalid run API path: {path}")
    return parts[2]


def _content_type(path: Path) -> str:
    if path.suffix == ".html":
        return "text/html; charset=utf-8"
    if path.suffix == ".js":
        return "text/javascript; charset=utf-8"
    if path.suffix == ".css":
        return "text/css; charset=utf-8"
    if path.suffix == ".json":
        return "application/json; charset=utf-8"
    if path.suffix == ".md":
        return "text/markdown; charset=utf-8"
    return "application/octet-stream"
