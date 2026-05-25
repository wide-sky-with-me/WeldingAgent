from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError

from pwps_agent.agent.prompt_loader import load_domain_skill
from pwps_agent.core.contracts import SearchResult
from pwps_agent.core.modes import apply_supplement, build_confirmation_view
from pwps_agent.graph.checkpoints import save_checkpoint
from pwps_agent.graph.state import GraphState
from pwps_agent.render.markdown import render_field_report, render_pwps_draft
from pwps_agent.storage.persist import persist_run_artifacts
from pwps_agent.tools.evidence import search_results_to_evidence
from pwps_agent.tools.field_reasoning import apply_field_candidates, infer_candidates_from_evidence
from pwps_agent.tools.local_doc_search import search_local_documents
from pwps_agent.tools.draft_verifier import verify_draft_quality
from pwps_agent.tools.risk_report import generate_risk_report
from pwps_agent.tools.section_generation import generate_sections
from pwps_agent.workflows.auto_draft import _merge_state_patch

LOGGER = logging.getLogger(__name__)


def use_domain_skill_node(graph_state: GraphState) -> dict:
    state = graph_state["pwps_state"].model_copy(deep=True)
    context = graph_state["context"]
    action = state.pending_action
    if action is None or not action.domain_skill_name:
        state.status = "failed"
        _append_trace(state, "use_domain_skill", "error", "No pending domain skill action.", {})
        _finalize_runtime_node(state, context, "use_domain_skill")
        return {"pwps_state": state}

    skill = load_domain_skill(action.domain_skill_name)
    if skill.name not in state.active_domain_skills:
        state.active_domain_skills.append(skill.name)
    context_id = f"domain_skill:{skill.name}"
    state.domain_skill_history.append(
        {
            "skill_name": skill.name,
            "context_id": context_id,
            "rationale": action.rationale_summary,
        }
    )
    _append_trace(
        state,
        "use_domain_skill",
        "domain_skill_selected",
        action.rationale_summary,
        {
            "skill_name": skill.name,
            "context_id": context_id,
            "active_domain_skills": state.active_domain_skills,
        },
    )
    _finalize_runtime_node(state, context, "use_domain_skill")
    return {"pwps_state": state}


def update_state_node(graph_state: GraphState) -> dict:
    state = graph_state["pwps_state"].model_copy(deep=True)
    context = graph_state["context"]
    action = state.pending_action
    if action is None:
        state.status = "failed"
        _append_trace(state, "update_state", "error", "No pending state update action.", {})
        _finalize_runtime_node(state, context, "update_state")
        return {"pwps_state": state}

    if action.tool_args.get("operation") != "supplement_update":
        state.status = "failed"
        _append_trace(
            state,
            "update_state",
            "error",
            f"Unsupported state update operation: {action.tool_args.get('operation')}",
            {"tool_args": action.tool_args},
        )
        _finalize_runtime_node(state, context, "update_state")
        return {"pwps_state": state}

    field_values = dict(action.tool_args.get("fields", {}))
    supplement = str(action.tool_args.get("supplement") or "")
    if not supplement or not field_values:
        state.status = "failed"
        _append_trace(
            state,
            "update_state",
            "error",
            "supplement_update requires supplement text and fields.",
            {"tool_args": action.tool_args},
        )
        _finalize_runtime_node(state, context, "update_state")
        return {"pwps_state": state}

    state = apply_supplement(state, supplement=supplement, field_values=field_values)
    state.status = "running"
    _finalize_runtime_node(state, context, "supplement_update")
    return {"pwps_state": state}


