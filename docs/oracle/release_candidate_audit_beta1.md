CANARY PASS

The ten required current attachments are present. The full candidate is 68 files / 750,327 bytes with SHA-256 `5c848efe9e3dcbbb4dcc632f150cca0e7e824384230de250a18e644a907945d3`; the RC3-to-current delta is 17 files / 64,625 bytes with SHA-256 `04004f17a6a90cf0c308acb3d3a11696163bbe98c96cf9100dab000a7420c3d7`. Both match the attached canary. Candidate tree `0c7b7f01e3389ef7efbecec40574619d292bdf78` is consistently recorded in the current canary and secret audit with clean temporary-index application and applied-tree equality.

All direct-file SHA-256 values match the canary table. The four current runtime source attachments also match the delta target Git blobs; `__main__(1).py` and `export_kicad_symbol.py` require only CRLF-to-LF normalization to match their exact repository blobs. Historical RC2 remains closed, and the preserved RC3 approval is correctly not reused for these runtime changes.

## Classification summary

* **RELEASE BLOCKER:** None.
* **SHOULD FIX:** None.
* **OPTIONAL:** None.

## RESOLVED

### B1-FT-01 — Symbol Fields Table projection boundary

`NATIVE_SYMBOL_FIELDS` is exactly `Manufacturer`, `MPN`, `LCSC Part`, and `Datasheet`. `CUSTOM_SYMBOL_FIELD_ORDER` is empty and `build_symbol_fields()` returns an empty ordered mapping, so metadata mode itself emits no custom symbol-property keys. Native values are supplied separately through the existing exporter fields.

The regression test verifies that provider part numbers and URLs remain in the Manifest while the symbol field projection is empty, including when verification status and provider errors are present.

Metadata-mode `--custom-field` input also cannot override the native fields or inject the enumerated Provider, URL, package, lifecycle, status, price, stock, MOQ, packaging, retrieval-time, or cache-key fields. Rejection occurs during argument validation, before metadata execution.

**Minimum in-scope fix:** None.
**Re-audit required:** No.

### B1-FT-02 — Manifest completeness without KiCad leakage

JSON and CSV retain Provider identity, distributor part numbers, product URLs, package, lifecycle, manufacturer datasheet, CAD source/status, exact-match evidence, conflicts, provenance, diagnostics, cache state, retrieval time, price breaks, stock, MOQ, packaging, and currency. None is projected into symbol properties.

The explicit Manifest manufacturer is `Texas Instruments`, while the existing KiCad Manufacturer remains `TI(德州仪器)`, preventing both metadata loss and silent CAD-property replacement.

**Minimum in-scope fix:** None.
**Re-audit required:** No.

### B1-MAN-01 — Part-scoped explicit-manufacturer evidence

The CAD payload must first prove the requested canonical LCSC ID and reconcile any MPN it contains. Contradictory LCSC-ID or MPN evidence remains fatal before distributor processing.

When an explicit manufacturer differs from the EasyEDA display, `explicit_manufacturer_lookup` makes the LCSC ID lookup mandatory. That lookup validates:

* the same canonical distributor ID;
* the exact normalized requested MPN;
* the exact normalized explicit manufacturer.

Unavailable, ambiguous, corrupt, ID-mismatching, MPN-mismatching, or manufacturer-mismatching evidence propagates as a fatal service error.

DigiKey and Mouser are contacted only after that mandatory proof. Their own exact lookup and cached-result validation continue to require the requested manufacturer and MPN.

The focused failure regression supplies EasyEDA manufacturer `TI(德州仪器)`, explicit manufacturer `Texas Instruments`, and an unavailable LCSC ID lookup; it confirms one LCSC attempt and zero DigiKey exact calls.

**Minimum in-scope fix:** None.
**Re-audit required:** No.

### B1-ID-01 — Native-field collision policy

The reconciliation logic now:

* fills an empty Manufacturer, MPN, or LCSC Part;
* preserves an equivalent existing value;
* preserves a differing nonempty Manufacturer and emits a value-free warning;
* raises before export for a differing nonempty MPN or LCSC Part.

Reconciliation runs immediately after symbol import and before exporter construction or symbol-library writing.

The field audit additionally confirms that `--custom-field Manufacturer:Override` exits with status 1 before creating cache, Manifest, or CAD artifacts.

**Minimum in-scope fix:** None.
**Re-audit required:** No.

