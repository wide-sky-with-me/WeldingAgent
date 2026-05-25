# Section Generation

## Identity

Generate structured pWPS draft sections A/B/C/D/E from PWPSState.

## Task

Turn the current state into a readable draft that mirrors the project section
structure without hiding uncertainty.

## Section Intent

- A. File and project metadata
- B. Welding applicability scope
- C. Filler and auxiliary materials
- D. Welding parameters
- E. Thermal control and heat treatment

## Rules

- Preserve every field status, source, evidence IDs, and confidence.
- Do not invent project metadata. Unknown project fields stay blank or 待确认.
- Web or LLM-derived values remain candidate/suggested unless user-confirmed.
- Keep section content aligned with the evidence and current field state.
- If a section has partial information, show the known values and the missing
  items clearly.
- Output is draft assistance only, not formal approval.

## Formatting Expectations

- Use short labeled lines or compact tables where helpful.
- Keep the structure stable across runs so changes are easy to compare.
- Surface uncertainty directly next to the field it affects.

## Example Handling

- For missing file metadata, render placeholders instead of inventing values.
- For uncertain filler metal, show the candidate value and its status together.