def call_tool_node(graph_state: GraphState) -> dict:
    state = graph_state["pwps_state"].model_copy(deep=True)
    context = graph_state["context"]
    action = state.pending_action
    if action is None or action.tool_name is None:
        state.status = "failed"
        _append_trace(state, "call_tool", "error", "No pending tool action.", {})
        _finalize_runtime_node(state, context, "call_tool")
        return {"pwps_state": state}

    deps = context.dependencies
    if action.tool_name == "requirement_understanding":
        result = _execute_tool_action(
            state,
            context.max_tool_retries,
            "requirement_understanding",
            lambda: deps.requirement_tool(state, deps.llm_client),
        )
        if not result:
            _finalize_runtime_node(state, context, "requirement_understanding")
            return {"pwps_state": state}
        state.status = "running"
        state = _merge_state_patch(state, result.state_patch)
        _append_trace(
            state,
            "requirement_understanding",
            "tool_result",
            result.summary,
            _tool_payload(state, "requirement_understanding", result.success, context.max_tool_retries),
        )
        _finalize_runtime_node(state, context, "requirement_understanding")
        return {"pwps_state": state}

    if action.tool_name == "knowledge_planning":
        result = _execute_tool_action(
            state,
            context.max_tool_retries,
            "knowledge_planning",
            lambda: deps.knowledge_planning_tool(state, deps.llm_client),
        )
        if not result:
            _finalize_runtime_node(state, context, "knowledge_planning")
            return {"pwps_state": state}
        state.status = "running"
        state = _merge_state_patch(state, result.state_patch)
        _append_trace(
            state,
            "knowledge_planning",
            "tool_result",
            result.summary,
            _tool_payload(state, "knowledge_planning", result.success, context.max_tool_retries),
        )
        _finalize_runtime_node(state, context, "knowledge_planning")
        return {"pwps_state": state}

    if action.tool_name == "local_doc_search":
        if not context.settings.knowledge.local_doc_enabled:
            state.status = "running"
            _append_trace(
                state,
                "local_doc_search",
                "tool_skipped",
                "Local document search is disabled by knowledge source configuration.",
                {"sources": context.settings.knowledge.sources},
            )
            _finalize_runtime_node(state, context, "local_doc_search")
            return {"pwps_state": state}
        if deps.local_doc_provider is None:
            state.status = "failed"
            _append_trace(
                state,
                "local_doc_search",
                "tool_error",
                "No local document provider is configured.",
                _tool_payload(state, "local_doc_search", False, context.max_tool_retries),
            )
            _finalize_runtime_node(state, context, "local_doc_search")
            return {"pwps_state": state}
        result = search_local_documents(state, deps.local_doc_provider)
        state.status = "running"
        state = _merge_state_patch(state, result.state_patch)
        _append_trace(
            state,
            "local_doc_search",
            "tool_result",
            result.summary,
            _tool_payload(state, "local_doc_search", result.success, context.max_tool_retries),
        )
        _finalize_runtime_node(state, context, "local_doc_search")
        return {"pwps_state": state}

    if action.tool_name == "web_search":
        if not context.settings.knowledge.web_enabled:
            state.status = "running"
            _append_trace(
                state,
                "web_search",
                "tool_skipped",
                "Web search is disabled by knowledge source configuration.",
                {"sources": context.settings.knowledge.sources},
            )
            _finalize_runtime_node(state, context, "web_search")
            return {"pwps_state": state}
        search_results = _run_search_queries(state, context, deps.search_provider)
        web_queries = _web_queries(state.knowledge_queries)
        if not search_results and web_queries:
            payload = _tool_payload(state, "web_search", False, context.max_tool_retries)
            if not context.settings.knowledge.model_fallback_enabled:
                state.status = "failed"
                _append_trace(
                    state,
                    "web_search",
                    "tool_result",
                    "No web search results were retrieved.",
                    payload,
                )
                _finalize_runtime_node(state, context, "web_search")
                return {"pwps_state": state}
            state.status = "running"
            _append_trace(
                state,
                "web_search",
                "tool_result",
                "No web search results were retrieved; model fallback remains enabled.",
                {**payload, "model_fallback_enabled": True},
            )
            _finalize_runtime_node(state, context, "web_search")
            return {"pwps_state": state}
        state.status = "running"
        state.search_results = [result.model_dump() for result in search_results]
        evidence = search_results_to_evidence(search_results)
        state.evidence.extend(evidence)
        _append_trace(
            state,
            "web_search",
            "tool_result",
            f"Retrieved {len(search_results)} web results.",
            {"queries": state.knowledge_queries},
        )
        _finalize_runtime_node(state, context, "web_search")
        return {"pwps_state": state}

    if action.tool_name == "field_reasoning":
        use_model_fallback = (
            context.settings.knowledge.model_fallback_enabled
            and not _has_external_evidence(state)
        )
        result = _execute_tool_action(
            state,
            context.max_tool_retries,
            "field_reasoning",
            lambda: deps.field_reasoning_tool(state, state.evidence, deps.llm_client),
        )
        if not result:
            _finalize_runtime_node(state, context, "field_reasoning")
            return {"pwps_state": state}
        state.status = "running"
        if result.success and result.state_patch.get("fields"):
            result.state_patch["fields"] = _drop_status_word_field_values(
                result.state_patch["fields"]
            )
            if use_model_fallback:
                result.state_patch["fields"] = _mark_model_fallback_fields(
                    result.state_patch["fields"]
                )
            state = _merge_state_patch(state, result.state_patch)
            summary = (
                "Generated suggested fields from model fallback."
                if use_model_fallback
                else result.summary
            )
        else:
            candidates = infer_candidates_from_evidence(state.evidence)
            state = apply_field_candidates(state, candidates)
            summary = "Used deterministic evidence fallback."
        _append_trace(
            state,
            "field_reasoning",
            "tool_result",
            summary,
            _tool_payload(state, "field_reasoning", True, context.max_tool_retries),
        )
        _finalize_runtime_node(state, context, "field_reasoning")
        return {"pwps_state": state}

    state.status = "failed"
    _append_trace(
        state,
        action.tool_name,
        "error",
        f"Unsupported tool action: {action.tool_name}",
        {},
    )
    _finalize_runtime_node(state, context, action.tool_name)
    return {"pwps_state": state}


