Generate structured pWPS draft sections A/B/C/D/E from PWPSState.

Rules:
- Preserve every field status, source, evidence IDs, and confidence.
- Do not invent project metadata. Unknown project fields stay blank or 待确认.
- Web or LLM-derived values remain candidate/suggested unless user-confirmed.
- Output is draft assistance only, not formal approval.
