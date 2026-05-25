from __future__ import annotations

from collections import Counter

from pwps_agent.core.contracts import Evidence, ToolResult
from pwps_agent.core.fields import FieldState
from pwps_agent.core.quality import (
    DraftQualityReport,
    EvidenceQualityReport,
    FieldCoverageReport,
)
from pwps_agent.core.state import PWPSState
from pwps_agent.tools.evidence import is_low_quality_source_ref


CRITICAL_DRAFT_FIELDS = (
    "applicable_standard",
    "base_material",
    "thickness",
    "workpiece_type",
    "welding_process",
    "joint_type",
    "welding_position",
    "filler_material",
    "shielding_gas",
    "polarity",
    "current_range",
    "voltage_range",
    "preheat_temperature",
    "interpass_temperature",
)

BLOCKED_INFERRED_FIELDS = {
    "pwps_no",
    "revision_no",
    "date",
    "company",
    "project_name",
    "client",
    "contract_no",
}

COVERED_STATUSES = {
    "filled",
    "candidate",
    "suggested",
    "user_confirmed",
    "need_confirmation",
}

COUNTED_STATUSES = (
    "filled",
    "candidate",
    "suggested",
    "missing",
    "need_confirmation",
    "conflict",
    "user_confirmed",
)

GUIDED_HUMAN_REVIEW_STATUSES = {
    "candidate",
    "suggested",
    "need_confirmation",
    "conflict",
}

USER_SOURCE_TYPES = {"user_input", "user_confirmation"}


def verify_draft_quality(state: PWPSState) -> ToolResult:
    evidence_by_id = {item.evidence_id: item for item in state.evidence}

    field_counts = _field_counts(state)
    critical_missing_fields = _critical_missing_fields(state)
    weak_evidence_fields = _weak_evidence_fields(state, evidence_by_id)
    low_quality_sources = _low_quality_sources(state)
    blocked_inference_violations = _blocked_inference_violations(state, evidence_by_id)
    target_field_coverage = _target_field_coverage(state)
    evidence_quality = _evidence_quality(state, low_quality_sources)

    attempts_exhausted = state.refinement_attempts >= state.max_refinement_attempts
    if blocked_inference_violations or (
        critical_missing_fields and attempts_exhausted
    ):
        recommended_action = "synthesize_with_limitations"
    elif critical_missing_fields:
        recommended_action = "refine_search"
    else:
        recommended_action = "synthesize"

    human_review_fields = _human_review_fields(
        state=state,
        critical_missing_fields=critical_missing_fields,
        weak_evidence_fields=weak_evidence_fields,
        blocked_inference_violations=blocked_inference_violations,
    )
    mode_guidance = _mode_guidance(
        state.interaction_mode,
        recommended_action,
        human_review_fields,
    )
    quality_level = _quality_level(
        critical_missing_fields=critical_missing_fields,
        weak_evidence_fields=weak_evidence_fields,
        low_quality_sources=low_quality_sources,
        blocked_inference_violations=blocked_inference_violations,
        attempts_exhausted=attempts_exhausted,
    )

    report = DraftQualityReport(
        quality_level=quality_level,
        recommended_action=recommended_action,
        field_counts=field_counts,
        critical_missing_fields=critical_missing_fields,
        weak_evidence_fields=weak_evidence_fields,
        low_quality_sources=low_quality_sources,
        blocked_inference_violations=blocked_inference_violations,
        refinement_focus_fields=list(critical_missing_fields),
        human_review_fields=human_review_fields,
        mode_guidance=mode_guidance,
        target_field_coverage=target_field_coverage,
        evidence_quality=evidence_quality,
        notes=_notes(
            critical_missing_fields=critical_missing_fields,
            weak_evidence_fields=weak_evidence_fields,
            blocked_inference_violations=blocked_inference_violations,
            attempts_exhausted=attempts_exhausted,
        ),
    )

    return ToolResult(
        tool_name="draft_verifier",
        success=True,
        state_patch={"quality_report": report.model_dump()},
        summary=f"Verified draft quality: {report.recommended_action}.",
    )


def _field_counts(state: PWPSState) -> dict[str, int]:
    counts = Counter(field.status for field in state.fields.values())
    for status in COUNTED_STATUSES:
        counts.setdefault(status, 0)
    return dict(sorted(counts.items()))


def _human_review_fields(
    *,
    state: PWPSState,
    critical_missing_fields: list[str],
    weak_evidence_fields: list[str],
    blocked_inference_violations: list[str],
) -> list[str]:
    review_fields = [
        *critical_missing_fields,
        *weak_evidence_fields,
        *blocked_inference_violations,
    ]
    if state.interaction_mode == "guided_confirmation":
        review_fields.extend(
            field.field_id
            for field in state.fields.values()
            if field.status in GUIDED_HUMAN_REVIEW_STATUSES
        )
    return _unique_ordered(review_fields)


def _critical_missing_fields(state: PWPSState) -> list[str]:
    missing = []
    for field_id in _critical_draft_fields_for_state(state):
        field = state.fields.get(field_id)
        if field is None:
            continue
        if field.status not in COVERED_STATUSES:
            missing.append(field_id)
    return missing


def _critical_draft_fields_for_state(state: PWPSState) -> tuple[str, ...]:
    workpiece_type = state.fields.get("workpiece_type")
    if workpiece_type and _indicates_pipe_or_tube(workpiece_type.value):
        return (*CRITICAL_DRAFT_FIELDS, "diameter")
    return CRITICAL_DRAFT_FIELDS


