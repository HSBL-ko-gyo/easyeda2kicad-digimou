# Design decisions

This is a living record. Implemented decisions remain subject to the independent
Oracle architecture and release-candidate reviews.

## D001 — Preserve a separate legacy execution path

**Status:** Implemented  
**Decision:** Runs using only existing options continue through the existing
validation and `_process_component` flow. Metadata orchestration is activated
only by a new option.  
**Reason:** This is the smallest reliable compatibility boundary: geometry,
control flow, and ordinary legacy output continue through upstream code. A
deliberate cross-path safety correction escapes backslashes, quotes, CR, and LF
in quoted KiCad property keys and values. Legacy input containing those special
characters can therefore be byte-different while becoming syntactically safe.  
**Alternatives:** Route every invocation through `MergedPart`; rejected because
it adds new network/error/normalization behavior to old commands.  
**Compatibility:** No general reserialization or metadata-path behavior is
introduced for existing invocations. A checked-in real C2040 CAD fixture and
baseline-generated symbol/footprint goldens now exercise the legacy CLI with
network access forced to fail. Separate baseline/current runs also produced
byte-identical symbol, footprint, and SVG artifacts from the same CAD payload.

## D002 — Separate distributor metadata from EasyEDA CAD

**Status:** Implemented  
**Decision:** `MetadataProvider` and `CadProvider` are different contracts.
DigiKey/Mouser never return CAD. Existing EasyEDA classes stay in place behind a
thin adapter.  
**Reason:** Prevents product availability from being mistaken for CAD success
and avoids moving stable upstream conversion code.  
**Alternatives:** One provider interface for all data; rejected because most
methods would be invalid for most providers.  
**Compatibility:** Minimal imports/adapters around existing code.

## D003 — Conservative exact-MPN normalization

**Status:** Implemented  
**Decision:** Normalize Unicode/case/whitespace and Unicode dash presentation,
but preserve separator positions and distinguish ASCII `-`, `_`, and `/`. Never
strip suffixes. Require manufacturer equality when supplied. Validate local
identity fields even when the API reports exact results.  
**Reason:** False matches are more harmful than explicit not-found results.  
**Alternatives:** Fuzzy matching, package suffix removal, distributor ranking;
rejected by scope and safety requirements.  
**Compatibility:** New MPN path only.

## D004 — Standard-library HTTP clients with injected transport

**Status:** Implemented  
**Decision:** Use `urllib` and small shared retry helpers.  
**Reason:** Matches upstream dependency policy and supports deterministic tests.  
**Alternatives:** `requests`, distributor SDKs; rejected to avoid runtime
dependencies and opaque credential/cache behavior.  
**Compatibility:** No new install requirement.

## D005 — Provider-scoped metadata cache with 24-hour freshness

**Status:** Implemented  
**Decision:** Store versioned redacted-raw and normalized responses separately
below the existing `.easyeda_cache` root. Online results expire after 24 hours;
offline accepts stale data. `--refresh-metadata` affects metadata only. Schema-v2
generation/hash binding is specified by D018.  
**Reason:** Distributor stock/pricing is volatile and API quotas require caching.
Separation prevents refresh from invalidating CAD.  
**Alternatives:** No cache; rejected for API quota. Indefinite cache; rejected as
misleading for stock/price. Reuse a single EasyEDA JSON file; rejected due schema
and secret-boundary risk.  
**Compatibility:** Existing cache file names and CAD behavior remain untouched.

## D006 — Continue on unavailable distributor credentials

**Status:** Implemented  
**Decision:** A requested distributor with missing/rejected auth yields an
explicit provider error and `PARTIAL` verification while other providers and CAD
continue. Identity ambiguity and explicit MPN mismatch remain fatal.  
**Reason:** CAD generation and available metadata remain useful, while absence
of credentials is not misreported as product absence.  
**Alternatives:** Fail the entire command on any auth error; rejected because it
makes multi-provider enrichment brittle. Silent skip; rejected because it hides
missing data.  
**Compatibility:** New metadata path only.

## D007 — Reuse hidden custom properties for additional KiCad fields

**Status:** Implemented  
**Decision:** Keep native existing properties and add stable metadata through the
exporter's ordered `custom_fields`. Do not add volatile fields. Preserve the
current datasheet unless `--datasheet-link` is explicit.  
**Reason:** This is the narrowest tested change and already handles KiCad schema
versions.  
**Alternatives:** Rewrite symbol S-expressions after export or redesign
`KiSymbolInfo`; rejected as more invasive.  
**Compatibility:** Metadata fields are not added on the legacy path; the quoted
property escaping exception is recorded in D001.

## D008 — Treat manifest CSV as BOM-compatible output

**Status:** Implemented  
**Decision:** JSON contains the complete merged model; CSV repeats stable fields
once per distributor and JSON-encodes nested values.  
**Reason:** The requested CLI names JSON/CSV manifests, and the CSV is directly
usable as a purchasing BOM without adding another near-duplicate option.  
**Alternatives:** Separate `--bom`; deferred unless review finds it necessary.  
**Compatibility:** Additive output only.

## D009 — AGPL-3.0 remains the project license

