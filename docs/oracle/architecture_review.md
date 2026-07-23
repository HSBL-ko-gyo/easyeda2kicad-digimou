## Architecture Review Verdict

**Not ready for release-candidate status.** The overall direction is correct—separate legacy and metadata paths, EasyEDA as the intended sole CAD authority, local exact-MPN validation, official DigiKey/Mouser APIs, provider-scoped metadata caches, and hidden-property reuse are all appropriate choices. The attached implementation nevertheless has **seven fix-now blockers**, **two pre-release blockers**, and several smaller boundary and test issues. The stated architecture itself requires preserving legacy conversion and preventing distributor metadata from becoming CAD authority. 

# BLOCKER

## B1 — Cross-provider manufacturer disagreement can become a false match

**Affected files:**
`easyeda2kicad/metadata/service.py`
`easyeda2kicad/metadata/merge.py`
`tests/test_metadata_service.py`
`tests/test_metadata_merge.py`

**Reasoning:** Provider-local validation correctly treats the same MPN returned under different manufacturers as multiple identities. After LCSC or CAD establishes an MPN, however, the service queries DigiKey and Mouser without constraining them by the inferred manufacturer. The merge then accepts every exact-MPN record and merely records manufacturer disagreement as a nonfatal conflict unless the user explicitly supplied `--manufacturer`. This can attach a valid distributor record for a different manufacturer to the EasyEDA CAD of the LCSC manufacturer.

The alias problem—such as `TI(德州仪器)` versus `Texas Instruments`—is real, but without an explicit alias authority there is no safe way to distinguish an alias from a genuinely different manufacturer. Treating both cases as verified purchasing records is less conservative than the provider-local matching rule.   

**Smallest backward-compatible fix:** When no user manufacturer is supplied, compare every distributor manufacturer with the manufacturer established by CAD/LCSC. If normalized values differ, exclude that distributor record from `distributor_records` and stable symbol properties, report `MANUFACTURER_UNVERIFIED`, and leave the overall result `PARTIAL`. Preserve the conflicting display value in diagnostics for audit. Do not introduce fuzzy matching or an alias table.

**Disposition:** **FIX NOW.**

**Missing tests:**

* Same MPN, genuinely different manufacturers across LCSC and DigiKey.
* Same MPN, genuinely different manufacturers across LCSC and Mouser.
* Alias-like disagreement is retained as a diagnostic but not published as a verified distributor match.
* Disagreeing records never reach KiCad properties or BOM rows.

---

## B2 — DigiKey search completeness is not proven before selecting an exact match

**Affected files:**
`easyeda2kicad/providers/digikey.py`
`tests/test_provider_digikey.py`

**Reasoning:** DigiKey requests exactly 50 records starting at position zero and performs no pagination or total-count completeness check. A matching or conflicting identity after record 50 is invisible, allowing a false `NOT_FOUND` or a false unique result. In addition, non-object entries in `Products` cause `INVALID_RESPONSE`, while malformed entries in `ExactMatches` are silently discarded because the strict length check is applied only to `Products`.  

An empty or structurally incomplete successful response can also become `NOT_FOUND`; `NOT_FOUND` should require a valid official zero-result envelope, not merely the absence of parsed candidates.

**Smallest backward-compatible fix:** Page using `RecordStartPosition` until the official result count is exhausted. If the API cannot provide the entire candidate set, fail closed as `AMBIGUOUS` with operation `search-truncated`. Validate every item in both `Products` and `ExactMatches`, and require the official result container/count even for a zero-result response.

**Disposition:** **FIX NOW.**

**Missing tests:**

* Exact candidate appears after the first 50 records.
* Conflicting exact manufacturer appears after the first 50 records.
* Declared total exceeds scanned records.
* Malformed item in `ExactMatches`.
* Empty object and missing result-count fields are `INVALID_RESPONSE`, not `NOT_FOUND`.

---

## B3 — Mouser result truncation can be mistaken for a complete exact search

**Affected files:**
`easyeda2kicad/providers/mouser.py`
`tests/test_provider_mouser.py`

**Reasoning:** Mouser reads `NumberOfResult`, but only rejects the special case where the count is nonzero and the returned `Parts` list is empty. A response declaring ten results while returning one part is treated as complete, and that one part can become the selected exact identity. Missing `SearchResults` is also treated as an empty search rather than an invalid response. 

