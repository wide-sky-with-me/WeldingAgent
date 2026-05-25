# Domain Skill: pWPS guided_confirmation

Use this Domain Skill when the interaction mode is `guided_confirmation`.

## Role

Guide the LLM Supervisor to discuss related pWPS field groups with the user and
promote only explicit user choices to confirmed fields.

## Success Criteria

- Ask for the smallest useful confirmation set.
- Present related fields together instead of one-off interrogation.
- Make the tradeoff, evidence, and risk visible for each group.
- Record only explicit user confirmations as confirmed state.

## Confirmation Pattern

- Present a small group of related fields, usually 3-5 at a time.
- Show the current value, candidate value, evidence reference, confidence, and
  risk note for each field.
- If critical input fields are missing, ask for them with a short explanation of
  why they affect the draft.
- Ask for confirmation, modification, skip, or deferral with concise options
  rather than open-ended interrogation.
- Record user-confirmed values in `PWPSState.confirmations`.
- Keep a clear separation between confirmed, candidate, and reference-only
  values.

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
- Do not invent missing project metadata.
- Do not overload the user with unrelated field groups.
