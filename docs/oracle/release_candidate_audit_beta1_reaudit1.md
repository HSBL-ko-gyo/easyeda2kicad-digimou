CANARY PASS

This is the distinct public-beta corrective re-audit cycle; neither historical RC2 nor preserved RC3 approval is reused.

## Canary verification

All seven current attachments are present and readable. Direct recomputation produced:

* Revised full candidate: **74 paths, 803,147 bytes**, SHA-256 `93f312f93119140709116d036597d9e4ca78f3e97879e2ef644b9784c5474bf4`
* Initial-to-revised delta: **12 paths, 63,485 bytes**, SHA-256 `68187df63a7a093d536c4d48232b56fd2482a37366f4684f959cf946daf84f25`
* Revised audited source tree: `334715a99d5ee514338199e27e685db1a78de81e`
* Clean temporary-index application/tree equality: PASS
* Built package inputs equal revised-candidate package inputs: PASS

Every attached-file SHA-256 matches the canary, including the initial answer, quality record, secret audit and inherited `publish.yml`. The internal release-prep and eight protected runtime/test hashes also match the current canary table.

The release-prep delta changes exactly these 12 paths:

`.github/ISSUE_TEMPLATE/bug_report.yml`, `.github/ISSUE_TEMPLATE/config.yml`, `NOTICE`, `README.md`, `SECURITY.md`, `docs/CODEX_RESULT.md`, `docs/CURRENT_STATE.md`, `docs/DECISIONS.md`, `docs/oracle/README.md`, `docs/releases/v1.1.0b1.md`, `easyeda2kicad/_version.py`, and `setup.py`.

No protected runtime or focused-test path appears in that delta.

## Classification summary

* **RELEASE BLOCKER:** None
* **SHOULD FIX:** None
* **OPTIONAL:** None

## RESOLVED

### B1-RA1-CAN-01 — Candidate identity and source canary

The candidate/delta hashes, path counts, source-tree identity, direct attachments and required release files are mutually consistent. Newly added files reconstructed from the full diff also match their target Git blobs and listed SHA-256 values.

**Minimum in-scope fix:** None.
**Re-audit required:** No. A failed post-answer canary recomputation would invalidate this answer mechanically.

### B1-FT-01 — Symbol Fields Table projection boundary

The protected `symbol_fields.py` and associated focused tests are unchanged by the 12-path delta. The authoritative initial finding therefore remains applicable: metadata mode emits no custom properties, while only Manufacturer, MPN, LCSC Part and Datasheet use the existing native projection.

**Minimum in-scope fix:** None.
**Re-audit required:** No.

### B1-FT-02 — Manifest completeness without KiCad leakage

The runtime and test hashes are unchanged. Provider identity, URLs, lifecycle, provenance, diagnostics, cache state, price, stock, MOQ and other sales data remain in JSON/CSV Manifests and are not projected into symbols.

**Minimum in-scope fix:** None.
**Re-audit required:** No.

### B1-MAN-01 — Part-scoped manufacturer evidence

`metadata/service.py` and its focused tests are unchanged. Same canonical LCSC ID, exact normalized MPN and exact explicit manufacturer remain mandatory before DigiKey or Mouser processing; unavailable or contradictory evidence remains fatal.

**Minimum in-scope fix:** None.
**Re-audit required:** No.

### B1-ID-01 — Native-field collision policy

CLI reconciliation and its tests are unchanged. Empty/equivalent fields may be reconciled; a differing nonempty Manufacturer is preserved with a value-free warning; nonempty MPN or LCSC-ID conflicts fail before export.

**Minimum in-scope fix:** None.
**Re-audit required:** No.

### B1-SYM-01 — Slash-bearing symbol identity

The exporter and symbol-helper test hashes are unchanged. Sanitized serialized identity remains common to lookup, sub-unit integration and overwrite, preventing duplicate `LM321MF_NOPB` roots.

**Minimum in-scope fix:** None.
**Re-audit required:** No.

### B1-BYTE-01 — Real-part byte compatibility

No runtime or output-path change was introduced. The established OPA333AIDBVR and LM321MF/NOPB legacy/metadata symbol and footprint hashes remain authoritative, including byte-identical repeated metadata overwrite and unchanged property/root counts.

**Minimum in-scope fix:** None.
**Re-audit required:** No.

### B1-COMP-01 — Compatibility and release-prep scope

The delta contains no Provider, cache, Manifest, exporter, CLI parser, dependency or public-API implementation path. `setup.py` keeps `name="easyeda2kicad"` and changes only descriptive/project metadata; `_version.py` changes only `1.0.1` to `1.1.0b1`. No `install_requires`, entrypoint, console-script, import-path or cache-schema change appears.

The README and release notes expressly preserve the import package, CLI command, public API, legacy `--lcsc_id` path and legacy KiCad output.

**Minimum in-scope fix:** None.
**Re-audit required:** No.

### B1-RA1-VERSION-01 — Version, tag and derivative identity