def compose_draft_node(graph_state: GraphState) -> dict:
    state = graph_state["pwps_state"].model_copy(deep=True)
    context = graph_state["context"]
    if not state.sections:
        sections_result = generate_sections(state)
        state = _merge_state_patch(state, sections_result.state_patch)
        _append_trace(
            state,
            "section_generation",
            "tool_result",
            sections_result.summary,
            {"success": sections_result.success},
        )
    if not state.field_report:
        report_result = generate_risk_report(state)
        state = _merge_state_patch(state, report_result.state_patch)
        _append_trace(
            state,
            "risk_report",
            "tool_result",
            report_result.summary,
            {"success": report_result.success},
        )
    draft = render_pwps_draft(state)
    report = state.field_report or render_field_report(state)
    state.draft_markdown = draft
    state.field_report = report
    run_dir = context.settings.paths.output_dir / state.run_id
    _append_trace(
        state,
        "compose_draft",
        "artifact",
        "Rendered and persisted pWPS draft artifacts.",
        {"output_dir": str(run_dir)},
    )
    persist_run_artifacts(state, draft, report, context.settings.paths.output_dir)
    _finalize_runtime_node(state, context, "compose_draft")
    return {"pwps_state": state}


def verify_draft_node(graph_state: GraphState) -> dict:
    state = graph_state["pwps_state"].model_copy(deep=True)
    context = graph_state["context"]
    result = verify_draft_quality(state)
    state = _merge_state_patch(state, result.state_patch)
    _append_trace(
        state,
        "draft_verifier",
        "tool_result",
        result.summary,
        {
            "success": result.success,
            "quality_report": result.state_patch.get("quality_report"),
        },
    )
    _finalize_runtime_node(state, context, "draft_verifier")
    return {"pwps_state": state}


def generate_report_node(graph_state: GraphState) -> dict:
    state = graph_state["pwps_state"].model_copy(deep=True)
    context = graph_state["context"]
    result = generate_risk_report(state)
    state = _merge_state_patch(state, result.state_patch)
    _append_trace(
        state,
        "risk_report",
        "tool_result",
        result.summary,
        {"success": result.success},
    )
    _finalize_runtime_node(state, context, "risk_report")
    return {"pwps_state": state}


def ask_user_node(graph_state: GraphState) -> dict:
    state = graph_state["pwps_state"].model_copy(deep=True)
    context = graph_state["context"]
    confirmation_view = build_confirmation_view(state)
    state.status = "need_user_input"
    _append_trace(
        state,
        "ask_user",
        "user_input_required",
        "Paused for guided field confirmation.",
        {"confirmation_view": confirmation_view},
    )
    _finalize_runtime_node(state, context, "ask_user")
    return {"pwps_state": state}


def finish_node(graph_state: GraphState) -> dict:
    state = graph_state["pwps_state"].model_copy(deep=True)
    context = graph_state["context"]
    if state.status not in {"failed", "interrupted", "need_user_input"}:
        state.status = "done"
    _append_trace(
        state,
        "finish",
        "state_update",
        f"Auto-draft graph finished with status {state.status}.",
        {"status": state.status},
    )
    if state.draft_markdown and state.field_report:
        persist_run_artifacts(
            state,
            state.draft_markdown,
            state.field_report,
            context.settings.paths.output_dir,
        )
    _finalize_runtime_node(state, context, "finish")
    return {"pwps_state": state}


def _append_trace(state, node: str, event_type: str, summary: str, payload: dict) -> None:
    LOGGER.info(
        "Graph event run_id=%s step=%s node=%s event=%s summary=%s",
        state.run_id,
        len(state.trace) + 1,
        node,
        event_type,
        summary,
    )
    state.trace.append(
        {
            "step": len(state.trace) + 1,
            "node": node,
            "event_type": event_type,
            "summary": summary,
            "payload": payload,
        }
    )


