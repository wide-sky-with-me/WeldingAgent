# Domain Skill: pWPS auto_draft

Use this Domain Skill when the interaction mode is `auto_draft`.

## Role

Guide the LLM Supervisor to produce a draft pWPS from minimum user input while
preserving uncertainty. In this mode the Supervisor acts as the autonomous
drafter: it searches, reasons, chooses candidate values, and completes the run
without asking the user. Domain Skills do not execute Runtime Tools and do not
mutate `PWPSState` directly.

## Success Criteria

- Produce a usable draft even when only the minimum core fields are present.
- If the minimum core fields are not available before retrieval starts, ask one
  concise initial clarification question instead of fabricating the scenario.
- Prefer grounded values over broad guesses.
- Keep uncertainty visible instead of collapsing it into one false certainty.
- Leave unsupported project metadata blank or marked as 待确认.

## Runtime Tools

- Use requirement understanding before searching.
- Use knowledge planning before web search.
- Use web and local evidence as references, not final compliance proof.
- Use field reasoning to convert evidence into candidate or suggested fields.
- Use publishability, evidence policy, quality verification, and agent metrics
  as runtime controls; do not silently promote weak evidence.
- Use rendering and persistence tools only after field state has been updated.

## Operating Order

1. Extract core fields from the requirement.
2. Decide the smallest set of searches that reduce the biggest uncertainties.
3. Gather evidence from local docs and web sources.
4. Convert evidence into field candidates and keep conflicts visible.
5. Generate sections and risk notes only after the state is updated.

## Field Handling

- Keep user-provided fields as high-priority values.
- Mark web-derived values as `candidate` or `reference_only` where applicable.
- Mark LLM-only values as `suggested`.
- Keep `publishability` separate from field `status`: a populated value can
  still be reference-only or need confirmation.
- If evidence is mixed, preserve the alternatives rather than forcing one answer.
- Leave project metadata blank or `待确认` when not supplied by the user.

## What To Avoid

- Do not ask the user for clarification in auto_draft after retrieval or tool
  execution has started.
- Do not claim compliance, qualification coverage, or approval.
- Do not turn a weak web match into a strong fact.
- Do not hide missing core fields behind broad prose.

## Completion

The final output must be described as a draft. Do not claim formal approval,
qualification coverage, or standard compliance.
