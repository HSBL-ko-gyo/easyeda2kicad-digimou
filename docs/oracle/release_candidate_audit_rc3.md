CANARY PASS

The four direct attachments are internally consistent and identify a new RC3 initial audit cycle; RC2 remains closed as `CANARY PASS / RELEASE BLOCKED`. The candidate diff independently hashes to `64b95ce3b63cd281c51e1bb200c8519d769503d69451bcd0b02d7336901a4ecb`, is 708,139 bytes, and contains 62 file entries. The quality and secret-audit hashes also match the canary. Every listed invariant was located in the current diff, so the `ORACLE INPUT UNAVAILABLE` stop condition does not apply.  

## RELEASE BLOCKER

### RB-RC3-1 — Exact-MPN parsing can escape as an untyped `OverflowError`

**Evidence**

The new common boundary correctly classifies raw MPNs before parsing and converts ordinary `TypeError`/`ValueError` parser failures into `InvalidResponseError`:

* `easyeda2kicad/providers/base.py:344-404`
* especially `base.py:371-383` for raw-MPN classification
* and `base.py:385-390` for full-record parsing

However, the parser boundary catches only:

```python
except (TypeError, ValueError):
```

The shared optional numeric parsers can raise `OverflowError`:

* `easyeda2kicad/providers/base.py:533-547`

  * `int(value)` at line 539 can overflow for a non-finite JSON float.
* `easyeda2kicad/providers/base.py:571-583`

  * `float(value)` at line 575 can overflow for an oversized JSON integer.

All three exact-MPN adapters call these helpers while converting a raw exact candidate:

* DigiKey stock, MOQ and price data: `easyeda2kicad/providers/digikey.py:287-357`
* Mouser stock, MOQ and price data: `easyeda2kicad/providers/mouser.py:178-233`
* LCSC stock, MOQ and price data: `easyeda2kicad/providers/lcsc.py:96-178`

An exact candidate containing an exponent-shaped JSON number such as `1e10000`, or an oversized integer in a price field, can therefore propagate an untyped `OverflowError` instead of the required typed Provider/parse failure.

The normalized-cache path has the same exception-class gap:

* `easyeda2kicad/metadata/service.py:541-555` catches only `TypeError` and `ValueError` while reconstructing a cached `DistributorRecord`.
* `easyeda2kicad/metadata/cache.py:285-296` catches only `TypeError`, `ValueError`, and `KeyError` from a cache validator.

A malformed schema-3 normalized entry containing an overflowing numeric value can consequently crash instead of becoming an online cache miss or an offline typed cache-corruption failure.

**Impact**

This does not appear to create or cache a false exact match—the exception occurs before cache publication—but it violates two mandatory RC3 properties:

1. A raw exact-MPN candidate that cannot be fully parsed must produce a typed Provider/parse failure.
2. Live response, raw-response replay, normalized cache, offline and refresh must have equivalent fail-closed semantics.

**Smallest required fix**

* Catch `OverflowError` at `_normalize_exact_candidates()`’s parser boundary.
* Make `optional_int()` and `optional_float()` explicitly reject non-finite or overflowing numeric values as `ValueError`.
* Include `OverflowError` in normalized-cache reconstruction and validation handling, mapping it to the existing online-miss/offline-corruption behavior.
* Add one overflowing exact-candidate regression for each Provider, covering live and direct raw-response normalization.
* Add schema-3 normalized-cache tests for online, offline and refresh behavior.
* Confirm failed responses leave neither raw nor normalized cache entries.

**Re-audit requirement**

Required. Produce a new candidate diff and canary hashes, then rerun the focused Provider/cache set, related regression set, all Python 3.9/3.12/3.14 matrices, Ruff, strict mypy, diff/apply checks and secret audit.

---

### SF-RC3-1 — Manifest below a selected symbol file bypasses preflight and leaves partial output

**Evidence**

The preflight represents the symbol output as a file and the other CAD outputs as directories:

* `easyeda2kicad/__main__.py:433-441`

It rejects only when the selected output is equal to or below the manifest path:

* `easyeda2kicad/__main__.py:443-458`

That correctly detects a manifest which is the same as or ancestral to a CAD output. It does not detect the reverse relationship for the symbol file.

Concrete accepted collision:

```text
--symbol
--output /tmp/lib
--manifest-json /tmp/lib.kicad_sym/meta.json
```

The selected symbol is `/tmp/lib.kicad_sym`, so the manifest is being placed below a path that must become a regular file.

Execution order then makes this destructive:

* CAD export occurs at `easyeda2kicad/__main__.py:1005-1054`.
* Manifests are written afterward at `__main__.py:1056-1057`.
* JSON writing calls `path.parent.mkdir(...)` at `easyeda2kicad/metadata/manifest.py:285-286`.
* The exception is converted to a failed return at `__main__.py:884-903`, but the already-created symbol file is not rolled back.

The existing tests cover same-path, ancestor, directory-child, adjacent-prefix, relative `..`, Windows comparison and early termination:

