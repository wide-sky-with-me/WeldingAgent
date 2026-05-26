# Prompt Registry

Production LLM prompts live in this directory. Runtime code may assemble
structured state payloads, but role, task-boundary, mode, and safety wording
should be kept here or in `src/pwps_agent/domain_skills/*.md`.

## Files

- `requirement_understanding.md`: extract reliable core pWPS fields from raw
  user requirements.
- `knowledge_planning.md`: plan local/web/model evidence queries from current
  state.
- `field_reasoning.md`: convert evidence and field context into traceable
  candidate values.
- `section_generation.md`: generate structured A/B/C/D/E draft sections.
- `risk_report.md`: generate field/source/risk report guidance.
- `supervisor.md`: base LLM Supervisor role, action-selection boundary, and
  stage-one safety rules.
- `supervisor_mode_auto_draft.md`: `auto_draft` mode boundary, including the
  initial minimum-context interaction gate.
- `supervisor_mode_guided_confirmation.md`: `guided_confirmation` mode boundary
  and recommendation/confirmation expectations.
- `supervisor_mode_supplement_update.md`: supplemental update mode boundary.

## Rules

- Keep output schemas in Pydantic models and `Field(description=...)` text.
- Keep prompt files focused on role, task boundary, safety constraints, and mode
  semantics.
- Do not duplicate large JSON-shape instructions in prompts when the Pydantic
  schema is the contract.
- Add or update this registry entry whenever a production prompt is added.
