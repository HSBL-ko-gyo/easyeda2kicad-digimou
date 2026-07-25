# Current state

Last updated: 2026-07-26 (Asia/Tokyo)

## Current phase

The post-beta issue sequence is now active on the actual default branch.
Issues #2 and #1 are merged and closed; Issue #4 Phase A and Issue #7 Phase A
are merged while their parent issues remain open. Issue #7 Phase B implements
the intermediate, local-package intake milestone. Issue #5 adds explicit,
project-local library registration after validated CAD generation. These are
not the completion of DigiKey/Ultra Librarian or Mouser/SamacSys service
acquisition.

RC2 remains closed as **CANARY PASS / RELEASE BLOCKED** with its two-re-audit
limit unchanged. RC3 remains preserved as **CANARY PASS / RELEASE APPROVED**.
The subsequent public-beta field-table audit found and fixed runtime issues.
Its distinct corrective RC and release-prep re-audit 1 both passed Oracle with
no release blocker. Version and package/release metadata are prepared for
`1.1.0b1`; only the final doc-only delta, commit/tag, and external publication
gates remain.

## Completed

- Added opt-in `--project PATH --register-project-libraries` registration for
  `sym-lib-table` and `fp-lib-table`, with `${KIPRJMOD}` URIs and nicknames
  derived from the output stem. `--project-relative` alone never registers a
  library or changes a project.
- Added read-only `--dry-run`, exact idempotency, nickname/URI collision
  detection, malformed/ambiguous project rejection, concurrent-change checks,
  fsync-backed temporary siblings, atomic replacement, and cross-table
  rollback. The `.kicad_pro` file is never modified.
- Retargeted imported native symbols to the installed footprint-library
  nickname after verifying one exact Footprint property. Missing or duplicate
  Footprint properties now fail closed before output.
- Verified a disposable KiCad 10 project end to end: the registered symbol
  appeared in the symbol chooser with pins 1/2, its `parts:SYNTH_FP` footprint
  resolved with pads 1/2 and courtyard, and the project-relative WRL loaded,
  centered, and rotated in 3D Viewer. KiCad CLI 7/9/10 parsed and rendered the
  registered symbol and footprint; KiCad CLI 10 also exported the schematic
  and rendered the PCB. No user-owned project was used or modified.
- Added a fail-closed local ZIP intake path for native KiCad packages using
  `--cad-package`, exact `--manufacturer`/`--mpn`, and explicit
  `--cad-source digikey|mouser`. Versioned Ultra Librarian and SamacSys adapters
  keep distributor, delivery partner, and model creator provenance separate.
- Added defensive archive limits and path/link/collision/nested-archive
  rejection, package-evidenced exact identity, unambiguous symbol/footprint/3D
  selection, pin/pad verification, portable `${KIPRJMOD}` model links, and
  staged atomic installation with concurrent-change detection and rollback.
- Added synthetic provider-layout fixtures only; no provider package, private
  response, credential, token, cookie, or secret-bearing URL is checked in.
- Verified the synthetic local-package output in a disposable KiCad 10 project:
  Symbol Editor showed both pins, Footprint Editor showed pads 1/2 plus the
  outline and courtyard, and 3D Viewer loaded and rotated the centered WRL
  model. No user-owned project was used or modified.
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

- DigiKey/Ultra Librarian and Mouser/SamacSys service discovery/handoff,
  user-owned real-package intake through the completed registration path, and
  real-package KiCad GUI verification remain required before Issue #7 can
  close.
- Credentialed DigiKey/Mouser live calls and native Linux process E2E remain
  disclosed external validation gaps.

## Explicit limitations and risks

- `DIGIKEY_CLIENT_ID`, `DIGIKEY_CLIENT_SECRET`, and `MOUSER_API_KEY` are absent,
  so DigiKey/Mouser live API smoke tests are explicitly skipped. Official-shape
  fixtures and mocked authentication/retry/error tests pass.
- The real OPA333AIDBVR and LM321MF/NOPB examples therefore contain LCSC
  metadata plus EasyEDA CAD, not live DigiKey/Mouser records.
- The distributor-present/CAD-absent example is an explicitly labeled mock;
  a real such part was not verified without distributor credentials.
- The local package importer has synthetic-layout, KiCad 7/9/10 CLI, and
  disposable KiCad 10 GUI coverage, but it does not scrape or automate Ultra
  Librarian/SamacSys websites and does not claim service download support.
  Real provider packages are intentionally not committed, and real-package GUI
  verification remains part of the later service phases.
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
