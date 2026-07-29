# v1.1.0b3 release-candidate re-audit 1

Oracle CLI: `0.16.1`
Session: `digimou-b3-reaudit-one`
Engine: browser with `--browser-manual-login`
Requested/resolved model: `Thinking 5.5` / `Thinking 5.5`
Model verification: `yes`
Elapsed: 10 minutes 36 seconds
Input: approximately 50,850 tokens across 10 individual files
Result: `CANARY PASS / RELEASE BLOCKED`

The dry-run and completed session both used explicit standard model
`gpt-5.5`. The dry-run reported ten attachments and `bundled: null`.

## Canary

Oracle confirmed that every attachment was present and readable, the repository
prohibits Pro-tier selection, README and release notes identify `1.1.0b3`, the
CLI owns post-verification automatic fallback, one handoff must contain every
requested artifact, evidence-free Mouser paths do not infer SamacSys, and the
README monitor publishes bounded safe output.

## Release blocker

### RB-B3-R1 — parsed-but-empty artifacts bypass semantic validation

Oracle found that `_verify_metadata_cad()` accepted a requested symbol-only or
footprint-only parse without requiring a non-empty electrical pin or numbered
plated-pad set. For a full request it reported the empty set as invalid but
returned both parsed objects. `_missing_requested_easyeda_artifacts()` treated
only `None`, missing 3D, and `CAD_PIN_PAD_MISMATCH` as missing, so a generic
invalid parsed artifact did not enter DigiKey/Mouser discovery.

Minimum requested correction:

1. Validate non-empty electrical pins for symbol-only requests.
2. Validate non-empty numbered electrical pads for footprint-only requests.
3. Propagate the specific invalid artifact into the missing-artifact set.
4. Preserve replacement of both artifacts for a true pin/pad mismatch.
5. Test both single-artifact paths, each one-empty full path, and a neutral
   no-external-match fail-closed result.
6. Repeat all focused, full, static, build, Twine, and isolated-wheel gates.

Disposition: **adopted and fixed**. Shared pin/pad extractors now validate every
requested parsed artifact. An empty parsed artifact is returned as `None`, so
the existing missing-artifact mapper sends exactly that kind to external
discovery. True mismatches retain their existing two-artifact replacement
rule. Four empty-artifact matrix cases and one neutral no-match integration
case were added.

## Should fix

### SF-B3-R1 — bounded output, unbounded monitor input collection

Oracle accepted that public issue content was bounded and sanitized but noted
that the checker still collected every commit subject and changed path, while
the workflow paginated the complete issue history.

Disposition: **adopted and fixed**. Repository inspection no longer invokes
`git log` or collects commit subjects. It stops fail-closed above 10,000 changed
paths. Workflow deduplication requests only the 100 most recently updated
issues rather than paginating all history. A fail-closed changed-path limit
regression and workflow assertions were added.

## Accepted risks

- A real Mouser-linked package has not completed project registration, KiCad
  CLI, and KiCad GUI validation. Complete Mouser CAD support remains unclaimed.
- Native Linux process E2E remains outside the evidence and is disclosed.
- The inherited reference-output skips remain disclosed.
- README-change detection remains a conservative review heuristic, not proof
  that an edit is semantically sufficient.

## Optional

- The legacy human banner still says `easyeda2kicad.py`; `--version` and package
  identity remain the distinct +DigiMou beta.
- GitHub Actions use major-version tags rather than immutable commit hashes.

## Resolved from the initial audit

Oracle confirmed all initial items:

- `RB-B3-1`: the service/CLI automatic-handoff short circuit is removed.
- `RB-B3-2`: split packages and irrelevant handoffs are rejected.
- `RB-B3-3`: evidence-free Mouser paths do not infer SamacSys.
- `RB-B3-4`: existing and new human log handlers receive configured-secret
  filtering and final rendered-text redaction.
- `RB-B3-5`: public monitor content contains no raw paths or commit subjects.
- `SF-B3-1`: ordinary production changes no longer bypass monitoring based on
  commit-subject spelling.
- `SF-B3-2`: a default-branch-named tag cannot satisfy the branch-only guard.
- `SF-B3-3`: the artifact fallback matrix is materially expanded, with the new
  empty-artifact cases required before publication.

## Re-audit verdict

Oracle ended with `RELEASE BLOCKED` until `RB-B3-R1` and its regression matrix
were complete. Those changes are now implemented and locally validated; they
must receive re-audit 2 before the GitHub-only pre-release is published.