### B1-SYM-01 — Slash-bearing serialized symbol identity

`ExporterSymbolKicad` computes one `sanitize_fields()` result and uses that same value for:

* sub-unit integration;
* existing-symbol lookup;
* overwrite replacement/writing.

Thus `LM321MF/NOPB` is consistently handled as serialized KiCad root ID `LM321MF_NOPB`.

The focused regression writes the slash-bearing symbol twice with overwrite, verifies identical bytes, and verifies exactly one root symbol.

**Minimum in-scope fix:** None.
**Re-audit required:** No.

### B1-BYTE-01 — Real OPA333 and LM321 output evidence

Both legacy and metadata commands were executed from fresh temporary directories with identical relative output context.

The matching legacy/metadata hashes are:

* OPA333AIDBVR symbol: `7c6987e3283d6439db20784392a937d84f039a87b5a831336b88642cad3e18aa`
* OPA333AIDBVR footprint: `5cc7149d13f6364eb716222d534e614f42813a28f62a46136a423262ddd8b626`
* LM321MF/NOPB symbol: `dbaf992ced899d9166151d4cb5781569224bd48270791d4670ebd48879df5ccf`
* LM321MF/NOPB footprint: `2fe093ab299a1405586b13dc2b9501b5cea63f48b0e2e6a57114ba40ec75bed7`

Metadata adds zero property keys. Repeated metadata `--overwrite` leaves symbol, footprint, JSON Manifest, and CSV Manifest byte-identical. Root counts remain one, with property counts remaining eight for OPA333 and nine for LM321.

**Minimum in-scope fix:** None.
**Re-audit required:** No.

### B1-COMP-01 — Scope and compatibility

The corrective delta changes exactly four runtime source files: CLI reconciliation, symbol exporter identity, metadata service orchestration, and symbol-field projection. The remaining changes are directly related tests and documentation; no unrelated runtime refactor was found.

There is no corrective-delta change to dependencies, cache schema, Provider implementations, package/import name, or Manifest schemas. Legacy CLI spellings remain unchanged. EasyEDA remains the CAD Provider, while LCSC/DigiKey/Mouser remain metadata Providers. Output compatibility is supported by the real byte comparisons above.

The full-candidate, delta, and current-tree secret audit found no high-confidence credentials, tokens, private keys, authentication artifacts, or credential-bearing URLs. The retained matches are fixed sanitizer test inputs, and the corrective delta has zero generic credential-pattern matches.

**Minimum in-scope fix:** None.
**Re-audit required:** No.

### B1-QA-01 — Quality gates

The attached quality record reports:

* Python 3.9.25: `702 passed, 71 skipped`
* Python 3.12.13: `702 passed, 71 skipped`
* Python 3.14.3: `702 passed, 71 skipped`
* focused corrective regressions: `7 passed`
* Ruff format and lint: PASS
* Python 3.9 strict mypy: PASS
* `git diff --check`: PASS

**Minimum in-scope fix:** None.
**Re-audit required:** No.

## ACCEPTABLE RISK

### B1-AR-01 — Inherited reference-output skips

Sixty-nine skips remain because the optional inherited upstream reference-output bundle is absent. Focused checked-in legacy and real-part evidence covers this corrective scope.

**Minimum in-scope fix:** None.
**Re-audit required:** No, unless new reference evidence exposes a concrete regression.

### B1-AR-02 — Credentialed DigiKey/Mouser live APIs

One DigiKey and one Mouser credentialed live test remain skipped. No secret-bearing workaround was used, and no current corrective change affects their authentication or transport implementations.

**Minimum in-scope fix:** None.
**Re-audit required:** No, unless a later live run identifies a defect.

### B1-AR-03 — Native Linux process E2E

Native Linux process-level E2E was not run. No new path or process change beyond the verified KiCad symbol-name sanitization was introduced, so the established risk classification remains unchanged.

**Minimum in-scope fix:** None.
**Re-audit required:** No, unless a native Linux run produces conflicting evidence.

The mandatory post-answer source-canary recomputation remains the final mechanical gate. A matching recomputation requires no re-audit; any mismatch is `SOURCE CANARY FAIL` and invalidates this answer.

**RELEASE VERDICT: RELEASE APPROVED — no RELEASE BLOCKER, and no re-audit is required after a matching post-answer source-canary recomputation.**
