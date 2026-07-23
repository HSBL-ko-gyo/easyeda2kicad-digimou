# Repository agent instructions

## Oracle review budget

- Do not request or select an Oracle Pro model, including `gpt-5.5-pro`.
- Do not use a `--model` value that resolves to a Pro tier.
- For Architecture Review, Stuck Consultation, and Release Candidate Audit,
  use an available non-Pro/standard model with the browser engine and
  `--browser-manual-login` unless the user explicitly changes this rule.
- If the available Oracle choices are Pro-only or the tier cannot be verified,
  do not spend a Pro review. Record the limitation under `docs/oracle/` and
  follow the repository's Oracle availability policy.
- Historical Oracle attempts recorded in `docs/oracle/README.md` may mention
  Pro; they do not authorize future Pro usage.

