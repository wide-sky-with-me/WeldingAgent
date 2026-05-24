# Domain Skill: pWPS guided_confirmation

Use this Domain Skill when the interaction mode is `guided_confirmation`.

## Role

Guide the LLM Supervisor to discuss related pWPS field groups with the user and
promote only explicit user choices to confirmed fields.

## Confirmation Pattern

- Present a small group of related fields.
- Show the current value, candidate value, evidence reference, confidence, and
  risk note for each field.
- Ask for confirmation, modification, skip, or deferral.
- Record user-confirmed values in `PWPSState.confirmations`.

## Constraints

- Do not treat silence as confirmation.
- Do not promote web-derived or LLM-derived values to `user_confirmed`.
- Do not invent missing project metadata.
- Do not overload the user with unrelated field groups.
