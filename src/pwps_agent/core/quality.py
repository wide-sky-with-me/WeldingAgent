from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


QualityLevel = Literal["good", "partial", "low"]
RecommendedAction = Literal[
    "synthesize",
    "refine_search",
    "synthesize_with_limitations",
]


class FieldCoverageReport(BaseModel):
    query_id: str | None = None
    target_fields: list[str] = Field(default_factory=list)
    covered_fields: list[str] = Field(default_factory=list)
    missing_target_fields: list[str] = Field(default_factory=list)


class EvidenceQualityReport(BaseModel):
    evidence_count: int = 0
    by_source_tier: dict[str, int] = Field(default_factory=dict)
    by_source_type: dict[str, int] = Field(default_factory=dict)
    low_quality_sources: list[str] = Field(default_factory=list)


class DraftQualityReport(BaseModel):
    quality_level: QualityLevel
    recommended_action: RecommendedAction
    field_counts: dict[str, int] = Field(default_factory=dict)
    critical_missing_fields: list[str] = Field(default_factory=list)
    weak_evidence_fields: list[str] = Field(default_factory=list)
    low_quality_sources: list[str] = Field(default_factory=list)
    blocked_inference_violations: list[str] = Field(default_factory=list)
    refinement_focus_fields: list[str] = Field(default_factory=list)
    human_review_fields: list[str] = Field(default_factory=list)
    mode_guidance: str | None = None
    target_field_coverage: list[FieldCoverageReport] = Field(default_factory=list)
    evidence_quality: EvidenceQualityReport = Field(default_factory=EvidenceQualityReport)
    notes: list[str] = Field(default_factory=list)