**Smallest backward-compatible fix:** Require a valid `SearchResults` object and nonnegative integer result count. The number of returned parts must equal the declared count unless the client implements complete pagination. If completeness cannot be obtained, return `AMBIGUOUS/search-truncated`, never a unique match or `NOT_FOUND`.

**Disposition:** **FIX NOW.**

**Missing tests:**

* `NumberOfResult > len(Parts)`.
* Negative, nonnumeric, and missing result counts.
* Missing `SearchResults`.
* Conflicting exact identity hidden in an incomplete result set.

---

## B4 — The LCSC metadata provider calls the CAD endpoint and violates refresh isolation

**Affected files:**
`easyeda2kicad/providers/lcsc.py`
`easyeda2kicad/providers/easyeda.py`
`easyeda2kicad/easyeda/easyeda_api.py`
`easyeda2kicad/metadata/service.py`
`tests/test_provider_lcsc_easyeda.py`
`tests/test_metadata_service.py`

**Reasoning:** The CLI creates separate CAD and metadata API instances specifically to keep their caches and refresh controls separate. The LCSC metadata provider nevertheless implements distributor-ID lookup by first calling `get_cad_data_of_component`. Consequently, an explicit LCSC-ID run can fetch EasyEDA CAD once through the CAD provider and a second time through the metadata provider. `--refresh-metadata` can therefore trigger a fresh CAD HTTP request despite the documented promise that it refreshes metadata only.   

This also means an LCSC distributor record can be derived from CAD data rather than the LCSC/JLC catalogue, and the associated metadata “raw” cache may contain `{}` or CAD-derived evidence rather than the sales-provider response. `EasyedaApi` itself now contains JLCPCB stock/price search methods, mixing CAD transport and distributor sales responsibilities. 

**Smallest backward-compatible fix:**

1. Remove the CAD-first branch from `LcscProvider.get_part_by_distributor_id`.
2. Resolve an LCSC distributor ID only through the JLCPCB/LCSC catalogue and filter the returned canonical LCSC ID exactly.
3. Keep `EasyedaProvider` as the only caller of `get_cad_data_of_component`.
4. Move the catalogue transport into an LCSC-specific client. A temporary forwarding method can remain on `EasyedaApi` for compatibility, but the provider should stop depending on the mixed class.
5. Store the official catalogue response before mapping, not the already-normalized adapter object.

**Disposition:** **FIX NOW.**

**Missing tests:**

* Explicit LCSC ID performs exactly one CAD fetch.
* `--refresh-metadata` never bypasses or invalidates CAD cache.
* LCSC raw cache contains catalogue response evidence, not CAD.
* CAD absence does not imply LCSC metadata absence.
* Malformed nested price or attribute containers become `INVALID_RESPONSE`, not traceback.

---

## B5 — Normalized cache entries are trusted without their raw evidence

**Affected files:**
`easyeda2kicad/metadata/cache.py`
`easyeda2kicad/metadata/service.py`
`easyeda2kicad/providers/lcsc.py`

**Reasoning:** A cache hit reads only `normalized.json`. The check that `raw_response_cache_key` equals the cache key proves only that the normalized object contains the expected request hash; it does not prove that `raw.json` exists, belongs to that normalized record, or has not been altered. Offline mode can therefore accept a fabricated or stale normalized distributor URL/part number with missing or corrupt raw evidence, provided its exact MPN and provider fields pass validation. 

The cache also calls `strip_secrets` on the purported raw response before storing it, meaning it is a redacted projection rather than reproducible raw API evidence. The raw and normalized files are atomically written individually but are not cryptographically or transactionally bound as one generation.  

**Smallest backward-compatible fix:**

* Store a `raw_sha256` and generation ID in both envelopes.
* On every normalized hit, require and validate the matching raw envelope and hash.
* Prefer re-running provider normalization and exact selection from raw data, or cache the complete normalized candidate set rather than only the selected record.
* Name the stored form `redacted_raw` if redaction remains; otherwise fail writes when an unexpected secret-bearing field is detected rather than silently changing the evidence.
* Bump the metadata cache schema version.

**Disposition:** **FIX NOW.**

**Missing tests:**

