# Domain Skill: pWPS risk_review

Use this Domain Skill before presenting a draft or field report.

## Success Criteria

- Surface the risks that matter to procedure drafting, not generic warnings.
- Tie each risk to a missing field, weak source, or assumption.
- Make it obvious what still needs confirmation.

## Risk Focus

- Missing core fields.
- Low-confidence candidate fields.
- Thermal control, preheat, interpass, PWHT, and heat input values without
  strong evidence.
- Qualification-sensitive assumptions such as process, position, material group,
  thickness range, and joint configuration.
- Project metadata that was not supplied by the user.

## Risk Priorities

- Highest: thermal control, PWHT, heat input, and qualification-sensitive
  assumptions.
- High: missing core scope fields that affect search and draft structure.
- Medium: candidate fields with weak or conflicting evidence.
- Lower: project metadata gaps, unless they are needed for a formal document.

## Wording

- Use `needs confirmation`, `candidate`, `suggested`, and `reference` language.
- Explain why confirmation is needed in concise engineering terms.
- Do not claim compliance, qualification, approval, or sign-off.

## Output Pattern

- risk item
- severity
- affected field
- why it matters
- evidence or gap description
- recommended next action

## State Handling

Risk notes should be reflected in field status, field notes, report risks, or
clarification questions. Important risk information must not live only in chat.
