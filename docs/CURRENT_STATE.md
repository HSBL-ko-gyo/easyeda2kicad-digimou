# Current state

Last updated: 2026-07-30 (Asia/Tokyo)

## Current phase

The post-beta issue sequence is active on the actual default branch. Issues #1,
#2, #3, #6, and #9 are merged and closed. Issue #4 Phase B now replaces the
README with the verified end-to-end user workflow and completes the planned
documentation work. Issue #7 Phase B implements the intermediate,
local-package intake milestone. Issue #5 adds explicit, project-local library
registration after validated CAD generation. Issue #7 Phase C completes the
DigiKey/Ultra Librarian real-service path through official manual download,
intake, registration, and KiCad CLI/GUI validation; Phase D provides the
policy-safe Mouser/SamacSys handoff infrastructure. Phase E implements
deterministic selection among verified EasyEDA CAD and fully validated local
provider packages. Mouser real-package proof and final multi-source live
completion remain outstanding. Issue #8 has its credentialed live-test
infrastructure but remains open until both provider runs pass.

The `1.1.0b2` release resolved Issue #11's install-time collision.
Distribution `easyeda2kicad-digimou`, command `easyeda2kicad-digimou`, and
Python package `easyeda2kicad_digimou` no longer overwrite upstream's
`easyeda2kicad` files or command. Generated KiCad library naming and the legacy
CLI/output contract remain unchanged.

Issue #27 removes the former `digikey -> ultralibrarian` assumption. DigiKey
CAD discovery now reports the actual product-specific manufacturer/provider
links, safely inspects the exact public model page when the API media response
has no CAD links, and supports hash-bound partial intake of a manufacturer
KiCad footprint plus STEP/WRL with an explicit missing-symbol result.

The `1.1.0b3` candidate adds three post-b2 improvements. The default-branch
README monitor checks public CLI changes and production paths, and can open a
bounded deduplicated follow-up issue without republishing raw commit subjects
or paths. Automatic CAD selection now continues from missing or invalid
EasyEDA artifacts to product-specific DigiKey and Mouser discovery, including
when those distributors were not selected as metadata providers; one source
must advertise every missing artifact kind. Missing or rejected provider API
credentials now produce actionable human output naming the exact environment
variables and official setup URLs without prompting for, echoing, or
persisting secrets, and all human log handlers redact configured values.

Historical RC2 remains closed as **CANARY PASS / RELEASE BLOCKED**, RC3 remains
preserved as **CANARY PASS / RELEASE APPROVED**, and the public-beta
field-table/release-prep cycle remains preserved as **RELEASE READY** for b1.
Those approvals are not reused for `1.1.0b3`; the b3 candidate receives its own
release-candidate validation and audit record before publication.

## Completed

- Added the policy-safe credential-free capability result for DigiKey and
  Mouser metadata. When user credentials are absent, the CLI performs no
  product-page request or scraping and reports `GUEST_LOOKUP_UNSUPPORTED`
  rather than `NOT_FOUND`, with a sanitized official credential setup URL.
  Authenticated official APIs remain preferred. `--require-providers` makes
  missing selected-provider records fail after requested manifests are written;
  the established optional `PARTIAL`/status-0 behavior remains the default.
- Added a same-command `JlcpcbResolution` for every exact-MPN metadata
  acquisition. The anonymous public LCSC/JLCPCB catalogue lookup now runs
  independently of metadata-provider and CAD-source selection, while explicit
  legacy `--lcsc_id` behavior remains unchanged.
- Added fixed `JLCPCB_PART_FOUND`, `MANUAL_GLOBAL_SOURCING_REQUIRED`,
  `JLCPCB_LOOKUP_FAILED`, `JLCPCB_IDENTITY_AMBIGUOUS`, and
  `JLCPCB_IDENTITY_CONFLICT` states. A canonical C-number remains FOUND at
  stock zero; lookup failures, ambiguity, and conflicts never become false
  no-match results.
- Added separate JLCPCB/LCSC number, check time, stock, cache state, manual
  action, and sanitized exact DigiKey/Mouser sourcing-candidate fields to JSON
  and generic CSV. Part-number cells contain only a canonical C-number or an
  empty string. The native KiCad compatibility field remains `LCSC Part`;
  sourcing status and sales data remain Manifest-only.
- Added product-specific DigiKey CAD discovery for explicit
  `--cad-source digikey`. Relevant Product Information V4 `MediaLinks` are
  classified as manufacturer, Ultra Librarian, SnapMagic, SamacSys, or another
  interactive source; DigiKey remains the distributor and is not treated as a
  delivery-partner alias.
- When the exact authenticated record has no relevant CAD media, the source may
  make one credential-free, cookie-free GET of the canonical numeric DigiKey
  model page. Only exact-full-MPN anchors with explicit symbol, footprint, or
  3D labels are accepted. Challenge/unrecognized pages and transport failures
  preserve an actionable model-page URL without claiming a provider.
- Added manifest `available_sources` and `missing_artifacts` diagnostics.
  Multiple providers remain separate, unsupported interactive sources are
  explicit, and unsafe/malformed/ambiguous URLs still fail closed.
- Added the hash-bound `manufacturer-kicad` adapter for a unique native KiCad
  footprint plus STEP/STP or WRL without a symbol. It installs and hashes the
  verified partial artifacts, rewrites the portable 3D reference, and reports
  `CAD_PARTIAL` with `SYMBOL_UNAVAILABLE` instead of inventing a symbol.
- Added typed `CAD_AUTH_REQUIRED` and `CAD_DOWNLOAD_UNAVAILABLE` DigiKey
  outcomes, credential-safe CLI handoff logging, unsafe/ambiguous URL rejection,
  and tests proving OAuth/media requests do not place credentials in URLs or
  retain raw CAD-discovery responses.
- Reconfirmed on 2026-07-29 that `Analog Devices Inc. / AD5314BRM` has no
  LCSC/EasyEDA CAD result while its public DigiKey-linked Ultra Librarian page
  advertises symbol, footprint, KiCad v6+, and STEP availability. The public
  model page permitted a guest download; its completion dialog showed two
  guest downloads remaining that day. API metadata lookup still requires
  user-owned DigiKey developer credentials.
- Completed the credentialed AD5314BRM live discovery smoke with one OAuth,
  exact lookup, and `Media` request. The API returned no recognized model media,
  so the then-current adapter used the exact official product-page handoff
  without retaining a raw response, token, credential, or secret-bearing URL.
  Issue #27 now derives the canonical numeric model-page handoff instead.
- Downloaded the unmodified guest KiCad v6+ plus STEP package after owner
  approval of DigiKey's Model Download Agreement. The ZIP contains five
  entries, stays within all archive limits, and is not committed or
  redistributed.
- Added strict `--cad-package-evidence` support for official packages that omit
  provider/manufacturer fields. The sanitized schema binds exact source,
  delivery partner, manufacturer/full MPN, official product/model URLs, UTC
  retrieval time, and package SHA-256. Unknown fields, unsafe URLs, identity or
  format mismatches, and hash mismatches fail closed.
- Added Ultra Librarian direct KiCad-v6 layout version 2 recognition. A
  hash-bound receipt never replaces native part evidence: the symbol must
  contain at least two exact full-MPN signals. Missing Manufacturer/MPN
  properties are then added from the receipt, while conflicting non-empty
  values are rejected.
- Imported the real AD5314BRM package twice into a disposable project with
  byte-identical idempotent results, registered its libraries, rewrote the STEP
  path portably, and parsed/rendered the real symbol and selected footprint
  successfully with KiCad CLI 7, 9, and 10. The provider's three footprint
  variants share one internal name; the symbol-referenced basename selects
  exactly the unsuffixed file and duplicate exact basenames remain ambiguous.
- Completed the real-package KiCad 10 GUI validation in the same disposable
  project: the exact AD5314BRM symbol and all ten pins, the selected
  `RM_10_ADI` footprint's ten pads and courtyard, and STEP geometry/alignment
  were confirmed. No user-owned project was used or modified.
- Added Mouser Search API V2 exact Product Detail handoff discovery for
  explicit `--cad-source mouser`. The source revalidates exact manufacturer and
  full MPN, accepts only a sanitized official `mouser.com` Product Detail URL,
  reports `CAD_MANUAL_DOWNLOAD_REQUIRED`, and never fetches the returned page
  or falls back to EasyEDA.
- Kept Mouser as distributor, SamacSys as delivery partner, and the
  package-proven model creator as separate provenance roles. SamacSys automated
  search, login, request, and download remain deliberately unimplemented under
  the current service terms.
- Mouser API metadata and CAD handoff lookups are live-only because the current
  API terms prohibit caching or storing API content. The adapter does not
  retain its raw response, service orchestration writes neither raw nor
  normalized Mouser cache entries, and offline mode performs no Mouser request.
- Reconfirmed on 2026-07-26 that `Rectron / FM220A-W` had no exact public LCSC
  match. Its official Mouser page exposed the ECAD/Library Loader flow but
  labelled the action “Build or request PCB Symbol, Footprint or Model”; an
  already downloadable package was not proven. Per the Phase D plan, no
  alternative candidate was selected. Credential- and package-gated smokes
  cover the remaining checks without retaining responses, credentials, or
  provider packages.
- Added deterministic `--cad-source auto` selection with the fixed priority
  verified EasyEDA, a validated DigiKey-linked package, then validated
  Mouser/SamacSys package. A provider landing URL remains an action-only
  handoff and is never treated as an acquired package.
- Added repeatable, source-labelled `--cad-candidate SOURCE=ZIP` and optional
  `--cad-candidate-evidence SOURCE=JSON` inputs. Every candidate completes
  archive, exact manufacturer/full-MPN, KiCad syntax, pin/pad, footprint, and
  3D validation before selection or output.
- Added fail-closed material comparison across acquired packages. Different
  pin/pad sets, footprint package, or primary 3D link return typed
  `CAD_SOURCE_CONFLICT` and produce no CAD output or source lock.
- Added an atomic, portable source lock containing only exact identity,
  selected provider source, and package SHA-256. Existing locks reproduce the
  same content even if source availability later changes; archive content is
  rehashed immediately before installation, and locked local packages rebuild
  offline without a provider request.
- Kept explicit DigiKey and Mouser selections as strict no-fallback paths.
  Auto-selected package manifests retain the selected `cad.source`, separated
  distributor/delivery-partner/model-creator provenance, package hash, and
  artifact hashes.
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

## Issue #6 quality evidence

| Gate | Result |
| --- | --- |
| Focused JLCPCB/metadata/CLI/legacy tests | `292 passed` |
| Full Python 3.12.13 pytest | `876 passed, 75 skipped` |
| Ruff format check | PASS, 314 files |
| Ruff lint | PASS |
| Strict mypy over package/tests/setup | PASS, 82 source files |
| Package build and `twine check` | PASS, wheel and sdist |
| Secret, secret-URL, and machine-path scan | PASS |
| `git diff --check` | PASS; Git emitted only LF/CRLF notices |

The credential-free public JLCPCB/LCSC path was also exercised live with exact
identity `Texas Instruments / OPA333AIDBVR`. It returned
`JLCPCB_PART_FOUND`, canonical `C30878`, and cache state `LIVE`. Explicit
`--cad-source digikey` remained `CAD_NOT_ACQUIRED`; it did not fall back to
EasyEDA. The sanitized temporary manifest passed the secret/path scan and was
removed.

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

## Issue #7 Phase D quality evidence

| Gate | Result |
| --- | --- |
| Mouser/DigiKey/package/docs focused tests | `108 passed, 2 skipped` |
| Python 3.12.13 full pytest | `837 passed, 75 skipped` |
| Ruff format check | PASS, 77 files |
| Ruff lint | PASS |
| Python 3.12 strict mypy | PASS, 77 source files |
| `git diff --check` | PASS |
| Build and Twine check | PASS for sdist and wheel |
| Changed source and unpacked distribution secret/path scan | PASS |

The two focused skips remain deliberate external gates:
`MOUSER_API_KEY` for the single-request official API smoke and
`MOUSER_FM220A_CAD_PACKAGE` for real-package import, project registration, and
KiCad CLI 7/9/10 rendering. A skip is not counted as live success.

## Issue #7 Phase E quality evidence

| Gate | Result |
| --- | --- |
| Auto/package/KiCad/project/docs focused tests | `85 passed` |
| Python 3.12.13 full pytest | `856 passed, 75 skipped` |
| Auto-selected KiCad CLI 7/9/10 parse/render | PASS, 6 tests |
| Ruff format check | PASS, 81 files |
| Ruff lint | PASS |
| Python 3.12 strict mypy | PASS, 81 source files |
| `git diff --check` | PASS |
| Build and Twine check | PASS for sdist and wheel |
| Changed source and unpacked distribution secret/path scan | PASS |

Synthetic dual-provider fixtures exercise selection, conflict, source-lock,
offline rebuild, package import, disposable-project registration, and KiCad
CLI 7/9/10 rendering. They are not substituted for the still required real
Mouser package and GUI proof.

## Issue #8 live-provider smoke infrastructure

- Added the opt-in `live_provider` marker and an independent
  `--run-live-provider` gate. The ordinary suite skips these tests even if a
  developer shell happens to contain provider credentials.
- Added a manual-only GitHub Actions workflow bound to the `provider-live`
  environment. It uses `contents: read`, one serial job, a ten-minute timeout,
  one API attempt per provider, no schedule, no pull-request trigger, and a
  default-branch-only job condition.
- Fixed the live canaries at `Texas Instruments / OPA333AIDBVR` for DigiKey
  Product Information V4 and `Texas Instruments / LM321MF/NOPB` for Mouser
  Search API V2. Both tests require exact manufacturer/full-MPN identity,
  a normalized record, a well-formed distributor part number, sanitized URLs,
  and compatibility with the normal Manifest path; volatile commercial values
  are not asserted.
- Added strict schema-v1 evidence with an allow list only for commit, UTC,
  provider, requested and normalized non-secret identity, pass/fail/skip, API
  operation/version, safe HTTP status category, failure category, and test-code
  hash. Evidence writes are atomic. Raw responses, credentials, tokens, headers,
  secret URLs, stock, price, and local paths are not accepted fields.
- Added deterministic seeded-canary scanning across stdout, stderr, cache,
  Manifest, and artifact surfaces. The workflow validates evidence against the
  configured secret values without printing those values and requires both
  providers to report `pass` before the job succeeds.

| Gate | Result |
| --- | --- |
| Deterministic live-infrastructure focused tests | `13 passed` |
| Explicit credentialed smoke in this process | `2 skipped` because all three credential variables are absent |
| Python 3.12.13 full pytest | `889 passed, 75 skipped` |
| Workflow YAML and static contract checks | PASS |
| Ruff lint / format | PASS, 125 files |
| Python 3.12 strict mypy | PASS, 84 source files |
| Build and Twine check | PASS for sdist and wheel |
| Changed source and unpacked distribution secret/path scan | PASS |
| Skip-evidence schema validation | PASS, 2 sanitized files; required-pass validator rejected them |

Infrastructure completion is not Issue #8 completion. A post-merge dispatch
must run with protected environment secrets `DIGIKEY_CLIENT_ID`,
`DIGIKEY_CLIENT_SECRET`, and `MOUSER_API_KEY`, and the sanitized artifact must
contain a real pass for both providers. Until that happens, Issue #8 remains
open and documentation must not replace the current unverified Mouser status
with a success claim.

## Issue #3 public metadata capability

The official DigiKey Product Information V4 and Mouser Search API paths remain
credentialed. The CLI now detects absent user credentials locally, makes no
provider-site request, and emits `GUEST_LOOKUP_UNSUPPORTED` with a sanitized
setup URL. It never labels that capability boundary as a product miss.
`--require-providers` is an explicit strictness switch; without it, the existing
optional-provider `PARTIAL`/status-0 behavior is unchanged.

| Gate | Result |
| --- | --- |
| Guest/CLI/provider/CAD/docs focused tests | `222 passed` |
| Python 3.12.13 full pytest | `895 passed, 75 skipped` |
| Ruff lint / format | PASS, 85 files |
| Python 3.12 strict mypy | PASS, 85 source files |
| Build and Twine check | PASS for sdist and wheel |
| Changed source and distribution secret/path scan | PASS |

## Issue #9 Phase A machine JSON v1

- Added the additive `acquire --machine-json` subcommand while preserving the
  root legacy CLI and its version banner/output/exit behavior.
- stdout is one UTF-8 schema-v1 JSON document; progress is stderr-only and the
  writer bypasses CP932 encoding. Machine mode does not prompt, launch KiCad,
  or open a browser.
- The result composes existing provider, CAD, JLCPCB, artifact, and project
  registration models. Artifact/project paths are relative and declare
  `path_base`; installed artifacts include SHA-256.
- Added repeatable `--require-provider`, `--require-cad`,
  `--require-jlcpcb-resolution`, and `--require-project-registration` with
  stable exit codes 0, 2–8, and 70.
- Checked in and packaged `machine-result-v1.schema.json`, with an explicit
  compatibility/versioning policy.

| Gate | Result |
| --- | --- |
| Machine/schema/CP932/offline/failure/security focused tests | `26 passed` |
| Related CLI/CAD/project/legacy focused tests | `190 passed` |
| Python 3.12.13 full pytest | `921 passed, 75 skipped` |
| Ruff lint / format | PASS, 87 files |
| Python 3.12 strict mypy | PASS, 87 source files |
| Build and Twine check | PASS for sdist and wheel |
| Schema present once in sdist and wheel | PASS |
| Changed source and unpacked distribution secret/path scan | PASS |

## Issue #9 Phase B headless discovery and events

- Added `acquire --json-events` with versioned UTF-8 JSON Lines, one request ID,
  monotonic sequence numbers, fixed event types, and a final `completed` event
  containing the Phase A result. Invalid requests, provider/manual-action
  failures, interruptions, and bounded internal failures retain a typed final
  result.
- Added JSON-only `capabilities`, `inspect-project`, `plan-acquire`, and
  `verify-artifacts` commands. Capability/plan output exposes authentication
  state only as booleans; it never returns secret names or values.
- Project inspection and acquisition planning are read-only. Planned project
  registration returns `${KIPRJMOD}` changes without creating or modifying
  tables. Artifact verification rejects absolute/traversal/symlink paths and
  compares SHA-256.
- Added closed event/headless schemas and an independent standard-library hash
  verification example. Cached semantic reruns retain the same artifact hashes
  and result after excluding the per-invocation request ID.

| Gate | Result |
| --- | --- |
| Event/read-only/schema/security focused tests | `22 passed` |
| Related machine/project/doc focused tests | `88 passed` |
| Python 3.12.13 full pytest | `943 passed, 75 skipped` |
| Real offline JSON Lines subprocess | PASS, exit 6 / final `OFFLINE_CACHE_MISS` |
| Ruff lint / format | PASS, 90 files |
| Python 3.12 strict mypy | PASS, 90 source files |
| Build and Twine check | PASS for sdist and wheel |
| Three schemas present once in sdist and wheel | PASS |
| Changed source and distribution secret/path scan | PASS |

## Issue #4 Phase B verified README workflow

- Reorganized the README around the user path: current capabilities,
  account-free quick start, API setup, provider smoke tests, CAD handoff/import,
  project registration, same-command JLCPCB resolution, KiCad verification,
  machine JSON, troubleshooting, and advanced references.
- Replaced ambiguous provider claims with an explicit metadata/CAD boundary.
  DigiKey and Mouser metadata require user-owned credentials; explicit
  distributor CAD sources never fall back to EasyEDA. DigiKey's verified real
  package and the still-outstanding Mouser/SamacSys real-package proof are
  dated separately.
- Documented current-terminal-only PowerShell, cmd.exe, and POSIX credential
  setup, boolean-only presence checks, official account/setup links, and the
  rule that OAuth tokens, raw responses, credentials, cookies, and
  secret-bearing URLs are never copied into project artifacts.
- Added a standard-library provider-manifest checker used by the documented
  smoke workflow. README acceptance tests parse the documented CLI commands,
  validate relative links, exercise the checker, and scan for secrets and
  machine-specific paths.

| Gate | Result |
| --- | --- |
| README/workflow/machine/provider focused tests | `90 passed` |
| Python 3.12.13 full pytest | `958 passed, 75 skipped` |
| Ruff lint / format | PASS |
| Python 3.12 strict mypy | PASS |
| Build and Twine check | PASS for sdist and wheel |
| Changed source and unpacked distribution secret/path scan | PASS |

## Issue #11 distinct install identity and 1.1.0b2 candidate

- Moved all runtime modules to `easyeda2kicad_digimou`; the wheel installs no
  files below upstream's `easyeda2kicad` package.
- Changed the distribution to `easyeda2kicad-digimou` and the sole console
  entry point to `easyeda2kicad-digimou`. No ambiguous upstream command alias is
  installed.
- Added `--version` output that includes the command, `1.1.0b2`, the +DigiMou
  display name, and its unofficial-derivative status.
- Updated current README, machine-contract, architecture, CI, protected live
  workflow, packaging manifest, schemas, and import tests for the new
  namespace.
- Kept the existing default generated library directory/name,
  `${EASYEDA2KICAD}`, legacy C2040 symbol/footprint bytes, normal legacy banner,
  arguments, and exit behavior unchanged.
- Added an explicit wheel co-install regression. The actual upstream `1.0.1`
  wheel and candidate wheel work in both installation orders; uninstalling
  either leaves the other package/module/command working.

