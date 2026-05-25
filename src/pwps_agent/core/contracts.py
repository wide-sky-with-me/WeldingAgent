from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentAction(BaseModel):
    action_type: Literal[
        "USE_DOMAIN_SKILL",
        "CALL_TOOL",
        "UPDATE_STATE",
        "ASK_USER",
        "COMPOSE_DRAFT",
        "GENERATE_REPORT",
        "FINISH",
    ]
    domain_skill_name: str | None = None
    tool_name: str | None = None
    tool_args: dict[str, Any] = Field(default_factory=dict)
    state_patch: dict[str, Any] = Field(default_factory=dict)
    rationale_summary: str
    expected_state_change: str | None = None
    stop_reason: str | None = None


class ToolResult(BaseModel):
    tool_name: str
    success: bool
    state_patch: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    summary: str


class Evidence(BaseModel):
    evidence_id: str
    query_id: str | None = None
    result_id: str | None = None
    source_type: Literal[
        "user_input",
        "user_confirmation",
        "local_doc",
        "web",
        "llm",
        "template",
        "future_db",
    ]
    source_ref: str | None = None
    content: str
    extracted_claims: list[str] = Field(default_factory=list)
    related_fields: list[str] = Field(default_factory=list)
    source_tier: Literal[
        "official_standard",
        "textbook",
        "webpage",
        "user",
        "llm",
        "unknown",
    ] = "unknown"
    reliability: Literal["high", "medium", "low", "unknown"] = "unknown"
    confidence: Literal["high", "medium", "low", "unknown"] = "unknown"
    note: str | None = None


class SearchResult(BaseModel):
    result_id: str
    query_id: str
    source_type: Literal["web", "local_doc"] = "web"
    provider: str
    title: str | None = None
    url: str | None = None
    snippet: str
    raw_content: str | None = None
    score: float | None = None


class ConfirmationRecord(BaseModel):
    confirmation_id: str
    field_ids: list[str]
    action: Literal["accepted", "modified", "skipped", "deferred", "edited", "rolled_back"]
    values: dict[str, Any] = Field(default_factory=dict)
    previous_values: dict[str, Any] = Field(default_factory=dict)
    user_message: str | None = None
    user_rationale: str | None = None
    rationale_shown: str | None = None
    evidence_ids_shown: list[str] = Field(default_factory=list)
    supersedes_confirmation_id: str | None = None
    rolled_back_confirmation_id: str | None = None
    created_at: str | None = None
