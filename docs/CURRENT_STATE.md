# Current state

Last updated: 2026-07-23 (Asia/Tokyo)

## Current phase

RC2 remains closed as **CANARY PASS / RELEASE BLOCKED** with its two-re-audit
limit unchanged. RC3 remains preserved as **CANARY PASS / RELEASE APPROVED**.
The subsequent public-beta field-table audit found and fixed runtime issues.
Its distinct corrective RC and release-prep re-audit 1 both passed Oracle with
no release blocker. Version and package/release metadata are prepared for
`1.1.0b1`; only the final doc-only delta, commit/tag, and external publication
gates remain.

## Completed

- Preserved upstream `uPesy/easyeda2kicad.py` at
  `fff10a38619963d7cb1c57d779655a9ea4572e95`, retained `origin`, and worked on
  local branch `feature/multi-distributor-metadata` without commit, stash,
  push, or GitHub fork.
- Added separate distributor-metadata and EasyEDA-CAD provider boundaries,
  exact-MPN models, provenance/conflicts, safe diagnostics, schema-v3 evidence
  cache, JSON/CSV manifests, and a native-only KiCad-property projection.
- Added official DigiKey Product Information V4/OAuth and Mouser Search API V2
  clients with environment-only credentials, bounded retry, deterministic
  exact-result validation, and credential-safe errors.
- Added a dedicated anonymous JLCPCB catalogue client for LCSC metadata while
  retaining the existing EasyEDA transport solely for CAD.
- Kept the legacy `--lcsc_id` path separate and additive CLI options opt-in.
- Implemented strict offline/refresh semantics, CAD identity reconciliation,
  LCSC-ID/MPN mismatch rejection, `CAD_NOT_FOUND`, `--require-cad`, action-aware
  CAD parsing, and pin/pad verification.
- Completed Oracle Architecture Review and consultation 001. Their BLOCKER and
  SHOULD FIX findings were dispositioned before implementation continued. The
  later RC audit found a new exact-identity blocker and a reverse path-collision
  gap; those final-audit findings are recorded separately below.
- Fixed RB-RC2-1 through one shared exact-aware normalization boundary. Unknown
  raw MPNs and exact candidates that cannot become complete records now fail
  `INVALID_RESPONSE`; only a provably different raw MPN is skipped. Mouser
  missing/null `Parts` is invalid, including zero-result responses.
- Bumped metadata cache schema from 2 to 3 so older normalized successes cannot
  cross the completeness boundary. Incomplete live/refresh responses are not
  cached, and offline cannot reduce them to a false exact hit.
- Fixed SF-RC2-1 by rejecting manifests that are equal to or ancestors of CAD
  output before any persistent output. Normal child manifests and adjacent
  prefixes remain valid.
- Adopted initial-audit `RB-RC3-1`: non-finite/overflowing numeric fields now
  become typed exact Provider failures, and schema-3 normalized cache preserves
  online/offline/refresh semantics.
- Adopted initial-audit `SF-RC3-1`: a manifest below the planned symbol output
  file is rejected before metadata resolution or output. Child manifests remain
  valid for selected CAD directories.
- Completed the two-part public-beta Symbol Fields Table audit. Metadata mode
  now adds zero custom columns for OPA333AIDBVR and LM321MF/NOPB; Provider,
  status, provenance, cache, and sales data remain Manifest-only.
- Added fail-closed part-scoped LCSC evidence for an explicit manufacturer that
  differs from the same-part EasyEDA display, while preserving the existing CAD
  Manufacturer property rather than silently overwriting it.
- Fixed idempotent `--overwrite` for slash-bearing symbol names by using the
  serialized KiCad ID for lookup and replacement.
- Added checked-in C2040 offline fixture/goldens and verified legacy exit code,
  stdout/stderr, no-network behavior, and byte-for-byte symbol/footprint output.
- Completed real public LCSC/EasyEDA E2E on Windows:
  - OPA333AIDBVR / C30878: symbol, footprint, WRL, STEP, JSON, and CSV;
    root/CAD status `VERIFIED`.
  - LM321MF/NOPB / C131103: symbol, footprint, WRL, STEP, JSON, and CSV;
    root/CAD status `VERIFIED`.
- Validated the two real manifests and the explicit mocked `CAD_NOT_FOUND`
  manifest with `tests/test_documented_examples.py`: `4 passed`.
- The field-table corrective initial Oracle audit used ten individual files,
  no bundle/cache, and passed post-answer canaries 10/10 and 17/17. Oracle
  reported no RELEASE BLOCKER, SHOULD FIX, or OPTIONAL item.
- Selected PEP 440 version `1.1.0b1` and tag `v1.1.0b1` because upstream
  `1.0.1` is already stable; kept distribution/import/CLI name unchanged.
- Prepared README, NOTICE, setup metadata, GitHub issue form, private security
  route, and beta release notes for `easyeda2kicad +DigiMou`.
- Built `easyeda2kicad-1.1.0b1.tar.gz` and
  `easyeda2kicad-1.1.0b1-py3-none-any.whl` from a clean external Git snapshot.
  Both contain `LICENSE`, `NOTICE`, and all package modules while excluding
  tests, caches, Oracle material, and credentials.
- Installed the wheel and sdist into separate fresh Python 3.9 venvs. Both
  report `1.1.0b1`, their console CLI help exposes legacy and metadata options,
  and the metadata smoke reaches a typed offline/cache failure without network.
- Completed public-beta re-audit 1 with seven individual files and no bundle.
  Oracle verified the candidate/delta/tree/build/quality/secret evidence,
  reported no RELEASE BLOCKER/SHOULD FIX/OPTIONAL item, and approved a manual
  GitHub pre-release without PyPI.
- Recomputed post-answer canaries: 23/23 source-table entries, 7/7 direct
  attachments, and exact package-input tree equality.

## Preserved RC3 quality evidence

| Gate | Result |
| --- | --- |
| Current Python 3.9.25 pytest | `695 passed, 71 skipped` |
| Current Python 3.12.13 pytest | `695 passed, 71 skipped` |
| Current Python 3.14.3 pytest | `695 passed, 71 skipped` |
| Unmodified baseline Python 3.9.25 pytest | `177 passed, 69 skipped` |
| Unmodified baseline Python 3.14.3 pytest | `177 passed, 69 skipped` |
| `ruff format --check . --no-cache` | PASS, `59 files already formatted` |
| `ruff check . --no-cache` | PASS |
| Python 3.9 strict mypy over package/tests/setup | PASS, 59 source files |
| `git diff --check` | PASS; Git emitted only working-tree LF/CRLF notices |

The 69 inherited skips are caused by the upstream checkout not containing
`tests/reference_outputs/`. The preserved suite adds two explicit live-provider
skips because DigiKey and Mouser credentials are absent. The new checked-in
C2040 golden test is independent of the missing upstream reference directory
and passes.

## Current corrective-RC quality

| Gate | Result |
| --- | --- |
| Python 3.9.25 pytest | `702 passed, 71 skipped` |
| Python 3.12.13 pytest | `702 passed, 71 skipped` |
| Python 3.14.3 pytest | `702 passed, 71 skipped` |
| Ruff format check | PASS, 59 files |
| Ruff lint | PASS |
| Python 3.9 strict mypy | PASS, 59 source files |
| `git diff --check` | PASS |

Focused field-table/manufacturer/overwrite regressions and the complete matrix
pass. The explicit release-fixture subset adds `7 passed`; build, dual-install,
archive-content, worktree-leak, and artifact-secret gates also pass.

The initial focused acceptance probe reported `22 passed, 192 deselected`.
After Oracle's initial audit, the new blocker probes report `8 passed` and the
related Provider/cache/CLI/E2E run reports `280 passed`. Coverage includes all
three Provider live-shaped/raw replay overflow paths, schema-3
online/offline/refresh handling, JSON/CSV child-of-symbol-file collisions, and
no partial output.

## Remaining

- Optional external validation only: credentialed DigiKey/Mouser live calls and
  native Linux process E2E remain the disclosed accepted risks.

## Explicit limitations and risks

- `DIGIKEY_CLIENT_ID`, `DIGIKEY_CLIENT_SECRET`, and `MOUSER_API_KEY` are absent,
  so DigiKey/Mouser live API smoke tests are explicitly skipped. Official-shape
  fixtures and mocked authentication/retry/error tests pass.
- The real OPA333AIDBVR and LM321MF/NOPB examples therefore contain LCSC
  metadata plus EasyEDA CAD, not live DigiKey/Mouser records.
- The distributor-present/CAD-absent example is an explicitly labeled mock;
  a real such part was not verified without distributor credentials.
- Runtime E2E was performed on Windows. POSIX path behavior has deterministic
  unit coverage, but native Linux runtime E2E was not available.
- The upstream golden resource directory remains absent; the extension adds a
  separate, checked-in C2040 compatibility fixture instead of reconstructing
  unspecified upstream resources.

## Oracle status and next action

Oracle CLI 0.16.0 completed the public-beta corrective initial audit through
the browser engine and `--browser-manual-login`. It reported CANARY PASS, no
release blocker, and RELEASE APPROVED; all post-answer canaries matched.
Release-prep re-audit 1 is complete and approved. Preserve the audited package,
runtime, and test hashes while adding only the Oracle answer/disposition and
final canary records. Then commit on `feature/multi-distributor-metadata`, create
annotated tag `v1.1.0b1`, and publish a manual GitHub pre-release. Do not push
the version-changing commit to `master`. The accepted risks remain unchanged:
no credentialed DigiKey/Mouser live run, no native Linux process E2E, and 69
inherited reference-output skips.