**Status:** Accepted  
**Decision:** Preserve the upstream `LICENSE`, package classifier, source
notices, and AGPL-3.0 distribution terms. A dated top-level `NOTICE` identifies
the upstream baseline and modification scope; README links it prominently and
source/wheel packaging includes it alongside `LICENSE`.  
**Reason:** The work is a modification of the AGPL-3.0 upstream project.  
**Alternatives:** Relicensing is out of scope and not permitted unilaterally.  
**Compatibility:** No license change.

## D010 — Continue locally when Oracle is unavailable before RC

**Status:** Accepted by explicit user instruction  
**Decision:** Record Oracle failures or stalled sessions and continue normal
implementation. A complete Architecture Review and Release Candidate Audit
remain mandatory before declaring an RC; stop only if Oracle is still
unavailable at that boundary.  
**Reason:** Oracle is an independent review gate, not a reason to discard safe
local progress before the gate can be retried.  
**Alternatives:** Stop immediately on every Oracle failure; superseded by the
user's revised policy. Silently omit the review; rejected.  
**Compatibility:** Process-only decision; no runtime effect.

## D011 — Require part-scoped evidence for inferred manufacturer aliases

**Status:** Implemented  
**Decision:** `--manufacturer` is compared exactly after conservative
normalization. Without that explicit constraint, the service builds an exact
manufacturer evidence set only from EasyEDA CAD and an LCSC catalogue record
reconciled to the same canonical LCSC ID and exact MPN. LCSC prefers the exact
record's `componentBrandEn` display when present. A DigiKey/Mouser record is
published only when its normalized manufacturer equals one of those evidence
values; otherwise it is excluded from merged fields, manifests, BOM rows, and
KiCad properties as `MANUFACTURER_UNVERIFIED`, retained only in a structured
conflict diagnostic, and makes the result `PARTIAL`. The inferred manufacturer
seed, its source, evidence, conflicts, and positive provenance are passed into
the merge and resolved in one pass rather than repaired afterwards.  
**Reason:** Real OPA333 data uses both `TI(德州仪器)` and `Texas Instruments`,
which an exact same-part EasyEDA/LCSC pair can prove. An arbitrary `Acme Devices`
versus `Other Devices` disagreement is not safe purchasing evidence merely
because the MPN text matches.  
**Alternatives:** Accept every exact-MPN distributor result, reject every
differing display string, or use a fuzzy/global alias table; rejected because
the first permits false matches and the latter two either reject proven
same-part aliases or create cross-part equivalence.  
**Compatibility:** New metadata path only. Previously accepted but unproven
external records now become an explicit nonfatal partial diagnostic.

## D012 — Verify identity from CAD payload evidence, not titles

**Status:** Implemented  
**Decision:** Reconcile LCSC ID, MPN, and manufacturer from top-level LCSC fields
and symbol/package `c_para`. Search terms, titles, descriptions, and caller
values are never fallback identity evidence. Contradictory or container-valued
evidence is `INVALID_RESPONSE`.  
**Reason:** Search ranking/title text is not exact identity proof.  
**Compatibility:** Legacy importers are unchanged; the check runs only in
metadata mode.

## D013 — Revalidate normalized cache and partition public locale

**Status:** Implemented  
**Decision:** Cache hits must match provider envelope, raw key, exact MPN,
optional user manufacturer, and distributor ID. DigiKey site/language/currency
are included in canonical cache context.  
**Reason:** Structurally valid wrong-provider data and cross-currency reuse are
unsafe.  
**Compatibility:** Older incompatible metadata entries miss/refetch online;
existing CAD cache layout is unchanged.

## D014 — Count SMD pads as electrical without trusting `is_plated`

**Status:** Implemented  
**Decision:** Pin/pad verification includes SMD pads and plated through-holes,
while excluding non-plated through-hole mechanics.  
**Reason:** EasyEDA uses `is_plated=false` for ordinary SMD pads; filtering only
on that flag made real OPA333 and LM321 CAD appear unparseable.  
**Compatibility:** Verification exists only in metadata mode.

## D015 — Fail an unavailable explicit datasheet selection

**Status:** Implemented  
**Decision:** No `--datasheet-link` preserves the original source value exactly.
An explicitly selected provider must supply `datasheet_url`; product pages are
never substituted.  
**Reason:** Silent fallback would contradict an explicit source choice and blur
datasheet/product URL responsibilities.  
**Compatibility:** Legacy/default behavior is unchanged.

## D016 — Harden public URLs and filesystem output boundaries

**Status:** Implemented in the new RC; the closed RC2 gap remains recorded in D025  
**Decision:** Normalize provider product/datasheet URLs before cache and output,
require valid HTTP(S) authority for public links, strip userinfo/fragments/secret
query parameters, and fail an explicit datasheet that equals its product page.
Prefix formula-active CSV cells with an apostrophe. Reject unsafe CAD-derived
artifact basenames, nested/colliding manifest paths, and project-relative model
paths outside the current project root.  
**Reason:** First-run output must have the same secret boundary as cache hits,
and output paths must be rejected before a CAD or manifest writer can escape or
replace another selected artifact. CSV should be safe to open in ordinary
spreadsheet software without changing the exact JSON model.  
**Release-candidate conformance:** RC2 rejected same-path collisions and
JSON/CSV mutual containment but missed a manifest that was an ancestor of CAD
output. D027 supersedes that behavior in the new RC: same/ancestor manifest
paths fail before persistent output, while a normal manifest child path is
allowed.  
**Compatibility:** The legacy conversion flow is unchanged except that unsafe
CAD-derived footprint/3D filenames now fail closed. Existing valid URLs, public
query parameters, filenames, and in-project paths retain their meaning.