* Normalized file exists but raw is absent.
* Raw exists but normalized is absent.
* Raw hash mismatch.
* Raw provider/request envelope mismatch.
* Offline stale pair succeeds.
* Offline incomplete or mismatched pair is `CACHE_CORRUPT`.
* Concurrent/interrupted pair replacement.

---

## B6 — Malformed non-string identity fields can become exact string matches

**Affected files:**
`easyeda2kicad/providers/base.py`
`easyeda2kicad/providers/digikey.py`
`easyeda2kicad/providers/mouser.py`
`easyeda2kicad/providers/lcsc.py`
`easyeda2kicad/metadata/models.py`

**Reasoning:** `optional_text` converts every non-`None` object with `str(value)`. The MPN normalizer also converts its input with `str`. A malformed numeric MPN `123`, boolean, list, or mapping can therefore become text and potentially match a user query such as `"123"` instead of producing `INVALID_RESPONSE`.  

The CAD identity implementation is stricter and rejects container-valued evidence; the distributor providers should enforce the same boundary. The design record expressly treats container-valued CAD identity evidence as invalid. 

**Smallest backward-compatible fix:** Introduce a strict `identity_text` helper accepting only nonempty strings. Use it for MPN, manufacturer, LCSC ID, and distributor part number. Keep the lenient text helper only for descriptive fields. Validate direct `DistributorRecord` construction as well as `from_dict`.

**Disposition:** **FIX NOW.**

**Missing tests:** Numeric, boolean, list, and mapping values in every provider’s MPN, manufacturer, and distributor-ID fields.

---

## B7 — A manifest path can silently overwrite the generated KiCad library

**Affected files:**
`easyeda2kicad/__main__.py`
`easyeda2kicad/metadata/manifest.py`
`tests/test_cli_metadata.py`
`tests/test_cli_metadata_e2e.py`

**Reasoning:** Validation checks only that JSON and CSV manifest paths differ from each other. It does not compare them with CAD output paths. The symbol is exported to `<output>.kicad_sym`, after which requested manifests are written. A command using that same path for `--manifest-json` or `--manifest-csv` will replace the valid KiCad symbol file and can still return status zero.   

The manifest writers intentionally replace their target atomically, so the collision is destructive rather than a failed write. 

**Smallest backward-compatible fix:** After output normalization, reject manifest paths that resolve to:

* `<output>.kicad_sym`;
* anything inside `<output>.pretty`;
* anything inside `<output>.3dshapes`;
* anything inside `<output>.svgs` when SVG export is requested.

Use platform-aware resolved/case-normalized comparisons.

**Disposition:** **FIX NOW.**

**Missing tests:** JSON and CSV collisions with symbol, footprint, SVG, STEP, and WRL targets, including Windows case-insensitive path variants.

---

## B8 — Legacy CLI and KiCad byte compatibility are asserted but not demonstrated

**Affected files/process:**
`tests/test_regression.py`
release CI
baseline-diff procedure
golden reference files

**Reasoning:** The architecture promises a distinct legacy path with unchanged validation, EasyEDA calls, output paths, datasheet behavior, exit codes, and generated geometry. That dispatch separation is present. 

The regression tests, however, skip symbol, footprint, and 3D comparisons whenever their reference directories are absent. The attached review bundle does not contain those reference files or provider fixtures, so the claimed byte-stability and test totals cannot be independently reproduced from the supplied material.  

The only documented baseline run is Python 3.12.13, despite the package targeting Python 3.9+. 

**Smallest backward-compatible fix/check:**

* Check in representative offline CAD fixtures and byte-for-byte golden KiCad outputs.
* Make absent references a CI failure, not a skip, in the release job.
* Run the untouched baseline and extension under Python 3.9 and at least one current Python.
* Compare stdout/stderr and exit status for representative legacy commands.
* Diff all importer/exporter changes against `fff10a38619963d7cb1c57d779655a9ea4572e95`; revert or split changes unrelated to metadata.
* Run on both Windows and Linux.

**Disposition:** **POST-IMPLEMENTATION, PRE-RC BLOCKER.**

---

## B9 — AGPL is retained, but the required prominent modification notice is incomplete

**Affected files:**
`README.md` or new `NOTICE`
`setup.py`
release packaging

**Reasoning:** The root license, setup license field, and classifier remain AGPL-3.0, which is correct.  The attached architecture also identifies the baseline and says the license is unchanged. 