* `tests/test_cli_metadata.py:252-413`

They do not cover a manifest path descending from a selected symbol **file**.

**Impact**

The command exits unsuccessfully but leaves a partial KiCad symbol output. That violates the required collision invariant that failure occur before CAD, manifest, cache or other persistent output begins and leave no partial output.

A manifest nested below a selected footprint, 3D or SVG **directory** must remain allowed; the defect is specifically the impossible child-of-file relationship.

**Smallest required fix**

Make collision rules aware of output type:

* For the symbol file, reject both containment directions:

  * manifest equal to or ancestral to the symbol;
  * manifest descending from the symbol.
* For footprint, 3D and SVG directories, continue allowing ordinary manifest children while rejecting equal or ancestral paths.
* Preserve adjacent same-prefix paths.
* Add JSON and CSV child-of-symbol-file tests through `main()`, asserting:

  * exit code 1;
  * metadata resolution is never entered;
  * no symbol, manifest, cache or parent output path is created.

**Re-audit requirement**

Required. Re-run the focused path tests, complete CLI/E2E set, all supported Python matrices, path checks on Windows-aware and POSIX path objects, and the standard candidate integrity gates.

## SHOULD FIX

### DOC-RC3-1 — Historical compatibility evidence is labelled as the current tree

**Evidence**

`docs/oracle/legacy_compatibility.md:47-55` labels three rows as “Current tree” with:

```text
666 passed, 71 skipped
```

The actual RC3 quality record reports:

```text
687 passed, 71 skipped
```

for Python 3.9, 3.12 and 3.14. 

The 666-pass figures appear to be valid historical RC2-era evidence, but “Current tree” makes the document disagree with the current candidate.

**Smallest required fix**

Preserve the historical numbers but rename those rows to something such as `RC2 pre-RC3 tree`, and add a short pointer stating that the current matrix is recorded in `docs/oracle/rc3_quality.md`.

**Re-audit requirement**

Documentation-only verification is sufficient, but the changed document and candidate diff hashes must be regenerated and checked in the next mandatory re-audit.

## ACCEPTABLE RISK

### AR-RC3-1 — Inherited reference-output tests remain skipped

The full matrix still has 69 inherited skips because the upstream `tests/reference_outputs/` bundle is absent. The skip count did not increase, and dedicated checked-in legacy golden evidence remains present. 

**Smallest required fix:** None for this RC.

**Re-audit requirement:** None unless the reference bundle is introduced or the skip count changes.

---

### AR-RC3-2 — Credentialed DigiKey and Mouser API execution remains unrun

The two live Provider tests remain skipped because credentials are absent. No new evidence shows deterioration in authentication or response handling. 

**Smallest required fix:** None for this RC.

**Re-audit requirement:** None unless credentialed runs are performed; any resulting response-shape differences must then be reviewed against RB-RC3-1 and exact-MPN truncation behavior.

---

### AR-RC3-3 — Native Linux process E2E remains unrun

POSIX path behavior is unit-tested, but no native Linux process-level E2E was added. This is unchanged from the previously accepted risk. 

**Smallest required fix:** None for this RC.

**Re-audit requirement:** None unless native Linux results become available or Linux-specific code changes.

## RESOLVED

### RES-RC3-1 — Raw MPN is classified before full conversion in all three Providers

The shared helper performs raw identity extraction and conservative normalization before calling the full parser:

* `easyeda2kicad/providers/base.py:344-404`
* DigiKey raw MPN: `providers/digikey.py:259-267`
* Mouser raw MPN: `providers/mouser.py:174-176`
* LCSC raw MPN: `providers/lcsc.py:92-94`

Only a provably different normalized MPN is skipped. Missing, non-string, empty or otherwise indeterminate identity evidence produces `InvalidResponseError`.

Regression coverage includes, for each Provider:

* indeterminate candidate followed by a valid exact candidate;
* exact candidate with an incomplete record;
* provably mismatching candidate with malformed unrelated fields;
* all candidates indeterminate;
* live-shaped and direct raw-response normalization.

Representative evidence:

* `tests/test_provider_digikey.py:371-430`
* `tests/test_provider_mouser.py:237-296`
* `tests/test_provider_lcsc_easyeda.py:147-219`

The focused record reports all 22 selected cases passing. 

**Smallest required fix:** None except RB-RC3-1’s exception-class edge.

**Re-audit requirement:** Re-check because RB-RC3-1 requires modification to this boundary.

---

### RES-RC3-2 — Mouser response container and LCSC ID/MPN validation remain strict

Mouser requires `SearchResults` to be an object and `Parts` to be a list even when the official result count is zero:

* `easyeda2kicad/providers/mouser.py:235-260`
* `tests/test_provider_mouser.py:225-234`

LCSC keeps canonical `C[1-9][0-9]*` IDs, unique exact identity resolution, pagination before uniqueness claims and strict ID/MPN mismatch rejection:

