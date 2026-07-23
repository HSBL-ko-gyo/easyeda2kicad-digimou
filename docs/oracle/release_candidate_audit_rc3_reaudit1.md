CANARY PASS

All ten planned direct attachments are present. Independent byte hashing matches every canary-listed direct attachment, including the 37,269-byte delta SHA-256 `695245d3ddde1a8607af0d17ac887170b7c8de0eb7b6861fa113201260a62b68`. The canary identifies the revised full candidate as 63 files, 723,055 bytes, SHA-256 `2c25cedc3f3720a3c9b54bc8563688b993d988e5ab75ba6791dc9c24dc23e6c5`; the secret audit independently records the same full/delta identities and clean-index apply checks. The canary explicitly defines the full candidate as the retained release artifact rather than one of these ten direct attachments, so this expected arrangement does not trigger `ORACLE INPUT UNAVAILABLE`.   

Every required fix invariant is present in the current source or delta. The delta contains 19 files and remains confined to documentation, the five affected shared source files, and corresponding regression tests. 

## RELEASE BLOCKER

**None. No release blocker remains.**

## RESOLVED

### RB-RC3-1 — Overflow and non-finite numeric failures retain typed semantics

**Disposition: RESOLVED**

The shared exact-candidate path now catches `OverflowError`, `TypeError`, and `ValueError` at all three relevant boundaries: raw candidate identity extraction, full record parsing, and reconstructed-record identity validation. Failures become `InvalidResponseError` with operation `exact-normalize`, rather than escaping as an untyped numeric exception. 

`optional_int()` rejects non-finite floats, while `optional_float()` converts integer-to-float overflow to `ValueError` and rejects non-finite direct or text-derived values. The normalized model likewise converts oversized numeric input to `ValueError`.  

Cache envelope parsing and validator execution now include `OverflowError`. Online mode treats an overflowing normalized entry as unusable, offline mode reports typed `CACHE_CORRUPT`, and refresh bypasses the entry. Service reconstruction also catches residual overflow before accepting the cached record.  

The service obtains and validates a provider record before assigning its raw-cache key or calling `cache.write()`. Thus a typed provider failure cannot publish either raw or normalized success; an invalid normalized online entry may only be replaced after a successful fresh fetch and validation. 

Provider coverage is complete for the authorized boundary:

* DigiKey live-shaped execution and direct raw replay. 
* LCSC live-shaped execution and direct raw replay. 
* Mouser live-shaped execution and direct raw replay. 
* Common infinity, NaN, oversized integer and oversized numeric-text probes. 
* Schema-3 online refetch, offline corruption and refresh bypass, plus direct cache-validator overflow mapping.  

### SF-RC3-1 — Manifest below a planned symbol file is rejected during preflight

**Disposition: RESOLVED**

Selected outputs now carry explicit file/directory type information. A symbol output is marked as a regular file and rejects a manifest that is equal to it, ancestral to it, or below it. Footprint, 3D and SVG outputs remain directories and therefore continue to permit ordinary manifest children. 

The collision check executes before creation of the default output directory and before metadata-mode execution. Consequently metadata, cache, CAD and manifest work cannot begin after a collision. 

Existing tests preserve the required allowed and rejected cases:

* Same-path and ancestor collisions remain rejected.
* Normal children of footprint directories remain allowed.
* Adjacent same-prefix paths remain allowed.
* Windows path semantics remain covered.  
* Both JSON and CSV child-of-symbol-file cases return 1; metadata resolution is instrumented to fail if entered, and the parent, symbol and manifest paths remain absent. 

### COMP-RC3-1 — Authorized scope and compatibility boundaries remain intact

**Disposition: RESOLVED**

The source delta is limited to internal overflow handling, cache/service exception mapping, and manifest preflight. It adds no dependency file, changes no public function signature, changes no CLI spelling, and does not alter a manifest or KiCad output schema.

`CACHE_SCHEMA_VERSION` remains 3. 

Provider and CAD responsibilities remain separated: LCSC, DigiKey and Mouser are metadata adapters, while EasyEDA remains the sole CAD provider. DigiKey and Mouser remain metadata-only during resolution.  

The conservative exact-MPN and LCSC-ID/MPN rules are unchanged: canonical LCSC IDs are still required, explicit mismatches remain fatal, and cached records are revalidated against MPN, manufacturer and distributor ID.   

Metadata mode remains opt-in. Legacy commands continue through the original conversion path, including multiple-ID processing and the previously accepted hidden argparse abbreviations.    

No Provider adapter implementation changed, so DigiKey/Mouser authentication, result truncation and LCSC pagination/identity behavior are not modified by this delta. The architecture continues to state GNU AGPL-3.0 unchanged. 

### QG-RC3-1 — Revised quality and integrity gates pass

**Disposition: RESOLVED**

The authoritative evidence reports:

* New blocker probes: `8 passed`
* Related Provider/cache/CLI/E2E set: `280 passed`
* Python 3.9.25: `695 passed, 71 skipped`
* Python 3.12.13: `695 passed, 71 skipped`
* Python 3.14.3: `695 passed, 71 skipped`
* Ruff formatting and lint: PASS
* Strict mypy: PASS
* Diff checks: PASS

The sequential full-suite runs returned exit code 0 and are expressly identified as authoritative. 

The revised secret audit and full/delta clean-index apply checks also pass. No real credential, authentication artifact, Oracle cache or provider token is present. 

## SHOULD FIX

### DOC-RC3-1 — Historical rows are corrected, but their quality-record pointer is stale

**Disposition: SHOULD FIX — partially resolved, non-blocking**

The substantive finding is corrected: all three `666 passed, 71 skipped` rows are now labelled `RC2 pre-RC3 tree`, not “Current tree.” 

The current re-audit quality record correctly reports `695 passed, 71 skipped` on all three Python versions. 

However, `legacy_compatibility.md` points readers to:

```text
docs/oracle/rc3_quality.md
```

while the authoritative revised record introduced by this delta is:

```text
docs/oracle/rc3_reaudit1_quality.md
```

The smallest fix is a one-line path correction in `legacy_compatibility.md`. This does not affect runtime behavior or release safety. If incorporated into the release artifact, regenerate the candidate/delta hashes and repeat the diff/apply and secret-document checks; no full code-matrix re-audit is required.

## ACCEPTABLE RISK

### AR-RC3-1 — Inherited reference-output skips

**Disposition: ACCEPTABLE RISK**

The same 69 inherited reference-output tests remain skipped because the optional upstream reference-output bundle is absent. The count did not increase. 

### AR-RC3-2 — Credentialed DigiKey and Mouser API execution remains unrun

**Disposition: ACCEPTABLE RISK**

The two credentialed live-provider tests remain skipped. No DigiKey or Mouser implementation changed in this delta, and no new evidence changes the previously accepted authentication/truncation risk. 

### AR-RC3-3 — Native Linux process E2E remains unrun

**Disposition: ACCEPTABLE RISK**

POSIX path behavior remains unit-tested, but native Linux process-level E2E is still unavailable and unchanged from the accepted initial disposition. 

## OPTIONAL

**None.**

**RELEASE VERDICT: RELEASE APPROVED WITH NON-BLOCKING DOC-RC3-1 PATH CORRECTION OUTSTANDING.**