## D017 — Keep CAD verification action-aware and symbol-stable

**Status:** Implemented; KiCad property sink narrowed by D030  
**Decision:** Parse only CAD artifacts required by requested actions and compare
pin/pad sets only when both symbol and footprint are requested. CAD verification
status remains in the Manifest; distributor/auth errors may change the overall
Manifest status but not the existing native symbol properties.  
**Reason:** An unrequested importer must not block an otherwise valid action,
and distributor availability is not a CAD property.  
**Compatibility:** Legacy mode and default Datasheet behavior are unchanged;
combined symbol/footprint metadata runs retain fail-closed pin/pad validation.

## D018 — Bind metadata cache evidence as schema-v2 generations

**Status:** Implemented  
**Decision:** Keep the existing `raw.json` path but label its stored payload
`redacted_raw`. Bind it to `normalized.json` with a shared random generation ID,
canonical request, timestamp, and SHA-256 of the stored redacted-raw data.
Normalized reads require and validate both files; writes prepare both temporary
files before either replacement.  
**Reason:** A normalized entry without its matching evidence must not be trusted,
and interrupted or concurrent two-file publication must fail closed.  
**Compatibility:** The cache schema is bumped to 2, so schema-v1 metadata misses
and refetches online. Existing CAD cache paths and behavior are unchanged.

## D019 — Reject non-string distributor identity evidence

**Status:** Implemented  
**Decision:** Provider, MPN, manufacturer, distributor/LCSC part number, and
EasyEDA component identity values must be non-empty strings when present.
Boolean, numeric, list, and object values are invalid rather than stringified.
The common model constructors and deserializers enforce the same rule.  
**Reason:** Permissive `str(value)` conversion could turn malformed API data into
an apparent exact MPN or distributor-ID match.  
**Compatibility:** Valid provider payloads and CLI strings are unchanged;
malformed identity payloads now report `INVALID_RESPONSE`.

## D020 — Normalize presentation-equivalent minus characters in place

**Status:** Implemented  
**Decision:** Map documented presentation-equivalent minus characters,
including U+2212 MINUS SIGN, to ASCII hyphen in addition to Unicode `Pd`
characters. Never delete or move separators, and continue distinguishing `-`,
`_`, and `/`.  
**Reason:** Ordering codes copied from PDFs commonly contain U+2212, whose
Unicode category is `Sm` rather than `Pd`.  
**Compatibility:** Visually equivalent dash/minus forms compare consistently;
separator position and semantically different separators remain exact.

## D021 — Keep LCSC metadata lookups catalogue-only

**Status:** Implemented  
**Decision:** `LcscProvider.get_part_by_distributor_id` resolves a canonical
`C[1-9][0-9]*` identifier only through the anonymous JLCPCB catalogue and stores
the fetched official catalogue pages as raw cache evidence. Production uses a
dedicated `JlcpcbCatalogueClient`; the old `EasyedaApi` catalogue method is a
forwarding compatibility facade. `LcscProvider` never calls the EasyEDA CAD
transport, and `EasyedaProvider` is the sole CAD caller. Metadata refresh can
therefore refetch LCSC catalogue data without bypassing or touching CAD cache.  
**Reason:** Reusing CAD as an LCSC metadata shortcut mixed provider authority and
made `--refresh-metadata` capable of causing an undocumented CAD request.  
**Compatibility:** Distributor metadata becomes consistently catalogue-backed;
the legacy EasyEDA conversion path is unchanged.

## D022 — Select distributor packaging independently of volatile sales data

**Status:** Implemented  
**Decision:** After exact identity validation, choose the lexically smallest
non-empty DigiKey or Mouser distributor part number and use product URL only as
a stable fallback/tie-breaker. MOQ, stock, and price remain attached to the
chosen record but never determine which record feeds hidden KiCad fields.  
**Reason:** Sales values can change between cache refreshes; allowing them to
select a packaging variation made stable symbol properties change without an
identity change.  
**Compatibility:** Manifest sales data remains available. Selection among
same-identity packaging variations is deterministic and cache-refresh stable.

## D023 — Preserve safe structured provider diagnostics

**Status:** Implemented  
**Decision:** Keep `provider_errors` as the stable provider-to-code mapping for
compatibility and add `provider_diagnostics` with only `code`, optional internal
operation, and optional numeric HTTP status. Emit both in JSON and compact-JSON
CSV columns and show the safe context in default warnings. Never retain request
URLs, headers, bodies, or exception messages.  
**Reason:** Oracle S2 correctly observed that reducing every `ProviderError` to
its category discarded useful credential-safe context even after warnings were
made visible.  
**Alternatives:** Replace `provider_errors` values with objects; rejected because
it would break existing consumers and tests. Preserve raw exception text;
rejected because Mouser keys and authorization data can occur there.  
**Compatibility:** Additive manifest field/CSV column only; the existing code
mapping and symbol projection remain unchanged.

## D024 — Treat secret-bearing suffixes as credential fields

**Status:** Implemented during the final security audit  
**Decision:** The metadata cache and provider compatibility canonicalizer remove
credential keys whose punctuation-insensitive names end in a known secret
suffix, including prefixed camelCase forms such as `oauthAccessToken`,
`myClientSecret`, and `databasePassword`. Presentation fields such as
`accessTokenExpiresAt` and `tokenizer` remain because they do not end in a
secret suffix. The same rule is applied to URL query keys.  
**Reason:** Official provider code does not cache OAuth token responses, but the
general recursive-redaction contract must remain safe for injected transports
and future official response shapes. Exact-name detection alone left a
defense-in-depth gap.  
**Alternatives:** Depend only on current provider call paths; rejected because
it weakens the documented cache boundary. Remove any key containing the word
`token`; rejected because it would discard unrelated fields such as
`tokenizer` and expiry metadata.  
**Compatibility:** Only credential-shaped request/cache fields are removed.
Public cache context, provider output models, legacy CAD cache, and CLI behavior
are unchanged. Regression tests cover both removal and non-secret retention.

## Oracle Architecture Review disposition — 2026-07-22

The complete Oracle answer is stored in
`docs/oracle/architecture_review.md`. B1's alias ambiguity was separately
consulted in `docs/oracle/consultations/001-manufacturer-alias-identity.md`.
Oracle advice was checked against code and tests rather than treated as an
authority by itself.

### BLOCKER

| Finding | Decision and evidence |
| --- | --- |
| B1 cross-provider manufacturer false match | **Adopted, narrowed by consultation.** D011 requires exact part-scoped EasyEDA/LCSC evidence and excludes unverified records from every publication surface. |
| B2 DigiKey incomplete search | **Adopted for result-count truncation.** Required counts and returned collections are checked, so declared-but-unreturned results fail closed as `AMBIGUOUS/search-truncated`. RC2 later reopened malformed-candidate completeness as RB-RC2-1; D026 resolves it in the new RC without reopening the closed RC2 audit. |
| B3 Mouser truncation | **Adopted for ordinary count/list disagreement.** `SearchResults` and a non-negative count are mandatory and ordinary disagreement fails closed. RC2 later found dropped malformed candidates and zero-count missing/null `Parts`; D026 resolves both in the new RC. |
| B4 LCSC/CAD responsibility | **Adopted.** D021 uses a dedicated anonymous catalogue client, stores official catalogue pages, leaves only a compatibility facade on `EasyedaApi`, and keeps `EasyedaProvider` as sole CAD caller. |
| B5 normalized cache without raw binding | **Adopted.** D018 schema-v2 generations bind `redacted_raw` and normalized envelopes by canonical request, generation ID, timestamp, and SHA-256. |
| B6 non-string identities | **Adopted.** D019 rejects bool/numeric/container identity evidence at provider and model boundaries. |
| B7 manifest overwrites CAD artifacts | **Adopted in the new RC.** RC2 covered same-path and JSON/CSV containment but missed manifest-as-ancestor; D027 adds that preflight while allowing a valid manifest child path. |
| B8 legacy release evidence | **Mostly adopted; Linux runtime classified AR-RC2-2.** A real C2040 fixture and baseline-generated goldens are checked in; baseline/current Python 3.9 plus current-Python Windows runs cover bytes, stdout, stderr, exit, and no-network behavior. Native Linux execution was unavailable, while POSIX in-tree/out-of-tree semantics have deterministic tests. The final RC audit accepted this as a disclosed risk. |
| B9 AGPL modification notice | **Adopted.** D009 adds the dated baseline/scope notice prominently and packages `NOTICE` with `LICENSE`. |

### SHOULD FIX

| Finding | Decision and evidence |
| --- | --- |
| S1 unstable symbol verification/distributor selection | **Adopted.** D017 makes the symbol status CAD-only; D022 makes DigiKey and Mouser selection independent of MOQ/stock/price. |
| S2 invisible/lossy provider errors | **Adopted.** Warnings are emitted by default and D023 adds safe structured operation/status diagnostics without replacing compatibility codes. |
| S3 corrupt offline CAD cache category | **Adopted.** Corrupt cache remains `CACHE_CORRUPT` and never attempts network offline. |
| S4 explicit datasheet validation | **Adopted.** D015/D016 require public HTTP(S) and reject normalized product-page equivalents. |
| S5 project-relative path handling | **Adopted.** Resolved in-project paths work; out-of-tree and Windows cross-drive paths fail validation. Windows and POSIX flavors are tested. |
| S6 post-merge manufacturer mutation | **Adopted.** D011 supplies the seed/evidence before a single merge/conflict/provenance pass. |
| S7 unconditional symbol/footprint parsing | **Adopted.** D017 parses only requested actions and compares pins/pads only when both are requested. |
| S8 U+2212 and minus-like characters | **Adopted.** D020 maps a documented presentation-equivalent set in place without removing separators. |
| S9 DigiKey client-ID scrubbing | **Adopted.** Separated, concatenated, and header-name variants are scrubbed in cache and provider utilities. |

