from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError

from pwps_agent.agent.prompt_loader import load_domain_skill
from pwps_agent.core.contracts import SearchResult
from pwps_agent.core.modes import build_confirmation_view
from pwps_agent.graph.checkpoints import save_checkpoint
from pwps_agent.graph.state import GraphState
from pwps_agent.render.markdown import render_field_report, render_pwps_draft
from pwps_agent.storage.persist import persist_run_artifacts
from pwps_agent.tools.evidence import search_results_to_evidence
from pwps_agent.tools.field_reasoning import apply_field_candidates, infer_candidates_from_evidence
from pwps_agent.workflows.auto_draft import _merge_state_patch


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

    if action.tool_name == "web_search":
        search_results = _run_search_queries(state, context, deps.search_provider)
        if not search_results and state.knowledge_queries:
            payload = _tool_payload(state, "web_search", False, context.max_tool_retries)
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
            state = _merge_state_patch(state, result.state_patch)
            summary = result.summary
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
    draft = render_pwps_draft(state)
    report = render_field_report(state)
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
    _finalize_runtime_node(state, context, "finish")
    return {"pwps_state": state}


def _append_trace(state, node: str, event_type: str, summary: str, payload: dict) -> None:
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
    if not state.knowledge_queries:
        return []
    search_results: list[SearchResult] = []
    executor = ThreadPoolExecutor(max_workers=max(1, context.max_parallel_queries))
    future_by_query = {}
    try:
        for query in state.knowledge_queries:
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
