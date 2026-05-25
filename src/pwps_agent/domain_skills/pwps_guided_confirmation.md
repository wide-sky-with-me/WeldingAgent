# Domain Skill: pWPS guided_confirmation

Use this Domain Skill when the interaction mode is `guided_confirmation`.

## Role

Guide the LLM Supervisor to discuss related pWPS field groups with the user and
promote only explicit user choices to confirmed fields.

## Success Criteria

- Ask for the smallest useful confirmation set.
- Present related fields together instead of one-off interrogation.
- Make the tradeoff, evidence, and risk visible for each group.
- Present recommended options before asking for confirmation when key fields are
  missing, weak, conflicting, or have multiple candidates.
- Record only explicit user confirmations as confirmed state.

## Confirmation Pattern

- Present a small group of related fields, usually 3-5 at a time.
- Show the current value, candidate value, evidence reference, confidence, and
  risk note for each field.
- Mark the recommended option explicitly and explain the suitability and risk
  in concise engineering terms.
- If critical input fields are missing, ask for them with a short explanation of
  why they affect the draft.
- Ask for confirmation, modification, skip, or deferral with concise options
  rather than open-ended interrogation.
- Record user-confirmed values in `PWPSState.confirmations`.
- Keep a clear separation between confirmed, candidate, and reference-only
  values.
- Keep the field in `need_confirmation` or candidate-like status until the user
  confirms; option recommendation is not confirmation.

## Grouping Strategy

- Start with core scope fields if they are missing or weak.
- Then cover filler and auxiliary materials.
- Then cover welding parameters.
- Then cover thermal control and heat treatment when they are still uncertain.

## Wording Pattern

- Use concise engineering language.
- Explain why the field matters in one sentence.
- Avoid long narratives when a direct option list will do.
- Do not let silence count as agreement.

## Constraints

- Do not treat silence as confirmation.
- Do not promote web-derived or LLM-derived values to `user_confirmed`.
- Do not let a recommended option bypass the evidence policy or publishability
  boundary.
- Do not invent missing project metadata.
- Do not overload the user with unrelated field groups.