* `easyeda2kicad/providers/lcsc.py:227-327`
* `easyeda2kicad/providers/lcsc.py:350-368`
* `tests/test_provider_lcsc_easyeda.py:222-327`

**Smallest required fix:** None.

**Re-audit requirement:** Only if these files change while fixing the blockers.

---

### RES-RC3-3 — Schema 3 invalidates schema-2 normalized successes and ordinary invalid responses are not cached

`CACHE_SCHEMA_VERSION` is 3:

* `easyeda2kicad/metadata/cache.py:20`

Normalized entries require a matching raw evidence pair and both envelopes are validated:

* `metadata/cache.py:228-282`

The service fetches and validates the Provider record before assigning the cache key or writing either cache entry:

* `easyeda2kicad/metadata/service.py:528-586`

The regression test verifies:

* failed exact response creates neither raw nor normalized cache;
* offline mode does not invoke the Provider;
* refresh propagates the same typed Provider failure;
* no replacement cache pair is published.

Evidence:

* `tests/test_metadata_service.py:739-797`
* `tests/test_metadata_cache.py:210-225`

The quality record confirms schema-2 rejection and write ordering. 

**Smallest required fix:** None for the tested ordinary failure classes; RB-RC3-1 must extend this to overflowing numeric failures.

**Re-audit requirement:** Required as part of RB-RC3-1.

---

### RES-RC3-4 — Required manifest same/ancestor checks and ordinary path normalization are implemented

For the expressly listed directory cases, the candidate:

* resolves relative, absolute, `.` and `..` paths before comparison;
* rejects a manifest equal to or ancestral to selected CAD output;
* supports Windows case-insensitive `PureWindowsPath` comparison;
* allows a normal manifest child of a selected directory;
* allows adjacent same-prefix paths;
* terminates before metadata resolution or output creation.

Evidence:

* `easyeda2kicad/__main__.py:426-459`
* `easyeda2kicad/__main__.py:585-629`
* `tests/test_cli_metadata.py:300-413`

**Smallest required fix:** None for those cases; SF-RC3-1 must close the child-of-symbol-file case.

**Re-audit requirement:** Required because the same preflight function must change.

---

### RES-RC3-5 — Legacy CLI, EasyEDA-to-KiCad behavior and Provider/CAD boundaries remain preserved

Metadata mode remains opt-in:

* `easyeda2kicad/__main__.py:389-404`

Legacy commands bypass the metadata orchestration and continue through the original EasyEDA route:

* `easyeda2kicad/__main__.py:1094-1101`

Previously accepted argparse abbreviations remain supported without being newly advertised:

* `easyeda2kicad/__main__.py:350-366`
* `tests/test_cli_metadata.py:629-656`

LCSC catalogue metadata and EasyEDA CAD retrieval are instantiated as separate responsibilities:

* `easyeda2kicad/metadata/service.py:145-168`

DigiKey and Mouser remain metadata-only and do not become CAD sources:

* `metadata/service.py:384-460`

The related regression run reports 252 passing tests, and all three full matrices report 687 passed with unchanged skips. 

No dependency addition or version update was found in the candidate.

**Smallest required fix:** None.

**Re-audit requirement:** Re-run the compatibility matrix after the blocker fixes because common Provider and CLI preflight code will change.

---

### RES-RC3-6 — Symbol-property stability, custom-property compatibility and CAD-not-found behavior are preserved

The hidden symbol projection contains stable identity, source and lifecycle fields only. Price, stock, MOQ, timestamps, cache keys, conflicts and Provider errors are expressly excluded:

* `easyeda2kicad/metadata/symbol_fields.py:14-35`

Legacy mode continues to permit existing custom-property names which metadata mode reserves:

* `tests/test_cli_metadata.py:602-626`

`CAD_NOT_FOUND`:

* writes a manifest and returns success when CAD is optional;
* creates no KiCad artifact;
* returns 1 after writing the manifest when `--require-cad` is selected.

Evidence:

* `tests/test_cli_metadata_e2e.py:489-569`
* `easyeda2kicad/__main__.py:1056-1067`

**Smallest required fix:** None.

**Re-audit requirement:** Re-run these E2E tests after SF-RC3-1 because CAD/manifest ordering is adjacent code.

---

### RES-RC3-7 — Credential and public-output boundaries pass

The current secret audit covers the 62-file candidate, current source/tests/docs, README, setup metadata and direct Oracle attachments. It reports no private keys, cloud/API tokens, JWT-shaped values, session cache, browser profile or authentication artifact. Generic URL/query matches are fixed sanitization test fixtures rather than credentials.  

Provider errors expose typed codes and bounded context rather than credentials, while public product and datasheet URLs are sanitized before normalized-cache publication.

**Smallest required fix:** None.

**Re-audit requirement:** Repeat the secret audit after regenerating the release candidate.

## OPTIONAL

No OPTIONAL findings.

**RELEASE VERDICT: RELEASE BLOCKED**