For conveying a modified source version, AGPL section 5 requires prominent notices stating that the work was modified and giving a relevant date. The attached tree does not contain a clear release-facing modification notice with a date and fork/source location; `setup.py` still identifies only the upstream author and upstream repository.  

**Smallest backward-compatible fix:** Add a top-level notice stating:

* this is a modified version of uPesy/easyeda2kicad.py;
* the exact upstream baseline commit;
* modification/release date;
* fork source URL and contributor attribution;
* continued AGPL-3.0 licensing.

Preserve the upstream author and license; add fork/contributor metadata rather than replacing upstream attribution.

**Disposition:** **MUST BE FIXED BEFORE DISTRIBUTION OR RC TAGGING.**

# SHOULD FIX

## S1 — The hidden `Verification Status` property is not stable

**Affected files:**
`easyeda2kicad/metadata/service.py`
`easyeda2kicad/metadata/symbol_fields.py`
provider selection code
symbol-field tests

**Reasoning:** A requested DigiKey or Mouser authentication/rate-limit failure downgrades the merged result from `VERIFIED` to `PARTIAL`. That overall status is then persisted into every generated symbol. The same verified CAD and identity can therefore produce different KiCad output based only on whether distributor credentials were available at generation time.  

Distributor part-number selection is also based on lowest MOQ before lexical part number, so a hidden DigiKey/Mouser part field can change indirectly when sales terms change even though MOQ itself is excluded. The design explicitly describes lowest-MOQ preference. 

**Smallest backward-compatible fix:** Remove overall `Verification Status` from KiCad properties or replace it with a CAD-only field derived from `cad.verification_status`. Keep provider completeness in manifests. For symbol distributor IDs, use a stable non-sales-dependent selection rule, or omit the field when multiple packaging variations exist.

**Disposition:** **FIX NOW.**

**Test:** Symbol metadata must remain byte-identical across auth failure, stock, price, MOQ, retrieval-time, and rate-limit changes.

---

## S2 — Missing credentials are not visibly reported by default

**Affected files:**
`easyeda2kicad/metadata/service.py`
`easyeda2kicad/__main__.py`

**Reasoning:** The README promises a visible provider error and a continuing `PARTIAL` result. The service catches provider errors and retains only the category string. The CLI prints those errors only when `--show-conflicts` is explicitly requested or when the user examines a manifest. A symbol-only command can succeed with status zero while requested DigiKey/Mouser metadata silently disappears.   

The conversion to `_error_code` also discards safe operation and HTTP status context already present in `ProviderError`. 

**Smallest backward-compatible fix:** Log one credential-safe warning for each nonfatal provider error by default. Store structured diagnostics such as `{code, operation, status}` in manifests while continuing to exclude request URLs, headers, bodies, and secrets.

**Disposition:** **FIX NOW.**

---

## S3 — Corrupt offline CAD cache is misreported as a cache miss

**Affected files:**
`easyeda2kicad/easyeda/easyeda_api.py`
`tests/test_easyeda_api.py`

**Reasoning:** Invalid cached JSON first sets `last_error = "cache_corrupt"`. Offline handling then calls `_offline_cache_miss`, which overwrites it with `"offline_cache_miss"` before checking whether it was corrupt. The corruption category is therefore lost.  

Current tests cover online corrupt-cache fallback and offline cache misses, but not corrupt CAD JSON offline.  

**Smallest backward-compatible fix:** Preserve the pre-offline error or have `_offline_cache_miss` avoid overwriting `cache_corrupt`. Add an offline-corrupt fixture that verifies no network call and a `CACHE_CORRUPT` provider result.

**Disposition:** **FIX NOW.**

---

## S4 — Explicit datasheet selection accepts invalid or product-page URLs

**Affected files:**
`easyeda2kicad/metadata/symbol_fields.py`
`tests/test_metadata_manifest_fields.py`

**Reasoning:** Automatic manufacturer-datasheet selection filters for HTTP(S) and excludes distributor product pages, but explicit `--datasheet-link` selection merely checks that the field is nonempty and returns it. A malformed provider response can therefore put a product page, `javascript:` value, or unrelated string into the native KiCad Datasheet property. 

**Smallest backward-compatible fix:** Apply the same shared URL validator to explicit selections: HTTP(S), valid authority, and normalized datasheet URL unequal to the provider product URL.

**Disposition:** **FIX NOW.**

---