| Gate | Result |
| --- | --- |
| Distribution identity/co-install focused tests | `5 passed` |
| Related identity/README/machine/legacy focused tests | `77 passed, 2 gated skips` |
| Python 3.12.13 full pytest | `961 passed, 77 skipped` |
| Ruff lint / format | PASS, 93 files |
| Python 3.12 strict mypy | PASS, 93 source files |
| Build and Twine check | PASS for renamed sdist and wheel |
| Wheel contains only new namespace and entry point | PASS |
| Changed source and unpacked distribution secret/path scan | PASS |

## Remaining

- Mouser/SamacSys exact official Product Detail discovery is implemented, but
  this checkout has not yet completed its credentialed FM220A-W smoke or
  received an owner-exported `MOUSER_FM220A_CAD_PACKAGE`. A real package must
  pass the completed import and project-registration path, KiCad CLI 7/9/10,
  and real KiCad GUI validation before Phase D can complete.
- Phase E selection, conflict handling, and source locking are implemented, but
  final DigiKey plus Mouser real-service E2E remains required before Issue #7
  closes. Fixture-only dual-source evidence does not meet that gate.
- Credentialed Mouser live calls and native Linux process E2E remain disclosed
  external validation gaps.
- Issue #8's protected `provider-live` environment contains the owner-provided
  DigiKey client ID and secret. It still requires an owner-provided
  `MOUSER_API_KEY` and one confirmed DigiKey plus Mouser passing dispatch.
  Skips and infrastructure-only CI are not counted as live success.

## Explicit limitations and risks

- DigiKey credentials are configured only in the owner's environment and its
  exact live smoke now passes. The Mouser live and package tests remain
  credential/package gated and are not counted as successful when skipped.
- The real OPA333AIDBVR and LM321MF/NOPB examples therefore contain LCSC
  metadata plus EasyEDA CAD, not live DigiKey/Mouser records.
- AD5314BRM is now the verified distributor-present/EasyEDA-CAD-absent
  candidate. Its API `Media` response did not expose the CAD model, so the
  implementation uses only the exact API-provided public product URL for the
  manual handoff; guest availability and rate limits may change.
- The local package importer has synthetic-layout, KiCad 7/9/10 CLI, and
  disposable KiCad 10 GUI coverage, but it does not scrape or automate Ultra
  Librarian/SamacSys websites and does not claim service download support.
  Real provider packages are intentionally not committed. The DigiKey real
  package has complete KiCad CLI and symbol/pin/footprint/pad/courtyard/3D GUI
  coverage; the corresponding Mouser real-package proof remains outstanding.
- Runtime E2E was performed on Windows. POSIX path behavior has deterministic
  unit coverage, but native Linux runtime E2E was not available.
- The upstream golden resource directory remains absent; the extension adds a
  separate, checked-in C2040 compatibility fixture instead of reconstructing
  unspecified upstream resources.

## 1.1.0b2 pre-release record

The release was intentionally published without claiming Mouser completion.
Issues #7 and #8 remained open, the README/release notes identified the missing
credentialed package/GUI/live proof, and explicit Mouser CAD did not fall back
to EasyEDA.

No Oracle Pro model was used or requested. `v1.1.0b2` was published only as a
GitHub pre-release with wheel, sdist, release notes, CLI help, and checksums;
it was not published to PyPI.

## 1.1.0b3 pre-release candidate

This candidate keeps the b2 install identity and existing CLI spelling. It adds
no command-line option. Its release delta consists of the README consistency
monitor, artifact-level automatic CAD fallback, actionable provider API
credential guidance, the refreshed README, and the corresponding version and
release documentation.

The local candidate reports `1010 passed, 77 skipped`; Ruff lint/format, strict
mypy, sdist/wheel build, Twine validation, package-content inspection, and an
isolated wheel install all pass. The initial non-Pro Oracle audit passed its
source canary and reported five release blockers plus three should-fix items.
All eight were reproduced and fixed. Re-audit 1 confirmed those corrections
and found one additional parsed-but-empty artifact boundary; that blocker and
the accompanying bounded-monitor recommendation are fixed. Final re-audit 2
confirmed the product blocker resolved and identified that the changed-path
limit still occurred after full subprocess capture. Its exact minimum fix,
which explicitly required no further Oracle review, now streams NUL-delimited
paths, stops at the first over-limit entry, and terminates/reaps Git. A focused
80-test matrix covers fallback, empty electrical artifacts, provenance,
credential-redaction, and monitor boundaries. The remaining release gates are
GitHub CI and CodeQL on the release PR and exact-commit artifact publication
as `v1.1.0b3`. Publish only a GitHub pre-release; do not publish to PyPI.