def _indicates_pipe_or_tube(value: object) -> bool:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return False
    return any(marker in normalized for marker in ("pipe", "tube", "管"))


def _weak_evidence_fields(
    state: PWPSState,
    evidence_by_id: dict[str, Evidence],
) -> list[str]:
    weak_fields = []
    for field in state.fields.values():
        if field.status not in {"candidate", "suggested"}:
            continue
        if not field.evidence_ids:
            weak_fields.append(field.field_id)
            continue
        linked_evidence = [
            evidence_by_id.get(evidence_id) for evidence_id in field.evidence_ids
        ]
        if all(_is_weak_evidence(item) for item in linked_evidence):
            weak_fields.append(field.field_id)
    return weak_fields


def _is_weak_evidence(evidence: Evidence | None) -> bool:
    if evidence is None:
        return True
    return (
        evidence.source_tier in {"webpage", "unknown"}
        or evidence.reliability in {"low", "unknown"}
        or evidence.confidence in {"low", "unknown"}
    )


def _low_quality_sources(state: PWPSState) -> list[str]:
    refs: list[str] = []
    for evidence in state.evidence:
        if is_low_quality_source_ref(evidence.source_ref):
            refs.append(evidence.source_ref or "")
    for result in state.search_results:
        source_ref = result.get("url") or result.get("source_ref")
        if is_low_quality_source_ref(source_ref):
            refs.append(source_ref or "")
    return _unique_ordered([ref for ref in refs if ref])


def _blocked_inference_violations(
    state: PWPSState,
    evidence_by_id: dict[str, Evidence],
) -> list[str]:
    violations = []
    for field_id in sorted(BLOCKED_INFERRED_FIELDS):
        field = state.fields.get(field_id)
        if field is None or field.status in {"missing", "not_applicable"}:
            continue
        if field.value in (None, "") and not field.candidates:
            continue
        source_type = _field_source_type(field)
        if source_type in USER_SOURCE_TYPES:
            continue
        if source_type is None and _all_linked_evidence_from_user(field, evidence_by_id):
            continue
        violations.append(field_id)
    return violations


def _field_source_type(field: FieldState) -> str | None:
    if not field.source:
        return None
    source_type = field.source.get("type") or field.source.get("source_type")
    return str(source_type) if source_type else None


def _all_linked_evidence_from_user(
    field: FieldState,
    evidence_by_id: dict[str, Evidence],
) -> bool:
    if not field.evidence_ids:
        return False
    linked = [evidence_by_id.get(evidence_id) for evidence_id in field.evidence_ids]
    return all(item is not None and item.source_type in USER_SOURCE_TYPES for item in linked)


def _target_field_coverage(state: PWPSState) -> list[FieldCoverageReport]:
    coverage = []
    for query in state.knowledge_queries:
        target_fields = list(query.get("target_fields", []))
        covered_fields = [
            field_id
            for field_id in target_fields
            if state.fields.get(field_id)
            and state.fields[field_id].status in COVERED_STATUSES
        ]
        missing_target_fields = [
            field_id for field_id in target_fields if field_id not in covered_fields
        ]
        coverage.append(
            FieldCoverageReport(
                query_id=query.get("query_id"),
                target_fields=target_fields,
                covered_fields=covered_fields,
                missing_target_fields=missing_target_fields,
            )
        )
    return coverage


def _evidence_quality(
    state: PWPSState,
    low_quality_sources: list[str],
) -> EvidenceQualityReport:
    by_source_tier = Counter(item.source_tier for item in state.evidence)
    by_source_type = Counter(item.source_type for item in state.evidence)
    return EvidenceQualityReport(
        evidence_count=len(state.evidence),
        by_source_tier=dict(sorted(by_source_tier.items())),
        by_source_type=dict(sorted(by_source_type.items())),
        low_quality_sources=low_quality_sources,
    )


def _mode_guidance(
    interaction_mode: str,
    recommended_action: str,
    human_review_fields: list[str],
) -> str:
    if interaction_mode == "guided_confirmation":
        if human_review_fields:
            return "ask_user_for_confirmation"
        if recommended_action == "synthesize":
            return "guided_synthesize"
        return "ask_user_for_confirmation"
    if recommended_action == "refine_search":
        return "auto_refine"
    if recommended_action == "synthesize_with_limitations":
        return "auto_suggest_with_limitations"
    return "auto_synthesize"


def _quality_level(
    *,
    critical_missing_fields: list[str],
    weak_evidence_fields: list[str],
    low_quality_sources: list[str],
    blocked_inference_violations: list[str],
    attempts_exhausted: bool,
) -> str:
    if blocked_inference_violations or (critical_missing_fields and attempts_exhausted):
        return "low"
    if critical_missing_fields or weak_evidence_fields or low_quality_sources:
        return "partial"
    return "good"


def _notes(
    *,
    critical_missing_fields: list[str],
    weak_evidence_fields: list[str],
    blocked_inference_violations: list[str],
    attempts_exhausted: bool,
) -> list[str]:
    notes = []
    if critical_missing_fields:
        notes.append("Critical draft fields are still uncovered.")
    if attempts_exhausted and critical_missing_fields:
        notes.append("Refinement attempts are exhausted.")
    if weak_evidence_fields:
        notes.append("Some candidate or suggested fields have weak evidence.")
    if blocked_inference_violations:
        notes.append("Project metadata must come from user-provided sources.")
    return notes


def _unique_ordered(values: list[str]) -> list[str]:
    seen = set()
    ordered = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered
