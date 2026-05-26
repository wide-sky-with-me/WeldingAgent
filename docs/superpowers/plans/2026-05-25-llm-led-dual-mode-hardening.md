# LLM-Led Dual Mode Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep the LLM Supervisor as the main actor while hardening the two product modes: low-interruption `auto_draft` and human-confirmed `guided_confirmation`.

**Architecture:** The LLM continues to plan, recommend, reason from evidence, and synthesize the draft. Runtime code supplies explicit state contracts, evidence gates, interaction gates, and eval metrics so model decisions remain traceable instead of silently becoming stronger than their source. The first cleanup for this plan already removed the old linear `run_auto_draft()` path and the deterministic ER50-6 evidence fallback, leaving the graph runtime as the canonical draft path.

**Tech Stack:** Python, Pydantic, LangGraph, LangChain structured output, pytest, existing `PWPSState`, `AgentAction`, Domain Skills, and `docs/superpowers/plans/` progress tracking.

---

## Product Contract

The project has two intended modes:

- `auto_draft`: the user provides a requirement and expects a draft. The agent should only interrupt at the beginning when minimum core information is missing. After that it drafts with uncertainty labels, missing-field reports, risk notes, and low-confidence suggestions.
- `guided_confirmation`: the agent organizes information, recommends options, explains applicability, and asks the user to confirm key choices such as welding process, joint type, position, filler, shielding gas, preheat/PWHT, and other qualification-sensitive fields.

LLM dependence is intentional. The work is not to demote the LLM, but to give the LLM-led system stronger state semantics, evidence governance, interaction boundaries, and eval feedback.

## Files

- Modify: `src/pwps_agent/core/fields.py`
- Modify: `src/pwps_agent/core/state_merge.py`
- Modify: `src/pwps_agent/core/modes.py`
- Modify: `src/pwps_agent/graph/supervisor.py`
- Modify: `src/pwps_agent/graph/nodes.py`
- Modify: `src/pwps_agent/tools/requirement_understanding.py`
- Modify: `src/pwps_agent/tools/field_reasoning.py`
- Modify: `src/pwps_agent/tools/draft_verifier.py`
- Modify: `src/pwps_agent/tools/risk_report.py`
- Modify: `src/pwps_agent/render/markdown.py`
- Modify: `src/pwps_agent/storage/persist.py`
- Modify: `src/pwps_agent/domain_skills/pwps_auto_draft.md`
- Modify: `src/pwps_agent/domain_skills/pwps_guided_confirmation.md`
- Create: `src/pwps_agent/core/interaction.py`
- Create: `src/pwps_agent/core/evidence_policy.py`
- Create: `src/pwps_agent/core/publishability.py`
- Create: `src/pwps_agent/core/eval_metrics.py`
- Create: `src/pwps_agent/tools/guided_options.py`
- Create: `tests/test_interaction_gates.py`
- Create: `tests/test_evidence_policy.py`
- Create: `tests/test_publishability.py`
- Create: `tests/test_guided_options.py`
- Create: `tests/test_eval_metrics.py`

## Task 1: Initial Information Gate For Auto Draft

**Files:**
- Create: `src/pwps_agent/core/interaction.py`
- Modify: `src/pwps_agent/graph/supervisor.py`
- Test: `tests/test_interaction_gates.py`

- [x] **Step 1: Write failing tests**

```python
from pwps_agent.core.interaction import missing_minimum_auto_draft_fields, should_interrupt_for_initial_info
from pwps_agent.core.state import create_initial_state


def test_auto_draft_interrupts_only_before_workflow_starts_when_core_fields_missing():
    state = create_initial_state("Need a pWPS draft", "auto_draft")
    assert missing_minimum_auto_draft_fields(state) == [
        "base_material",
        "thickness",
        "workpiece_type",
        "welding_process",
        "joint_type",
        "welding_position",
    ]
    assert should_interrupt_for_initial_info(state) is True


def test_auto_draft_does_not_interrupt_after_retrieval_started():
    state = create_initial_state("Need a pWPS draft", "auto_draft")
    state.trace.append({"node": "knowledge_planning", "event_type": "tool_result"})
    assert should_interrupt_for_initial_info(state) is False
```

- [x] **Step 2: Run failing tests**

Run: `uv run pytest tests/test_interaction_gates.py -q`

- [x] **Step 3: Implement gate**

Add `MINIMUM_AUTO_DRAFT_FIELDS` and two functions in `core/interaction.py`. Use `PWPSState.fields[field_id].value` and `status in {"filled", "user_confirmed"}` as the initial adequacy check. Treat any trace node other than `supervisor` as workflow-started.

- [x] **Step 4: Wire Supervisor**

In `graph/supervisor.py`, before normal safe-next progression, if `state.interaction_mode == "auto_draft"` and `should_interrupt_for_initial_info(state)` is true, return `ASK_USER` with a concise missing-field question. Keep the existing rule that later `ASK_USER` in `auto_draft` is overridden.

- [x] **Step 5: Verify**

Run: `uv run pytest tests/test_interaction_gates.py tests/test_graph_supervisor_planner.py -q`

## Task 2: Separate Confidence, Confirmation, And Publishability

**Files:**
- Modify: `src/pwps_agent/core/fields.py`
- Create: `src/pwps_agent/core/publishability.py`
- Modify: `src/pwps_agent/core/state_merge.py`
- Test: `tests/test_publishability.py`

- [x] **Step 1: Write failing tests**

```python
from pwps_agent.core.publishability import publishability_for_field
from pwps_agent.core.state import create_initial_state


def test_user_confirmed_field_is_publishable_draft_value():
    state = create_initial_state("Q355B GMAW", "guided_confirmation")
    field = state.fields["welding_process"]
    field.value = "GMAW"
    field.status = "user_confirmed"
    field.source = {"type": "user_confirmation"}
    assert publishability_for_field(field) == "draft_publishable"


def test_web_candidate_is_reference_only_until_confirmed():
    state = create_initial_state("Q355B GMAW", "auto_draft")
    field = state.fields["shielding_gas"]
    field.value = "80% Ar / 20% CO2"
    field.status = "candidate"
    field.source = {"type": "web"}
    field.confidence = "medium"
    assert publishability_for_field(field) == "reference_only"
```

- [x] **Step 2: Run failing tests**

Run: `uv run pytest tests/test_publishability.py -q`

- [x] **Step 3: Implement publishability helper**

Create `Publishability = Literal["draft_publishable", "needs_confirmation", "reference_only", "blocked"]`. Map user-confirmed and user-input `filled` fields to `draft_publishable`; web/local/model candidates to `reference_only` or `needs_confirmation`; blocked metadata without user source to `blocked`.

- [x] **Step 4: Add field metadata without breaking persisted state**

Add optional `publishability: str | None = None` to `FieldState`. In `state_merge.py`, after each field patch, set `field.publishability = publishability_for_field(field)`.

- [x] **Step 5: Verify**

Run: `uv run pytest tests/test_publishability.py tests/test_state_merge.py tests/test_render.py -q`

## Task 3: Evidence Policy And Promotion Gate

**Files:**
- Create: `src/pwps_agent/core/evidence_policy.py`
- Modify: `src/pwps_agent/tools/draft_verifier.py`
- Modify: `src/pwps_agent/tools/risk_report.py`
- Test: `tests/test_evidence_policy.py`

- [x] **Step 1: Write failing tests**

```python
from pwps_agent.core.contracts import Evidence
from pwps_agent.core.evidence_policy import evidence_strength, may_promote_candidate


def test_official_plus_textbook_evidence_can_support_recommendation():
    evidence = [
        Evidence(evidence_id="ev1", source_type="web", source_tier="official_standard", confidence="high", content="AWS reference"),
        Evidence(evidence_id="ev2", source_type="local_doc", source_tier="textbook", confidence="medium", content="Local guide"),
    ]
    assert evidence_strength(evidence) == "strong"
    assert may_promote_candidate(evidence, requires_human_confirmation=False) is True


def test_webpage_only_evidence_cannot_promote_key_choice():
    evidence = [
        Evidence(evidence_id="ev1", source_type="web", source_tier="webpage", confidence="low", content="Blog snippet"),
    ]
    assert evidence_strength(evidence) == "weak"
    assert may_promote_candidate(evidence, requires_human_confirmation=True) is False
```

- [x] **Step 2: Run failing tests**

Run: `uv run pytest tests/test_evidence_policy.py -q`

- [x] **Step 3: Implement policy**

Use source tier and confidence only. Do not inspect welding content. Return `strong`, `medium`, or `weak`; require human confirmation for key choices regardless of evidence strength in `guided_confirmation`.

- [x] **Step 4: Wire verifier/risk report**

Use the policy to mark weak evidence fields, key-choice confirmation requirements, and low-quality source risks. Do not auto-upgrade web/model values to `filled`.

- [x] **Step 5: Verify**

Run: `uv run pytest tests/test_evidence_policy.py tests/test_draft_quality.py tests/test_risk_report.py -q`

## Task 4: Guided Option Recommendation Tool

**Files:**
- Create: `src/pwps_agent/tools/guided_options.py`
- Modify: `src/pwps_agent/graph/supervisor.py`
- Modify: `src/pwps_agent/graph/nodes.py`
- Modify: `src/pwps_agent/core/modes.py`
- Modify: `src/pwps_agent/domain_skills/pwps_guided_confirmation.md`
- Test: `tests/test_guided_options.py`

- [x] **Step 1: Write failing tests**

```python
from pwps_agent.core.contracts import ToolResult
from pwps_agent.tools.guided_options import GuidedOption, GuidedOptionSet, merge_guided_option_set


def test_guided_options_include_recommendation_and_confirmation_requirement():
    option_set = GuidedOptionSet(
        field_id="welding_process",
        question="Confirm welding process.",
        options=[
            GuidedOption(value="GMAW", suitability="Good for productivity on plate joints.", risk_note="Confirm shielding gas and transfer mode.", recommended=True),
            GuidedOption(value="SMAW", suitability="Useful for repair or site welding.", risk_note="Lower productivity.", recommended=False),
        ],
        requires_user_confirmation=True,
    )
    result = ToolResult(tool_name="guided_options", success=True, state_patch=merge_guided_option_set(option_set), summary="ok")
    assert result.state_patch["fields"]["welding_process"]["status"] == "need_confirmation"
    assert result.state_patch["fields"]["welding_process"]["candidates"][0]["recommended"] is True
```

- [x] **Step 2: Run failing tests**

Run: `uv run pytest tests/test_guided_options.py -q`

- [x] **Step 3: Implement structured output schemas**

Create `GuidedOption` and `GuidedOptionSet` Pydantic models. The LLM may generate options and recommendations, but the merge result must keep the field `need_confirmation` until the user confirms.

- [x] **Step 4: Wire graph action**

Add `guided_options` to available graph tools. In guided mode, Supervisor should request it before `ASK_USER` when key fields are missing or have multiple candidates.

- [x] **Step 5: Verify**

Run: `uv run pytest tests/test_guided_options.py tests/test_graph_guided_confirmation.py tests/test_guided_confirmation.py -q`

## Task 5: Split Supervisor Policy From LLM Planning

**Files:**
- Create: `src/pwps_agent/graph/policy.py`
- Modify: `src/pwps_agent/graph/supervisor.py`
- Test: `tests/test_graph_supervisor_planner.py`

- [x] **Step 1: Write failing tests**

Add tests proving a repeated completed action, premature finish, and invalid auto-draft interruption are handled by `GraphPolicy.resolve(action, state)` and recorded with reason codes: `completed_action`, `premature_finish`, `auto_draft_initial_gate`, `guided_confirmation_required`.

- [x] **Step 2: Run failing tests**

Run: `uv run pytest tests/test_graph_supervisor_planner.py -q`

- [x] **Step 3: Move override logic**

Move `_override_repeated_completed_action`, `_needs_refinement_planning`, `_needs_guided_confirmation_pause`, and related helpers into `graph/policy.py`. Keep `supervisor.py` responsible for calling the LLM planner, validating schema, applying policy, and recording trace.

- [x] **Step 4: Preserve trace vocabulary**

Keep existing `agent_action_overridden` events, but add `reason_code` to payload. Do not remove old fields used by current tests.

- [x] **Step 5: Verify**

Run: `uv run pytest tests/test_graph_supervisor_planner.py tests/test_graph_auto_draft.py tests/test_graph_guided_confirmation.py -q`

## Task 6: Agent Eval Metrics

**Files:**
- Create: `src/pwps_agent/core/eval_metrics.py`
- Modify: `src/pwps_agent/storage/persist.py`
- Test: `tests/test_eval_metrics.py`

- [x] **Step 1: Write failing tests**

```python
from pwps_agent.core.eval_metrics import compute_agent_metrics
from pwps_agent.core.state import create_initial_state


def test_metrics_count_override_and_field_statuses():
    state = create_initial_state("Q355B GMAW", "auto_draft")
    state.fields["base_material"].status = "filled"
    state.fields["shielding_gas"].status = "candidate"
    state.trace.append({"event_type": "agent_action_overridden", "payload": {"reason_code": "completed_action"}})
    metrics = compute_agent_metrics(state)
    assert metrics["field_status_counts"]["filled"] == 1
    assert metrics["field_status_counts"]["candidate"] == 1
    assert metrics["override_count"] == 1
    assert metrics["override_reason_counts"]["completed_action"] == 1
```

- [x] **Step 2: Run failing tests**

Run: `uv run pytest tests/test_eval_metrics.py -q`

- [x] **Step 3: Implement metrics**

Compute field status counts, confirmation counts, weak evidence count from `quality_report`, override count, override reason counts, refinement attempts, and final status. Return plain JSON-serializable dict.

- [x] **Step 4: Persist metrics**

Write `agent_metrics.json` next to `quality_report.json` and add `agent_metrics` to `pwps.json` only if the `PWPSState` schema gets the field. Prefer separate artifact first to avoid schema churn.

- [x] **Step 5: Verify**

Run: `uv run pytest tests/test_eval_metrics.py tests/test_graph_auto_draft.py tests/test_draft_quality.py -q`

## Final Verification

- [x] Run focused mode tests:

```bash
uv run pytest tests/test_interaction_gates.py tests/test_publishability.py tests/test_evidence_policy.py tests/test_guided_options.py tests/test_eval_metrics.py -q
```

- [x] Run graph regression tests:

```bash
uv run pytest tests/test_graph_auto_draft.py tests/test_graph_guided_confirmation.py tests/test_graph_supervisor_planner.py tests/test_guided_confirmation.py tests/test_guided_confirmation_resume.py -q
```

- [x] Run full verification:

```bash
uv run pytest -q
uv run python -m compileall -q src tests
git diff --check
```

Verified on 2026-05-25:

```bash
uv run pytest tests/test_interaction_gates.py tests/test_publishability.py tests/test_evidence_policy.py tests/test_guided_options.py tests/test_eval_metrics.py -q
11 passed

uv run pytest tests/test_graph_auto_draft.py tests/test_graph_guided_confirmation.py tests/test_graph_supervisor_planner.py tests/test_guided_confirmation.py tests/test_guided_confirmation_resume.py -q
43 passed

uv run pytest -q
159 passed

uv run python -m compileall -q src tests
passed

git diff --check
passed with no output
```

End-to-end CLI smoke used a local OpenAI-compatible stub at `127.0.0.1:18080`
to avoid sending repository prompts or `.env` credentials to an external LLM:

```bash
LLM_API_KEY=stub LLM_BASE_URL=http://127.0.0.1:18080/v1 LLM_MODEL=stub KNOWLEDGE_SOURCES=model uv run pwps-agent auto-draft ... --output-dir /tmp/pwps-agent-e2e-hardening --run-id auto_dual_mode_hardening
auto result: status=done; draft contains filler, gas, polarity, current, voltage, travel speed, heat input, preheat, interpass, and PWHT draft values.

LLM_API_KEY=stub LLM_BASE_URL=http://127.0.0.1:18080/v1 LLM_MODEL=stub KNOWLEDGE_SOURCES=model uv run pwps-agent guided-draft ... --run-id guided_dual_mode_hardening3
guided pause result: status=need_user_input; guided_options produced recommended options for key fields.

uv run pwps-agent guided-confirm-resume /tmp/pwps-agent-e2e-hardening/guided_dual_mode_hardening3/pwps.json ...
guided final result: status=done; user_confirmed=12; no candidate/suggested/need_confirmation/conflict fields remain; quality report refreshed after confirmation.
```

## Progress

- [x] Removed old linear `run_auto_draft()` compatibility workflow.
- [x] Removed deterministic ER50-6 candidate fallback from field reasoning.
- [x] Added regression coverage that graph field reasoning does not create hard-coded candidates when the LLM returns no fields.
- [x] Verified cleanup with `uv run pytest tests/test_graph_auto_draft.py tests/test_evidence_reasoning.py tests/test_cli.py -q`: 33 passed.
- [x] Verified repository with `uv run pytest -q`: 142 passed.
- [x] Verified syntax with `uv run python -m compileall -q src tests`: passed.
- [x] Verified patch hygiene with `git diff --check`: passed with no output.
- [x] Implement Task 1 initial information gate.
- [x] Implement Task 2 state/publishability separation.
- [x] Implement Task 3 evidence policy.
- [x] Implement Task 4 guided option recommendation.
- [x] Implement Task 5 Supervisor policy split.
- [x] Implement Task 6 agent eval metrics.

## Task 7: Runtime Interaction Request Protocol

