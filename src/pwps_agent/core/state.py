from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from pwps_agent.core.contracts import AgentAction, ConfirmationRecord, Evidence
from pwps_agent.core.fields import FieldState, initialize_fields


class PWPSState(BaseModel):
    run_id: str
    user_input: str
    task_goal: str = "generate_pwps_draft"
    interaction_mode: Literal["auto_draft", "guided_confirmation", "supplement_update"]
    messages: list[dict] = Field(default_factory=list)
    core_fields: dict[str, object] = Field(default_factory=dict)
    fields: dict[str, FieldState] = Field(default_factory=initialize_fields)
    confirmations: list[ConfirmationRecord] = Field(default_factory=list)
    actions: list[AgentAction] = Field(default_factory=list)
    pending_action: AgentAction | None = None
    active_domain_skills: list[str] = Field(default_factory=list)
    domain_skill_history: list[dict] = Field(default_factory=list)
    knowledge_queries: list[dict] = Field(default_factory=list)
    search_results: list[dict] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    sections: dict[str, object] = Field(default_factory=dict)
    draft_markdown: str = ""
    draft_html: str = ""
    field_report: dict[str, object] = Field(default_factory=dict)
    clarification_questions: list[dict] = Field(default_factory=list)
    risks: list[dict] = Field(default_factory=list)
    trace: list[dict] = Field(default_factory=list)
    status: Literal["running", "need_user_input", "done", "failed", "interrupted"] = "running"
    step_count: int = 0


def create_initial_state(
    user_input: str,
    interaction_mode: Literal["auto_draft", "guided_confirmation", "supplement_update"],
    run_id: str = "run_local",
) -> PWPSState:
    return PWPSState(
        run_id=run_id,
        user_input=user_input,
        interaction_mode=interaction_mode,
        evidence=[
            Evidence(
                evidence_id="ev_user_input_1",
                source_type="user_input",
                content=user_input,
                reliability="high",
            )
        ],
    )
