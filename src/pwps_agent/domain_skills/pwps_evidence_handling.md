# Domain Skill: pWPS evidence_handling

Use this Domain Skill when the Supervisor needs to classify or interpret
evidence for pWPS fields.

## Source Classes

- User input and user confirmation are high-priority state evidence.
- Local documents may support candidates when source context is preserved.
- Web references are external reference evidence and need confirmation.
- LLM-derived values are suggestions unless supported by user or document
  evidence.

## Evidence Rules

- Every generated field should keep source, evidence IDs, confidence, and status
  when possible.
- Prefer explicit evidence claims over broad page titles.
- Preserve conflicting evidence as candidate alternatives rather than overwriting
  user-provided fields.
- Never describe a web result as verified standard fact.

## Runtime Tools

The Supervisor should use Runtime Tools to search, extract, merge, and render.
Domain Skills only guide the Supervisor's choices and wording.
