# New RC re-audit 1 quality evidence

Generated: 2026-07-23 (Asia/Tokyo)

## Initial-audit disposition

Oracle session `easyeda-new-rc-initial-audit` completed with
**CANARY PASS / RELEASE BLOCKED**. Its answer is preserved in
`docs/oracle/release_candidate_audit_rc3.md` with SHA-256
`2a2c63dcbe6c21597bcaaaee42242dd81a2887a1eaef1187ed6efca6135edebb`.
All 20 initial source-canary hashes matched immediately after the answer.

Codex independently confirmed and adopted:

- `RB-RC3-1`: overflowing/non-finite numeric data could escape the exact
  Provider and normalized-cache boundaries as untyped `OverflowError`;
- `SF-RC3-1`: a manifest below the selected symbol file was not rejected before
  CAD export; and
- `DOC-RC3-1`: historical RC2 `666 passed` rows were labelled as the current
  tree.

The three previously accepted risks remain unchanged.

## Minimal fixes

- Shared optional numeric parsing now rejects non-finite and overflowing values
  as `ValueError`; the common exact-candidate boundary converts
  `OverflowError`, `TypeError`, and `ValueError` to typed
  `INVALID_RESPONSE/exact-normalize`.
- Normalized model/cache reconstruction maps overflow to the existing online
  miss and offline corruption semantics. Refresh still bypasses the entry.
- Manifest collision preflight records whether each selected output is a file
  or directory. Only the symbol file rejects containment in both directions;
  footprint, 3D, and SVG directories still allow normal child manifests.
- The historical compatibility rows are now labelled `RC2 pre-RC3 tree` and
  point to the current quality record.

No API, CLI spelling, output format, dependency, cache schema, or Provider
responsibility changed.

## Regression probes

| Probe | Result |
| --- | --- |
| New Oracle-blocker probes | `8 passed` |
| Related Provider/cache/CLI/E2E files | `280 passed` |

The new probes cover:

- DigiKey, Mouser, and LCSC overflowing exact candidates through live-shaped
  transport and direct raw-response replay;
- common optional numeric parser rejection of infinity, NaN, oversized
  integers, and oversized numeric text;
- schema-3 normalized cache online refetch, offline corruption, refresh bypass,
  and validator-overflow mapping; and
- JSON and CSV manifests nested below a planned symbol file, with metadata
  resolution never entered and no parent, symbol, manifest, or cache output.

## Full quality matrix

| Gate | Result |
| --- | --- |
| Python 3.9.25 full pytest | `695 passed, 71 skipped` |
| Python 3.12.13 full pytest | `695 passed, 71 skipped` |
| Python 3.14.3 full pytest | `695 passed, 71 skipped` |
| Ruff format check | PASS, `59 files already formatted` |
| Ruff lint | PASS |
| Python 3.9 strict mypy | PASS, 59 source files |
| `git diff --check` | PASS; only Git LF/CRLF working-tree notices |

The pass count increased by eight from the initial RC3 audit and the skip count
did not change. The 69 inherited reference-output skips and two credentialed
live-Provider skips remain the previously accepted risks. Native Linux
process-level E2E remains unrun.

The first parallel full-suite harness also printed the same three successful
`695 passed, 71 skipped` summaries, but its PowerShell wrapper treated an empty
post-exit process property as failure. The standard sequential commands were
therefore rerun and each returned exit code 0; only those clean runs are the
authoritative matrix above.