def _finalize_runtime_node(state, context, node_name: str) -> None:
    state.step_count += 1
    if (
        context.interrupt_after_steps is not None
        and state.status == "running"
        and state.step_count >= context.interrupt_after_steps
    ):
        state.status = "interrupted"
        _append_trace(
            state,
            node_name,
            "interrupt",
            f"Interrupted after runtime step {state.step_count}.",
            {"step_count": state.step_count},
        )
    if context.checkpoint_enabled:
        save_checkpoint(state, context.settings.paths.output_dir, node_name)


def _execute_tool_action(state, max_retries: int, node: str, call):
    try:
        result = call()
    except Exception as exc:  # noqa: BLE001 - graph runtime records provider/tool failures
        payload = _tool_payload(state, node, False, max_retries)
        payload["error"] = str(exc)
        state.status = "failed"
        _append_trace(state, node, "tool_error", str(exc), payload)
        return None
    if not result.success:
        payload = _tool_payload(state, node, False, max_retries)
        payload["errors"] = result.errors
        state.status = "failed"
        _append_trace(state, node, "tool_result", result.summary, payload)
        return None
    return result


def _run_search_queries(state, context, search_provider) -> list[SearchResult]:
    queries = _web_queries(state.knowledge_queries)
    if not queries:
        return []
    search_results: list[SearchResult] = []
    executor = ThreadPoolExecutor(max_workers=max(1, context.max_parallel_queries))
    future_by_query = {}
    try:
        for query in queries:
            query_text = str(query["query_text"])
            query_id = str(query["query_id"])
            future_by_query[
                executor.submit(search_provider.search, query_text, query_id)
            ] = query
        for future, query in future_by_query.items():
            query_id = str(query["query_id"])
            try:
                results = future.result(timeout=context.query_timeout_seconds)
            except TimeoutError:
                _append_trace(
                    state,
                    "web_search_query",
                    "tool_timeout",
                    f"Web search query timed out: {query_id}",
                    {"query_id": query_id, "timeout_seconds": context.query_timeout_seconds},
                )
                continue
            except Exception as exc:  # noqa: BLE001 - per-query provider failures are trace data
                _append_trace(
                    state,
                    "web_search_query",
                    "tool_error",
                    f"Web search query failed: {query_id}",
                    {"query_id": query_id, "error": str(exc)},
                )
                continue
            search_results.extend(results)
            _append_trace(
                state,
                "web_search_query",
                "tool_result",
                f"Web search query returned {len(results)} results.",
                {"query_id": query_id, "success": True},
            )
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
    return search_results


def _web_queries(knowledge_queries: list[dict]) -> list[dict]:
    return [
        query
        for query in knowledge_queries
        if "web" in (query.get("preferred_sources") or ["web"])
    ]


def _has_external_evidence(state) -> bool:
    return any(item.source_type in {"local_doc", "web"} for item in state.evidence)


def _mark_model_fallback_fields(fields: dict) -> dict:
    marked = {}
    for field_id, field_patch in fields.items():
        if field_id in {
            "pwps_no",
            "revision_no",
            "date",
            "company",
            "project_name",
            "client",
            "contract_no",
        }:
            continue
        patch = dict(field_patch)
        note = patch.get("note")
        fallback_note = "Suggested by model fallback because no external evidence was retrieved."
        patch["status"] = "suggested"
        patch["confidence"] = "low"
        evidence_ids = list(patch.get("evidence_ids") or [])
        patch["evidence_ids"] = evidence_ids
        patch["source"] = {"type": "model_fallback", "evidence_ids": evidence_ids}
        patch["confirmation"] = {"required": True, "confirmed": False}
        patch["note"] = f"{note} {fallback_note}" if note else fallback_note
        marked[field_id] = patch
    return marked


def _drop_status_word_field_values(fields: dict) -> dict:
    cleaned = {}
    for field_id, field_patch in fields.items():
        value = field_patch.get("value")
        if isinstance(value, str) and value.strip().lower() in {
            "candidate",
            "suggested",
            "need_confirmation",
            "missing",
            "unknown",
            "待确认",
        }:
            continue
        cleaned[field_id] = field_patch
    return cleaned


def _tool_payload(state, node: str, success: bool, max_retries: int) -> dict:
    attempt = _tool_attempt_count(state.trace, node) + 1
    retryable = not success and attempt <= max_retries + 1 and attempt <= max_retries
    return {
        "success": success,
        "attempt": attempt,
        "max_retries": max_retries,
        "retryable": retryable,
    }


def _tool_attempt_count(trace: list[dict], node: str) -> int:
    return sum(
        1
        for entry in trace
        if entry.get("node") == node
        and entry.get("event_type") in {"tool_result", "tool_error"}
    )