## S5 — `--project-relative` fails for ordinary relative or out-of-tree paths

**Affected files:**
`easyeda2kicad/__main__.py`
CLI path tests

**Reasoning:** The implementation calls `Path(...).relative_to(Path.cwd())`. A relative output path cannot be made relative to an absolute CWD this way, an absolute output outside CWD raises `ValueError`, and Windows paths on different drives fail. 

Metadata mode catches some resulting export errors, but the legacy path can still surface an uncaught exception.

**Smallest backward-compatible fix:** Resolve both paths first. Require the output library to be under the project root, or calculate a platform-aware relative path with a clear validation error. On different Windows drives, reject during argument validation rather than during export.

**Disposition:** **FIX NOW.**

**Missing tests:** Relative path, absolute in-tree path, out-of-tree path, Windows same-drive, and Windows cross-drive.

---

## S6 — Manufacturer is changed after conflict and provenance calculation

**Affected files:**
`easyeda2kicad/metadata/service.py`
`easyeda2kicad/metadata/merge.py`

**Reasoning:** `merge_records` selects the identity manufacturer and creates conflicts/provenance. `MetadataResolution.to_merged` may then overwrite `merged.identity.manufacturer` with the CAD/LCSC trusted display value and replace its provenance. This can leave `Conflict.selected_value` inconsistent with the final identity, or omit a conflict entirely when a sole distributor manufacturer disagrees with CAD.  

**Smallest backward-compatible fix:** Pass the trusted display manufacturer and source into `merge_records` as a non-filtering identity seed. Generate conflicts and provenance once, around the final selected value. Do not mutate identity after merge.

**Disposition:** **FIX NOW.**

---

## S7 — Metadata mode always requires both symbol and footprint parsing

**Affected files:**
`easyeda2kicad/__main__.py`
CAD verification tests

**Reasoning:** `_verify_metadata_cad` always imports both symbol and footprint and always requires nonempty pin and pad sets, even for manifest-only, symbol-only, SVG-only, or 3D-only commands. The architecture says the pin/pad comparison applies “when both symbol and footprint are available.”   

This introduces a new metadata-path failure for a valid symbol whose package data is absent or unparseable, despite the symbol itself being exportable by the legacy path.

**Smallest backward-compatible fix:** Verify CAD identity independently. Parse only the artifacts required by the requested action. Run pin/pad comparison only when both parsed artifacts are present; require both only for `--full` or combined symbol-and-footprint export.

**Disposition:** **FIX NOW.**

---

## S8 — Unicode dash handling does not cover common minus-like characters

**Affected files:**
`easyeda2kicad/metadata/models.py`
normalization tests

**Reasoning:** The normalizer converts characters in Unicode category `Pd`. Common copied ordering codes can contain U+2212 MINUS SIGN, whose category is `Sm`, so it remains distinct from ASCII hyphen despite the stated Unicode-dash conversion rule. The implementation otherwise correctly preserves separator positions and keeps `-`, `_`, and `/` distinct. 

**Smallest backward-compatible fix:** Define an explicit, documented translation table containing accepted presentation-equivalent dash/minus code points, followed by the existing NFKC, uppercase, trimming, and whitespace collapse. Do not remove or reposition separators.

**Disposition:** **FIX NOW.**

---

## S9 — Secret scrubbing does not cover DigiKey client ID

**Affected files:**
`easyeda2kicad/metadata/cache.py`
`easyeda2kicad/providers/base.py`
secret-scanning tests

**Reasoning:** The cache scrub patterns cover API keys, client secrets, tokens, authorization, and passwords, but not `client_id`/`clientId`. The normal service path does not currently include the client ID in its canonical request, so no direct client-secret or token leak was found. Nevertheless, the stated boundary says DigiKey credential values, including the client ID, must never enter cache keys or cache content.  

**Smallest backward-compatible fix:** Add normalized `client_id`, `clientid`, and DigiKey header-name variants to both scrub implementations. Add nested request/raw-response tests for client ID, secret, token, authorization header, and Mouser query URLs.

**Disposition:** **FIX NOW.**

# OPTIONAL

## O1 — There are two independent cache-key abstractions and an over-wide provider protocol

**Affected files:**
`easyeda2kicad/providers/base.py`
`easyeda2kicad/metadata/cache.py`
`easyeda2kicad/metadata/service.py`
provider tests