### OPTIONAL

| Finding | Decision and evidence |
| --- | --- |
| O1 duplicate cache helpers / wide protocol | **Deferred.** `metadata/cache.py` is the service authority; provider helpers remain compatibility wrappers. Narrowing the public protocol now would add churn without closing a demonstrated correctness gap. |
| O2 models described as immutable | **Adopted as documentation cleanup.** Architecture now calls them validated mutable dataclasses; freezing them was rejected as an invasive refactor. |
| O3 product-image scraping scope | **Not changed.** `get_product_image_url()` predates this baseline extension. The new metadata path never calls it and now uses its own catalogue client; removing inherited behavior would be unrelated upstream churn. |

## D025 — Stop the current RC cycle on the confirmed final-audit blocker

**Status:** Release blocked; human direction required  
**Decision:** Accept RB-RC2-1, SF-RC2-1, and SF-RC2-2 as valid findings after
independent source inspection and read-only reproduction. Correct SF-RC2-2 in
the documentation, but do not change runtime source after the second and final
permitted re-audit. Record AR-RC2-1 through AR-RC2-3 as accepted limitations and
stop this RC cycle with RB-RC2-1 and SF-RC2-1 unresolved.  
**Reason:** Provider probes accepted one valid exact record while silently
discarding another candidate with missing identity; Mouser also accepted zero
results with missing/null `Parts`. A separate path probe accepted a manifest
that was an ancestor of the CAD output directory. Those observations match the
Oracle findings and are release-relevant. Continuing to implement and request a
third re-audit would violate the user-defined maximum.  
**Alternatives:** Ignore the answer because earlier transport attempts used
stale input; rejected because the final session passed the current-source
canary and Codex reproduced its findings. Apply the fixes without stopping;
rejected because this is the exact stop condition specified for the final
re-audit.  
**Compatibility:** No runtime source, test, fixture, or package input changed
after the audited candidate. Only status, contract, decision, and review-log
documents were corrected.

## Oracle Release Candidate Audit disposition — 2026-07-23

The authoritative answer is stored in
`docs/oracle/release_candidate_audit.md`. The browser/manual-login session read
the current 20-file package, matched all source canaries, and reported
**CANARY PASS / RELEASE BLOCKED**. It was the second and final re-audit.

| Finding | Decision and evidence |
| --- | --- |
| RB-RC2-1 malformed candidates can be dropped before exact selection | **Accepted; unresolved RELEASE BLOCKER.** Reproduced for DigiKey and Mouser mixed candidates and for Mouser missing/null `Parts`; source inspection confirms LCSC uses the same skip pattern. A new RC cycle must reject the full response when any returned candidate lacks identity and add mixed-candidate tests for all three providers. |
| SF-RC2-1 manifest may be an ancestor of CAD output | **Accepted; unresolved SHOULD FIX.** A read-only preflight probe returned success for the reverse-containment case. A new RC cycle must reject containment in both directions and verify no partial output. |
| SF-RC2-2 Provider-contract review status was stale | **Accepted and corrected.** `docs/PROVIDER_CONTRACT.md` now records the completed Architecture Review and blocked RC status. |
| AR-RC2-1 credentialed DigiKey/Mouser live APIs not executed | **Accepted risk.** Credentials were absent; no secret-bearing workaround was attempted. Official-shape fixtures and live-test skip evidence remain recorded. |
| AR-RC2-2 native Linux process E2E not executed | **Accepted risk.** Windows runtime and deterministic POSIX path tests do not substitute for a native Linux run. |
| AR-RC2-3 69 inherited reference-output tests skipped | **Accepted risk.** The upstream reference bundle is absent; the checked-in C2040 golden provides focused legacy coverage without fabricating upstream fixtures. |
| OPTIONAL | **No required item.** Future fork/version naming remains a possible later cleanup, not a reason to expand this blocked RC. |

No Oracle finding was rejected in the valid final audit. Earlier stale-input and
input-mismatch attempts were not treated as findings and are documented with
their transport evidence in `docs/oracle/README.md`.

## D026 — Classify raw MPN relevance before complete Provider parsing

**Status:** Implemented and locally verified in the new RC  
**Decision:** All three exact-search adapters use one
`BaseMetadataProvider._normalize_exact_candidates` boundary. It validates the
requested MPN, extracts and normalizes each raw candidate MPN, skips only a
provably different MPN, and requires indeterminate or exact raw candidates to
produce a complete `DistributorRecord` with the same normalized MPN. A failure
in either relevant category is typed `INVALID_RESPONSE/exact-normalize`, never
`NOT_FOUND` or a successful exact result. Mouser also requires a present,
list-valued `Parts` member for zero results.  
**Reason:** Exact uniqueness cannot be inferred after silently losing a
candidate that may be the requested part. Conversely, a raw candidate whose MPN
proves it is a different part cannot affect exact uniqueness and need not make a
valid result fail because an unrelated field is malformed.  
**Cache compatibility:** Cache schema version 3 changes both the canonical
request and cache key. Schema-v2 raw/normalized pairs are not reused, because an
old normalized success may not preserve the fact that a relevant raw candidate
was dropped. New incomplete responses raise before `cache.write`; offline sees
a miss rather than a false success, and refresh propagates the same parse
failure without publishing a pair.  
**Compatibility:** No Provider public method, CLI option, output model, or
manifest/KiCad format changed. LCSC ID/MPN reconciliation remains unchanged and
its existing tests pass.

## D027 — Reject a manifest that occupies a CAD output ancestor

**Status:** Implemented and locally verified in the new RC  
**Decision:** Resolve planned manifest and selected CAD paths before any output.
Reject when the CAD path is equal to or below the manifest path. Do not reject a
manifest that is a regular file below a CAD output directory. Continue rejecting
mutual JSON/CSV containment independently. Delay default output-directory
creation and user output-parent validation until after collision preflight.  
**Reason:** A planned manifest file cannot also serve as the directory required
by a selected CAD output. `Path.resolve()` handles relative paths, `.` and `..`,
and native Windows path equality; `PureWindowsPath` tests fix case-insensitive
Windows semantics without adding a platform skip.  
**Compatibility:** Valid child manifests and adjacent path prefixes are accepted.
No CLI spelling or output format changed. Direct, multi-level, relative-parent,
Windows, child, adjacent-prefix, and no-partial-output tests cover the boundary.

## D028 — Open a new RC cycle without reopening RC2

**Status:** Accepted by explicit user instruction on 2026-07-23  
**Decision:** Preserve RC2's `CANARY PASS / RELEASE BLOCKED` answer, diff,
source canary, and two-re-audit limit unchanged. Start a new candidate from the
verified RC2 source hashes, limited to D026, D027, their tests, and new audit
records. The new cycle permits one initial Oracle audit and at most two
re-audits if needed.  
**Reason:** The user authorized correction of the two confirmed findings while
requiring the previous audit trail to remain closed and immutable.  
**Compatibility:** No commit, stash, push, fork, unrelated refactor, dependency
change, CLI change, API change, or output-format change is authorized.

## D029 — Adopt the new RC initial-audit findings

**Status:** Implemented; Oracle re-audit 1 resolved both blockers  
**Decision:** Preserve the initial new-RC answer as
`docs/oracle/release_candidate_audit_rc3.md`. Adopt `RB-RC3-1` by rejecting
non-finite/overflowing numeric fields at the shared parser boundary, converting
any residual `OverflowError` to the existing typed Provider/cache semantics,
and testing all three Providers plus online/offline/refresh. Adopt `SF-RC3-1`
by treating the symbol output as a file and rejecting a manifest on either
side of its containment relation, while retaining child manifests for CAD
directories. Adopt `DOC-RC3-1` by relabelling the `666 passed` matrix as
historical RC2 evidence. Retain `AR-RC3-1` through `AR-RC3-3` unchanged.  
**Reason:** Direct probes reproduced the exception-class gap and the
child-of-symbol-file path collision. Both are edge cases of the two changes
authorized for this new cycle, not a scope expansion. The document label was
factually stale.  
**Alternatives:** Catch overflow independently in each Provider; rejected
because it would duplicate semantics. Reject every manifest below any selected
CAD path; rejected because a child file is valid inside footprint, 3D, and SVG
directories. Change cache schema again; rejected because schema 3 already
preserves completeness and only exception mapping was missing.  
**Compatibility:** No public API, CLI option, output format, dependency, cache
schema, or Provider/CAD responsibility changed. The full matrix is now
`695 passed, 71 skipped` on Python 3.9, 3.12, and 3.14.

## New RC re-audit 1 disposition — 2026-07-23

The authoritative answer is
`docs/oracle/release_candidate_audit_rc3_reaudit1.md`. Oracle verified all ten
individual attachments and reported **CANARY PASS**, no `RELEASE BLOCKER`, and
`RESOLVED` for `RB-RC3-1`, `SF-RC3-1`, compatibility boundaries, and quality
gates. `AR-RC3-1` through `AR-RC3-3` remain accepted risks.

Oracle's only remaining `SHOULD FIX`, `DOC-RC3-1`, observed that the historical
matrix pointed to the initial `rc3_quality.md` rather than the authoritative
`rc3_reaudit1_quality.md`. The one-line pointer was corrected and all three
full Python suites were rerun successfully. Oracle explicitly stated that this
document-only correction does not require another model re-audit; it requires
regenerated candidate/delta hashes plus diff/apply and secret-document checks.
Those checks are recorded in the final new-RC evidence.

## D030 — Keep distributor metadata out of KiCad Symbol Fields Table columns

**Status:** Implemented; initial public-beta corrective audit approved  
**Decision:** Reuse only the exporter's existing native `Manufacturer`, `MPN`,
`LCSC Part`, and `Datasheet` properties. `build_symbol_fields()` emits no
metadata-mode custom properties. Provider part numbers/URLs, manufacturer
datasheet, package, lifecycle, CAD source/status, provenance, diagnostics,
cache state, and sales data remain in JSON/CSV Manifests.  
**Reason:** A hidden KiCad custom property is still a Symbol Fields Table
column. Real OPA333AIDBVR and LM321MF/NOPB generation showed that the previous
projection added five unwanted columns even with LCSC alone. Both legacy
symbols already contain Manufacturer and MPN, so aliases or additional custom
fields add no stable BOM identity value.  
**Compatibility:** In identical path contexts, audited legacy and metadata
symbols and footprints are byte-identical for both parts. Manifest schemas are
unchanged. Explicit user custom fields remain supported subject to the existing
metadata reserved-name boundary.

## D031 — Verify explicit manufacturer display aliases with same-part evidence

**Status:** Implemented; initial public-beta corrective audit approved  
**Decision:** Continue exact normalized manufacturer matching at every
distributor boundary. Do not require the EasyEDA display label itself to equal
the explicit distributor label when, and only when, a mandatory LCSC lookup
proves the same canonical LCSC ID, exact MPN, and explicit manufacturer.
Unavailable or mismatching evidence is fatal before external Provider calls.  
**Reason:** The required real parts use `TI(德州仪器)` in EasyEDA and
`Texas Instruments` in the LCSC catalogue. No single `--manufacturer` value
could previously satisfy both boundaries. The canonical ID plus exact MPN and
exact LCSC manufacturer prove the display alias without a fuzzy/global table.  
**Alternatives:** Omit `--manufacturer`; rejected because the public-beta audit
explicitly requires that CLI path. Accept every CAD display disagreement;
rejected because MPN text need not be globally unique and would weaken
fail-closed identity.  
**Compatibility:** MPN and LCSC-ID reconciliation are unchanged. The explicit
manufacturer remains the merged/Manifest identity. The existing non-empty CAD
Manufacturer property is preserved with a warning rather than overwritten;
non-empty MPN or LCSC property conflicts still fail.

## D032 — Use the serialized KiCad symbol ID for overwrite lookup

**Status:** Implemented; initial public-beta corrective audit approved  
**Decision:** Apply the existing `sanitize_fields()` transformation to the
component name before both symbol-library lookup/replacement and sub-unit
integration.  
**Reason:** KiCad serialized `LM321MF/NOPB` as `LM321MF_NOPB`, while the
overwrite helper searched for the unsanitized name and appended another symbol
on every run. The same identifier must govern detection and writing.  
**Compatibility:** Names without spaces, slash, or colon are unchanged.
Focused and real-output tests show one root symbol and byte-identical repeated
`--overwrite` output for OPA333AIDBVR and LM321MF/NOPB.

## D033 — Open a distinct public-beta corrective RC cycle

**Status:** Accepted by the public-beta release instruction on 2026-07-23  
**Decision:** Preserve the approved RC3 candidate, canary, and Oracle answer as
historical evidence. Because the field-table audit required runtime changes,
create a new candidate/source canary, rerun the three-Python quality matrix, and
obtain a new Oracle browser/manual-login Release Candidate audit before any
version/tag/GitHub publication work.  
**Reason:** The approved RC3 cannot authorize source that it did not review.
The public-beta instructions explicitly make a fresh RC mandatory after a
runtime correction.  
**Compatibility:** The initial corrective audit reported CANARY PASS and no
release blocker. Release preparation then changed version/package metadata, so
the revised tag candidate requires re-audit 1 before commit, tag, fork, release,
or any other publication. PyPI publication remains excluded.

## Public-beta corrective initial-audit disposition — 2026-07-23

The authoritative answer is
`docs/oracle/release_candidate_audit_beta1.md`. Oracle received ten individual
current files with `bundled: null`, verified both candidate hashes and every
source canary, and reported **CANARY PASS / no RELEASE BLOCKER / RELEASE
APPROVED**. Codex then recomputed the direct-attachment canary 10/10 and the
complete source table 17/17.

| Finding | Decision and evidence |
| --- | --- |
| `B1-FT-01` / `B1-FT-02` | **RESOLVED.** Native-only KiCad projection and complete Manifest-only distributor metadata match code, tests, and real artifact evidence. |
| `B1-MAN-01` | **RESOLVED.** The part-scoped LCSC proof remains mandatory and fail-closed before external Provider calls. |
| `B1-ID-01` | **RESOLVED.** Empty/equivalent native values are reconciled; nonempty Manufacturer is preserved; MPN/LCSC conflicts fail before export. |
| `B1-SYM-01` | **RESOLVED.** Sanitized lookup/write identity prevents slash-bearing duplicate symbols. |
| `B1-BYTE-01` | **RESOLVED.** OPA333AIDBVR and LM321MF/NOPB legacy/metadata artifacts and repeat runs match byte-for-byte. |
| `B1-COMP-01` / `B1-QA-01` | **RESOLVED.** Scope, compatibility, secrets, and the 702/71 matrix passed. |
| `B1-AR-01` through `B1-AR-03` | **Accepted risks retained.** |
| SHOULD FIX / OPTIONAL | None. |

No Oracle finding was rejected. This approval establishes the field-table
runtime boundary. It does not silently approve later version/package/release
metadata changes; those are placed in the revised candidate for re-audit 1.

## D034 — Version the additive derivative as 1.1.0b1

