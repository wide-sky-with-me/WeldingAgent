from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from pwps_agent.core.state import PWPSState


MINIMUM_AUTO_DRAFT_FIELDS = [
    "base_material",
    "thickness",
    "workpiece_type",
    "welding_process",
    "joint_type",
    "welding_position",
]


class InteractionOption(BaseModel):
    value: Any
    label: str | None = None
    suitability: str | None = None
    risk_note: str | None = None
    recommended: bool = False
    evidence_ids: list[str] = Field(default_factory=list)
    field_updates: dict[str, Any] = Field(default_factory=dict)


class InteractionQuestion(BaseModel):
    question_id: str
    field_ids: list[str]
    prompt: str
    input_kind: Literal["free_text", "single_choice", "multi_field_confirmation"]
    required: bool = True
    options: list[InteractionOption] = Field(default_factory=list)


class InteractionRequest(BaseModel):
    request_id: str
    interaction_mode: Literal["auto_draft", "guided_confirmation", "supplement_update"]
    purpose: Literal["initial_minimum_context", "guided_field_confirmation"]
    title: str
    summary: str
    questions: list[InteractionQuestion]
    allow_partial: bool = False
    transport_neutral: bool = True


def missing_minimum_auto_draft_fields(state: PWPSState) -> list[str]:
    missing: list[str] = []
    for field_id in MINIMUM_AUTO_DRAFT_FIELDS:
        field = state.fields.get(field_id)
        if field is None or field.value in (None, ""):
            missing.append(field_id)
            continue
        if field.status not in {"filled", "user_confirmed"}:
            missing.append(field_id)
    return missing


def should_interrupt_for_initial_info(state: PWPSState) -> bool:
    if state.interaction_mode != "auto_draft":
        return False
    if _retrieval_or_reasoning_started(state):
        return False
    return bool(missing_minimum_auto_draft_fields(state))


def build_initial_info_request(state: PWPSState) -> InteractionRequest:
    missing = missing_minimum_auto_draft_fields(state)
    labels = [_field_label(state, field_id) for field_id in missing]
    return InteractionRequest(
        request_id=f"{state.run_id}:initial_minimum_context:{len(state.interaction_requests) + 1}",
        interaction_mode=state.interaction_mode,
        purpose="initial_minimum_context",
        title="补充最小焊接场景信息",
        summary=(
            "auto_draft 可以低交互生成草稿，但当前输入还不足以启动检索和推理。"
        ),
        questions=[
            InteractionQuestion(
                question_id="minimum_core_fields",
                field_ids=missing,
                prompt="请补充这些最小起点字段：" + "、".join(labels),
                input_kind="free_text",
                required=True,
            )
        ],
        allow_partial=False,
    )


def build_guided_confirmation_request(
    state: PWPSState,
    confirmation_view: dict[str, Any],
) -> InteractionRequest:
    questions: list[InteractionQuestion] = []
    for group in confirmation_view.get("groups", []):
        for field in group.get("fields", []):
            field_id = str(field["field_id"])
            candidates = list(field.get("candidates") or [])
            options = [
                InteractionOption(
                    value=candidate.get("value"),
                    label=str(candidate.get("value")),
                    suitability=candidate.get("suitability") or candidate.get("note"),
                    risk_note=candidate.get("risk_note"),
                    recommended=bool(candidate.get("recommended", index == 0)),
                    evidence_ids=list(candidate.get("evidence_ids") or []),
                    field_updates={field_id: candidate.get("value")},
                )
                for index, candidate in enumerate(candidates)
                if candidate.get("value") not in (None, "")
            ]
            questions.append(
                InteractionQuestion(
                    question_id=f"confirm_{field_id}",
                    field_ids=[field_id],
                    prompt=str(
                        field.get("note")
                        or field.get("confirmation", {}).get("question")
                        or f"Confirm {field.get('label', field_id)}."
                    ),
                    input_kind="single_choice" if options else "free_text",
                    required=True,
                    options=options,
                )
            )
    return InteractionRequest(
        request_id=f"{state.run_id}:guided_field_confirmation:{len(state.interaction_requests) + 1}",
        interaction_mode=state.interaction_mode,
        purpose="guided_field_confirmation",
        title="确认关键焊接选择",
        summary="agent 已整理候选和推荐理由，关键字段需要用户确认后才能提升。",
        questions=questions,
        allow_partial=True,
    )


def attach_interaction_request(
    state: PWPSState,
    request: InteractionRequest,
) -> None:
    request_dict = request.model_dump()
    state.pending_interaction = request_dict
    state.interaction_requests.append(request_dict)


def _retrieval_or_reasoning_started(state: PWPSState) -> bool:
    started_nodes = {
        "knowledge_planning",
        "local_doc_search",
        "web_search",
        "field_reasoning",
        "draft_verifier",
        "section_generation",
        "risk_report",
        "compose_draft",
    }
    return any(entry.get("node") in started_nodes for entry in state.trace)


def _field_label(state: PWPSState, field_id: str) -> str:
    field = state.fields.get(field_id)
    return field.label if field is not None else field_id
