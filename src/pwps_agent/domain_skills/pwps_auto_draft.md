# Domain Skill: pWPS auto_draft

Use this Domain Skill when the interaction mode is `auto_draft`.

## Role

Guide the LLM Supervisor to produce a draft pWPS from minimum user input while
preserving uncertainty. The Supervisor remains the decision maker. Domain Skills
do not execute Runtime Tools and do not mutate `PWPSState` directly.

## Runtime Tools

- Use requirement understanding before searching.
- Use knowledge planning before web search.
- Use web and local evidence as references, not final compliance proof.
- Use field reasoning to convert evidence into candidate or suggested fields.
- Use rendering and persistence tools only after field state has been updated.

## Field Handling

- Keep user-provided fields as high-priority values.
- Mark web-derived values as `candidate` or `reference_only` where applicable.
- Mark LLM-only values as `suggested`.
- Leave project metadata blank or `待确认` when not supplied by the user.

## Completion

The final output must be described as a draft. Do not claim formal approval,
qualification coverage, or standard compliance.
