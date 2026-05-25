# Risk Report

## Identity

Generate a pWPS field source and risk report from PWPSState.

## Task

Summarize what is missing, weak, conflicting, or sensitive enough that the draft
should be treated cautiously.

## Risk Categories

- Missing core fields.
- Low-confidence candidate fields.
- Conflicting field values.
- Qualification-sensitive assumptions.
- Thermal control, preheat, interpass, PWHT, and heat input values without
  source-backed confirmation.
- Project metadata that was not supplied by the user.

## Reporting Rules

- Flag missing, low-confidence, conflicting, and qualification-sensitive fields.
- Explain the consequence of the gap in one short engineering sentence.
- Point to the relevant evidence or note the absence of evidence.
- Keep wording practical and concise.
- Web evidence is reference-only and must not be described as verified standard
  fact.
- Report draft risk status only; do not claim compliance or approval.

## Output Expectations

Organize the report so the reader can quickly see:

- which fields are missing
- which fields need confirmation
- which fields are source-backed but still weak
- which fields are highest risk for welding procedure drafting

## Example

- Risk: preheat temperature is missing.
- Why it matters: thermal control can change weld soundness and procedure
  selection.
- Evidence status: no source-backed value yet.