**Reasoning:** `providers/base.py` defines its own canonical-request and cache-key implementation, while the service actually uses `MetadataCache.canonical_request` and `MetadataCache.get_cache_key`. The provider protocol also requires normalization, validation, cache-key generation, auth description, exact search, and distributor-ID lookup from every provider, although orchestration uses only a subset. Security tests against `provider.get_cache_key` can therefore pass without exercising the actual service cache-key path.   

**Smallest backward-compatible fix:** Make `metadata/cache.py` the single cache-key authority. Retain provider methods as deprecated forwarding wrappers if external callers may use them. Narrow the orchestration protocol and use smaller optional protocols for distributor-ID lookup and authentication description.

**Disposition:** **POST-IMPLEMENTATION CLEANUP.**

---

## O2 — Documentation calls common models immutable although they are intentionally mutable

**Affected files:**
`docs/architecture.md`
`easyeda2kicad/metadata/models.py`
`easyeda2kicad/metadata/service.py`

**Reasoning:** The architecture labels `models.py` as immutable common dataclasses, but the dataclasses are not frozen and the service mutates records, identities, paths, statuses, cache keys, and provenance.  

**Smallest backward-compatible fix:** Correct the documentation to “validated mutable dataclasses with JSON-safe serialization.” Freezing the current models would be a larger incompatible refactor and is not justified now.

**Disposition:** **DOCUMENTATION CLEANUP AFTER FIXES.**

---

## O3 — Product-page image scraping is out of scope for this extension

**Affected files:**
`easyeda2kicad/easyeda/easyeda_api.py`
baseline diff/release scope

**Reasoning:** The architecture states that this extension does not scrape product pages, while `EasyedaApi` contains an HTML scraper for LCSC product images and logs transport exception text. The method is not shown as part of the metadata orchestration path, so it is not itself a metadata runtime blocker, but it expands the mixed-responsibility class and contradicts the stated scope.   

**Smallest backward-compatible fix:** If this method was introduced after the stated baseline, split it into a separate change or remove it. If it predates the extension, clarify that the **new metadata path** performs no product-page scraping and ensure tests prove it is never invoked.

**Disposition:** **POST-IMPLEMENTATION BASELINE-DIFF CHECK.**

# Areas that are otherwise sound

* The CLI has a genuine separate legacy dispatch and does not route ordinary `--lcsc_id` commands through `MergedPart`.
* The central MPN rule correctly applies NFKC, uppercase, outer trimming, internal whitespace collapse, Unicode `Pd` conversion, and preserves suffixes and separator positions. Similar forms such as `LM321MF/NOPB` and `LM321MF-NOPB` remain distinct. 
* Explicit LCSC ID plus MPN is verified against actual CAD payload evidence before DigiKey/Mouser are contacted; neither identifier silently overrides the other. 
* DigiKey OAuth tokens remain in memory, Mouser’s query-string API key is replaced by safe provider exceptions, and neither client intentionally places credentials in normal cache requests or manifests.
* Direct stock, price, MOQ, currency, retrieval timestamps, cache keys, and provider errors are excluded from symbol properties. 
* JSON and CSV writers are deterministic and atomic per file; Windows- and POSIX-style path values are preserved as strings. 
* The AGPL-3.0 license file and package classifier remain intact.

## Mandatory post-implementation release checks

Before RC designation:

1. Run the unchanged baseline suite and the extension suite on Python 3.9 and a current Python release.
2. Run Windows and Linux jobs, including relative, absolute, out-of-tree, and cross-drive paths.
3. Use checked-in offline CAD/provider fixtures; release jobs must not silently skip golden comparisons.
4. Verify byte-identical legacy symbol, footprint, 3D-path, stdout/stderr, and exit-code behavior against `fff10a38619963d7cb1c57d779655a9ea4572e95`.
5. Add credential-gated live DigiKey and Mouser smoke tests; the architecture claims these, but they are not present in the attached provider test files. The documented test strategy also lists truncation, cache, Windows/POSIX, and secret-scanning release gates that need executable evidence. 
6. Scan generated cache files, manifests, logs, and exceptions for all credential values.
7. Test every cache corruption and refresh combination, including raw/normalized mismatch and corrupt CAD cache offline.
8. Add the dated AGPL modification notice and verify it is present in both source and packaged artifacts.