**Status:** Implemented; revised candidate requires re-audit 1  
**Decision:** Change the single package version source from stable `1.0.1` to
PEP 440 version `1.1.0b1` and use annotated tag `v1.1.0b1`. Keep the Python
distribution name, import package, console command, CLI options, public API, and
legacy formats named `easyeda2kicad`. Use `easyeda2kicad +DigiMou` only as the
public display name and `easyeda2kicad-digimou` as the GitHub repository slug.
**Reason:** A `1.0.1b1` prerelease sorts before the already released `1.0.1`
stable version. Exact-MPN multi-distributor metadata is an additive feature
appropriate for the next minor beta; renaming internal/public Python surfaces
would add compatibility risk without helping the first beta.
**Compatibility:** Setup metadata and the release URL change, but dependency
requirements, entrypoint, import paths, and runtime behavior do not.

## D035 — Publish the first beta only as a GitHub pre-release

**Status:** Prepared; publication awaits re-audit and final commit/tag gates  
**Decision:** Build sdist, wheel, release notes, CLI help, and checksums from an
external clean snapshot; publish only through a GitHub fork and pre-release.
Do not upload to PyPI. Push the existing feature branch rather than upstream
`master`, and create the annotated tag only after the audited tree is committed.
**Reason:** The user explicitly excluded PyPI and required fork-network
preservation. The inherited upstream workflow publishes only on a `master`
branch push that changes `_version.py`; the controlled beta flow does neither.
**Compatibility:** Build/cache/venv/output directories remain ignored and are
not committed. The release assets contain LICENSE, NOTICE, and all package
modules, while excluding tests, caches, Oracle material, and credentials.

## Public-beta release-prep re-audit 1 disposition — 2026-07-23

The authoritative answer is
`docs/oracle/release_candidate_audit_beta1_reaudit1.md`. Oracle received seven
individual current files with `bundled: null`, verified the 74-path candidate,
12-path release-prep delta, revised source tree, direct hashes, protected
runtime/test hashes, build inputs, and quality/artifact evidence, and reported
**CANARY PASS / no RELEASE BLOCKER / no SHOULD FIX / RELEASE READY**.

| Finding | Decision and evidence |
| --- | --- |
| `B1-RA1-CAN-01` | **RESOLVED.** Candidate, delta, source tree, attachment hashes, and clean apply all matched. |
| Initial `B1-*` runtime findings | **RESOLVED.** Protected runtime and focused test hashes remained unchanged. |
| `B1-RA1-VERSION-01` | **RESOLVED.** `1.1.0b1`/`v1.1.0b1` is valid and internal Python identities remain unchanged. |
| `B1-RA1-DOC-01` | **RESOLVED.** Attribution, disclaimer, behavior, credentials, Manifest/KiCad boundary, and GitHub-only publication are explicit. |
| `B1-RA1-ISSUE-01` | **RESOLVED.** Required debug fields and safe security-reporting boundaries are present. |
| `B1-RA1-ART-01` / `B1-QA-01` | **RESOLVED.** Build, dual install, content, checksum, quality, and secret evidence matched. |
| `B1-RA1-PUB-01` | **Adopted operational condition.** Push only `feature/multi-distributor-metadata` and annotated tag `v1.1.0b1`; do not push the version-changing commit to `master`. |
| `B1-AR-01` through `B1-AR-03` | **Accepted risks retained.** |
| RELEASE BLOCKER / SHOULD FIX / OPTIONAL | None. |

Codex recomputed the post-answer hash table 23/23, direct attachments 7/7,
and package-input tree equality. No Oracle finding was rejected and no second
re-audit is required.

## D036 — Keep the version-changing commit off master

**Status:** Mandatory release operation  
**Decision:** Push the existing `feature/multi-distributor-metadata` branch,
then push the already-created annotated `v1.1.0b1` tag and create the GitHub
pre-release manually. Never push the version-changing commit to `master` as
part of this beta.
**Reason:** The inherited upstream workflow triggers only on a `master` push
that changes `_version.py`; before the tag exists it would create its own tag
and release and attempt PyPI publication. Feature-branch and annotated-tag
pushes do not match that trigger. Once the tag exists, the workflow's own
tag-existence check would stop before build/publish, but the audited plan avoids
the trigger entirely.
**Compatibility:** No workflow source change is required. A future plan to
merge this version change to `master` requires a separate publication-workflow
assessment.

## D037 — Separate +DigiMou's install identity before the second beta

**Status:** Implemented; supersedes D034 only for install-time identity
**Decision:** Starting with `1.1.0b2`, use distribution
`easyeda2kicad-digimou`, command `easyeda2kicad-digimou`, Python package
`easyeda2kicad_digimou`, and module invocation
`python -m easyeda2kicad_digimou`. Do not install an `easyeda2kicad` package or
console-script alias. Keep the existing CLI arguments, default generated
library name/path, `${EASYEDA2KICAD}`, generator compatibility fields, KiCad
artifacts, and exit behavior.
**Reason:** `1.1.0b1` reused upstream's distribution, import package, and
console command. Installation order could overwrite either implementation and
uninstalling one could remove the other's files. A repository display name
alone does not provide safe package identity.
**Compatibility:** The import and command spelling changes for +DigiMou users.
The built wheel can coexist with upstream in both installation orders, and
uninstalling either leaves the other working. Generated KiCad compatibility is
unchanged.
