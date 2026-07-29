# v1.1.0b3 release-candidate re-audit 2

Oracle CLI: `0.16.1`
Valid session: `digimou-b3-final-reaudit-two-4`
Engine: browser with `--browser-manual-login`
Requested Oracle model ID: `gpt-5.6`
Picker evidence: `GPT-5.6 Sol` / `GPT-5.6 Sol`, verified `yes`
Answer model statement: active `GPT-5.6 Thinking`, non-Pro
Elapsed: 4 minutes 14 seconds
Input: approximately 30,170 tokens across 7 individual files
Result at answer time: `CANARY PASS / RELEASE BLOCKED`

The dry-run reported seven individual attachments and `bundled: null`.
The response passed both the non-Pro model and attachment canaries.

## Release blocker

No remaining product-path release blocker was found.

### RB-B3-R1 — resolved

Oracle confirmed that shared extraction functions validate non-empty
electrical symbol pins and normalized numbered electrical footprint pads.
`_verify_metadata_cad()` validates every requested parsed artifact
independently. A parsed-empty symbol or footprint becomes `None` while the
other valid artifact remains intact, so automatic discovery receives exactly
the invalid artifact kind.

A true non-empty pin/pad mismatch still returns both parsed objects with
`CAD_PIN_PAD_MISMATCH`, and the missing-artifact mapper replaces both requested
members only in that case.

The attached regressions covered symbol-only zero pins, footprint-only zero
pads, each one-empty full request, exact missing kinds, mismatch replacement,
and a neutral no-external-match result that remains fail-closed.

Classification: **RESOLVED**.

## Should fix

### SF-B3-R1 — open at answer time

Oracle confirmed that commit-subject collection and complete issue-history
pagination were removed. It found that changed-path collection was still
unbounded because `_git_paths()` used `subprocess.run(stdout=PIPE)` and only
compared the materialized tuple with `MAX_CHANGED_PATHS` afterward.

The existing test mocked `_git_paths()` with 10,001 already-materialized
entries, so it proved post-collection rejection but not early termination.

Classification at answer time: **SHOULD FIX — OPEN**.

Exact minimum correction:

1. Consume `git diff --name-only -z` incrementally.
2. Retain at most `MAX_CHANGED_PATHS + 1` decoded paths and terminate/reap Git
   on the first over-limit path.
3. Use the bounded reader for ordinary and added-only collection.
4. Test the actual reader and prove it stops and terminates the producer.
5. Repeat focused, full, static, build, Twine, and isolated-wheel gates.

The answer ended with: “No further Oracle review is requested.”

## Post-answer disposition

All five exact requirements were adopted:

- `_git_paths()` now launches fixed-executable Git without a shell and reads
  NUL-delimited stdout in 64 KiB chunks.
- It raises on the first path above `MAX_CHANGED_PATHS`, terminates the child,
  waits up to five seconds, and kills then reaps it only if termination stalls.
- Stderr uses a temporary file, so a producer cannot deadlock the bounded stdout
  reader by filling a second pipe.
- Both ordinary and `--diff-filter=A` collection use the same implementation.
- The reader regression uses an oversized chunked producer and asserts that it
  was terminated and waited, stdout was closed, and trailing bytes remained
  unread. The inspection-level limit test remains.

Post-fix evidence:

- focused matrix: `80 passed`;
- Python 3.12 full suite: `1010 passed, 77 skipped`;
- Ruff lint/format: 96 files;
- strict mypy: 43 source files;
- sdist/wheel build and Twine: pass;
- isolated wheel: `1.1.0b3`, 53 entries, all three schemas, no upstream
  `easyeda2kicad/` namespace.

Because re-audit 2 was the final permitted audit and explicitly requested no
further review, this exact post-answer correction is closed by deterministic
local evidence rather than a third re-audit.

## Accepted risks

- Real Mouser-linked package registration and KiCad CLI/GUI proof remain
  incomplete and complete Mouser CAD support remains unclaimed.
- Native Linux process E2E remains outside the evidence.
- Inherited reference-output skips remain disclosed.
- README-change detection is a conservative review heuristic, not semantic
  proof.

## Optional

- The human startup banner retains the legacy `easyeda2kicad.py` name.
- GitHub Actions use major-version action tags rather than immutable hashes.

## Earlier findings

Oracle found no evidenced regression in initial `RB-B3-1` through `RB-B3-5`
or `SF-B3-1` through `SF-B3-3`.