**Goal:** Align both product modes with the intended model: interactions happen
inside the graph as runtime pauses, while terminal, Web, or API inputs are only
transport adapters.

**Files:**
- Modify: `src/pwps_agent/core/interaction.py`
- Modify: `src/pwps_agent/core/state.py`
- Modify: `src/pwps_agent/graph/nodes.py`
- Modify: `src/pwps_agent/graph/policy.py`
- Modify: `src/pwps_agent/graph/supervisor.py`
- Modify: `src/pwps_agent/domain_skills/pwps_auto_draft.md`
- Modify: `src/pwps_agent/domain_skills/pwps_guided_confirmation.md`
- Create: `src/pwps_agent/workflows/interaction_resume.py`
- Modify: `src/pwps_agent/cli.py`
- Modify: `tests/test_interaction_gates.py`
- Modify: `tests/test_graph_guided_confirmation.py`
- Create: `tests/test_interaction_resume.py`
- Modify: `tests/test_cli.py`

- [x] Add transport-neutral `InteractionRequest`, `InteractionQuestion`, and
  `InteractionOption` contracts for graph pauses.
- [x] Store `pending_interaction` and `interaction_requests` on `PWPSState` so
  important interaction state is not only present in trace text.
- [x] Make `ask_user_node` attach an `interaction_request` payload for both
  `auto_draft` initial information pauses and `guided_confirmation` field
  confirmation pauses.
- [x] Preserve the distinction between modes: `auto_draft` only asks for missing
  minimum startup fields; `guided_confirmation` asks for recommended field
  choices and explicit confirmation.
- [x] Keep the `auto_draft` initial gate active after `requirement_understanding`
  if minimum fields are still missing, but stop asking once retrieval,
  reasoning, verification, or composition has started.
- [x] Add generic `apply_interaction_payload()` / `resume_interaction()` so CLI,
  Web, or API adapters can resume the same graph pause shape.
- [x] Ensure generic `interaction-resume` builds the same real runtime
  dependencies as normal draft runs when dependencies are not injected.
- [x] Add `pwps-agent interaction-resume` as the terminal adapter for the generic
  interaction protocol.

Focused verification during implementation:

```bash
uv run pytest tests/test_interaction_gates.py::test_initial_info_request_is_transport_neutral_runtime_payload -q
1 passed

uv run pytest tests/test_graph_guided_confirmation.py::test_ask_user_node_pauses_with_confirmation_view -q
1 passed

uv run pytest tests/test_graph_guided_confirmation.py::test_ask_user_node_pauses_auto_draft_for_initial_context -q
1 passed

uv run pytest tests/test_interaction_resume.py -q
1 passed

uv run pytest tests/test_cli.py::test_cli_parser_accepts_generic_interaction_resume -q
1 passed

uv run pytest tests/test_interaction_gates.py tests/test_interaction_resume.py tests/test_graph_guided_confirmation.py tests/test_graph_supervisor_planner.py -q
26 passed

uv run pytest tests/test_cli.py -q
16 passed

uv run pytest tests/test_guided_confirmation_resume.py tests/test_guided_confirmation_web.py tests/test_guided_confirmation.py -q
15 passed

uv run pytest tests/test_interaction_gates.py tests/test_graph_auto_draft.py tests/test_graph_supervisor_planner.py -q
35 passed

uv run pytest tests/test_interaction_resume.py tests/test_cli.py::test_cli_parser_accepts_generic_interaction_resume -q
3 passed
```

## Task 8: Prompt Centralization Cleanup

**Goal:** Keep production LLM prompt text centralized and documented. Runtime
code can still assemble structured state payloads, but model role, task
boundary, mode behavior, safety language, and output expectations should live in
`configs/prompts/` or Domain Skill markdown.

**Files:**
- Create: `configs/prompts/README.md`
- Create: `configs/prompts/supervisor.md`
- Create: `configs/prompts/supervisor_mode_auto_draft.md`
- Create: `configs/prompts/supervisor_mode_guided_confirmation.md`
- Create: `configs/prompts/supervisor_mode_supplement_update.md`
- Modify: `configs/prompts/knowledge_planning.md`
- Modify: `src/pwps_agent/graph/supervisor.py`
- Modify: `src/pwps_agent/tools/knowledge_planning.py`
- Modify: `tests/test_domain_skills.py`
- Modify: `tests/test_graph_supervisor_planner.py`

- [x] Add a prompt registry README explaining ownership, file purpose, and the
  boundary between centralized prompt text and runtime state payloads.