`1.1.0b1` is valid PEP 440, is a prerelease, and sorts after stable `1.0.1`; `1.0.1b1` would have sorted before that stable release. The intended annotated tag is consistently `v1.1.0b1`. Distribution/import/CLI identity remains `easyeda2kicad`; only the display name and repository slug identify +DigiMou. PyPI publication is expressly prohibited.

**Minimum in-scope fix:** None.
**Re-audit required:** No.

### B1-RA1-DOC-01 — Attribution, behavior and publication documentation

README, NOTICE, setup metadata and release notes clearly identify:

* the unofficial derivative and exact upstream baseline;
* continued GNU AGPL-3.0 licensing;
* no DigiKey, Mouser, LCSC, EasyEDA or upstream endorsement/ownership;
* exact-MPN fail-closed behavior and unchanged legacy path;
* EasyEDA-only CAD responsibility;
* raw/normalized cache, offline and refresh semantics;
* native-only KiCad projection and Manifest-only volatile sales data;
* environment-only credentials and no persistence to logs, Manifests, cache or properties;
* GitHub-pre-release-only installation and no PyPI beta.

**Minimum in-scope fix:** None.
**Re-audit required:** No.

### B1-RA1-ISSUE-01 — Issue and security reporting boundaries

The issue form requires OS, Python, KiCad, command, Provider, MPN, LCSC ID, legacy/metadata mode, cache mode, actual result, expected result and a minimal reproduction. It explicitly forbids API keys, client secrets, access tokens, Authorization headers, credential-bearing URLs and unsanitized/raw cache material, including through a required confirmation.

The issue configuration links directly to private vulnerability reporting, and `SECURITY.md` provides a no-details public fallback if that route is unavailable.

**Minimum in-scope fix:** None.
**Re-audit required:** No.

### B1-QA-01 / B1-RA1-ART-01 — Quality, build and release artifacts

The revised candidate evidence records:

* Python 3.9.25, 3.12.13 and 3.14.3: **702 passed, 71 skipped** each
* Explicit release fixtures: **7 passed**
* Ruff format/lint: PASS
* Strict mypy: PASS over 59 files
* `git diff --check`: PASS
* Version/import and installed CLI help: PASS
* Clean sdist/wheel builds
* Dual fresh-venv installation
* Required LICENSE, NOTICE and package modules present
* Tests, caches, Oracle material, credentials and build leakage absent

Reported release hashes:

* `easyeda2kicad-1.1.0b1.tar.gz`: `f14db949c2d3c5b7bc4e262183b1f14a8eea19e5129ddb8e90839dea8c221e32`
* `easyeda2kicad-1.1.0b1-py3-none-any.whl`: `13b52e840ebab29b2cf8bec1de5ebb0136d171a7634baa843cb02f4261fa2be7`

The independent secret record agrees that built package inputs equal revised-candidate package inputs and reports zero high-confidence secrets in source, delta and release artifacts.

**Minimum in-scope fix:** None.
**Re-audit required:** No.

### B1-RA1-PUB-01 — GitHub-only publication workflow

The inherited workflow triggers only on a **push to `master` that changes `easyeda2kicad/_version.py`**. A feature-branch push, an annotated-tag push and manual GitHub pre-release creation do not satisfy that trigger.

The concrete hazardous deviation is an off-plan `master` push containing the version change **before** `v1.1.0b1` exists. That would create a lightweight tag, create an automatic GitHub release and attempt PyPI publication.

If the annotated tag already exists, the workflow exits at its tag-existence check before build, release or PyPI. Under the stated sequential plan there is no tag/release duplication. A second release would require an operational deviation such as a differently spelled or differently cased tag.

**Minimum in-scope fix:** None for the audited plan. Do not push the `_version.py` change to `master` before completing the manual beta release.
**Re-audit required:** No. A changed publication plan involving `master` would require a new workflow assessment.

## ACCEPTABLE RISK

### B1-AR-01 — Inherited reference-output skips

Exactly 69 inherited skips remain because the optional upstream reference-output bundle is absent.

**Minimum in-scope fix:** None.
**Re-audit required:** No, unless new reference evidence exposes a regression.

### B1-AR-02 — Credentialed DigiKey/Mouser live E2E

The credentialed DigiKey and Mouser live tests remain unrun; no secret-bearing workaround was introduced.

**Minimum in-scope fix:** None.
**Re-audit required:** No, unless a later live run exposes a defect.

### B1-AR-03 — Native Linux process E2E

Native Linux process-level E2E remains unrun. This release-prep delta introduces no runtime, process or path implementation change.

**Minimum in-scope fix:** None.
**Re-audit required:** No, unless native execution produces conflicting evidence.

These are the same three accepted risks established by the initial audit and recorded in the revised quality evidence.

**RELEASE VERDICT: YES — this exact revised candidate is ready to commit, push on `feature/multi-distributor-metadata`, tag with the annotated tag `v1.1.0b1`, and publish as a manual GitHub pre-release without PyPI. Do not push the version-changing commit to `master`; the only remaining gate is a matching post-answer source-canary recomputation.**
