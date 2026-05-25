# Domain Skill: pWPS evidence_handling

Use this Domain Skill when the Supervisor needs to classify or interpret
evidence for pWPS fields.

## Success Criteria

- Keep evidence tied to the exact field it supports.
- Preserve uncertainty and conflicts.
- Keep source quality visible in the state.

## Source Classes

- User input and user confirmation are high-priority state evidence.
- Local documents may support candidates when source context is preserved.
- Web references are external reference evidence and need confirmation.
- LLM-derived values are suggestions unless supported by user or document
  evidence.

## Evidence Hierarchy

- User-confirmed values override other sources.
- Local document evidence is stronger than general web reference when it names
  the same field in a close procedural context.
- Web evidence is useful for candidate values, but should stay reference-only
  unless confirmed.
- LLM-only values are the weakest and should be labeled as suggestions.

## Evidence Rules

- Every generated field should keep source, evidence IDs, confidence, and status
  when possible.
- Prefer explicit evidence claims over broad page titles.
- Preserve conflicting evidence as candidate alternatives rather than overwriting
  user-provided fields.
- Never describe a web result as verified standard fact.

## Output Pattern

- Field name
- Evidence source class
- Evidence IDs
- Status
- Short rationale
- Remaining uncertainty

## Runtime Tools

The Supervisor should use Runtime Tools to search, extract, merge, and render.
Domain Skills only guide the Supervisor's choices and wording.