- [x] Move Supervisor base prompt and mode-specific prompt text out of
  `graph/supervisor.py` and into `configs/prompts/`.
- [x] Keep `LLMSupervisorPlanner` responsible for assembling loaded prompt
  files, mode prompt, and Domain Skill context.
- [x] Move the remaining knowledge-planning instruction sentence from the
  runtime user-payload builder into `configs/prompts/knowledge_planning.md`.
- [x] Add tests proving Supervisor prompt files load and production Supervisor
  prompt text is not hardcoded in `_system_prompt()`.

Focused verification during implementation:

```bash
uv run pytest tests/test_domain_skills.py::test_supervisor_prompts_are_loaded_from_prompt_directory tests/test_graph_supervisor_planner.py::test_llm_supervisor_planner_loads_production_prompt_text_from_prompt_files tests/test_graph_supervisor_planner.py::test_llm_supervisor_planner_describes_mode_specific_closure_rules -q
3 passed
```

## Task 9: Live Remote Structured Output Robustness

**Goal:** Keep real remote-provider structured-output parser failures from
ending an otherwise recoverable draft run when a safe deterministic fallback is
available.

**Files:**
- Modify: `src/pwps_agent/tools/knowledge_planning.py`
- Modify: `tests/test_knowledge_planning.py`

- [x] Catch structured-output/provider parser exceptions in
  `plan_knowledge_queries()`.
- [x] Fall back to the existing targeted fallback query and preserve the parser
  error in `ToolResult.errors` for trace/debugging.
- [x] Add regression coverage for the parser-failure fallback path.

Focused verification:

```bash
uv run pytest tests/test_knowledge_planning.py tests/test_interaction_resume.py -q
6 passed

uv run pytest -q
168 passed
```

## Task 10: Guided Mode Empty-Pause Guard

**Goal:** Prevent the LLM Supervisor from pausing guided-confirmation runs before
the agent has gathered candidates, missing-field targets, or confirmation
content to show the user.

**Files:**
- Modify: `src/pwps_agent/graph/policy.py`
- Modify: `tests/test_graph_supervisor_planner.py`

- [x] Override premature guided `ASK_USER` actions when no pending confirmation
  fields exist.
- [x] Override premature `guided_options` tool calls when there are no missing,
  candidate, conflicting, or confirmation-required fields to build options from.
- [x] Route both cases back to the safe next graph action, normally
  `knowledge_planning` after requirement understanding.

Focused verification:

```bash
uv run pytest tests/test_graph_supervisor_planner.py::test_graph_policy_prevents_empty_guided_confirmation_pause tests/test_graph_supervisor_planner.py::test_graph_policy_prevents_empty_guided_options_tool_call -q
2 passed

uv run pytest tests/test_graph_supervisor_planner.py tests/test_graph_guided_confirmation.py tests/test_guided_confirmation_resume.py -q
30 passed

uv run pytest -q
170 passed
```

## Task 11: Inline Interactive CLI Adapter

**Goal:** Make the CLI behave like a real terminal interaction adapter for the
same graph pause protocol. When `auto-draft`, `guided-draft`, or `draft` reaches
`status=need_user_input` in an interactive terminal, the command should print the
runtime question, show recommendations/options when available, block for user
input, apply the response through `resume_interaction()`, and continue the graph
inside the same process. Non-TTY/scripted runs keep the previous behavior and
can still use `interaction-resume`.

**Files:**
- Modify: `src/pwps_agent/cli.py`
- Modify: `tests/test_cli.py`

- [x] Add an inline interactive continuation loop after `draft`,
  `auto-draft`, and `guided-draft` graph invocation.
- [x] Keep graph/runtime semantics unchanged: the CLI only adapts
  `pending_interaction` into terminal prompts and resumes through
  `resume_interaction()`.
- [x] For initial auto-draft context, prompt each missing minimum field in the
  same command instead of requiring a second resume command.
- [x] For guided confirmation, print candidate options, mark recommended values,
  show suitability/risk notes, accept an option number or direct value, and then
  continue.
- [x] Preserve non-interactive script compatibility by only blocking when
  `stdin.isatty()` is true.

Focused verification:

```bash
uv run pytest tests/test_cli.py -q
18 passed
```

Follow-up structure work moved into
`docs/superpowers/plans/2026-05-26-interaction-adapters-and-web-workbench.md`:
CLI and React Web are now treated as adapters above `pending_interaction` /
`resume_interaction()`, and the old embedded guided-confirmation HTML is being
retired in favor of a mode-neutral runtime Web API plus React workbench.
