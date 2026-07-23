# Codex public-beta Release Candidate result — Oracle approved

Generated: 2026-07-23 (Asia/Tokyo)  
Upstream baseline: `fff10a38619963d7cb1c57d779655a9ea4572e95`  
Local branch: `feature/multi-distributor-metadata`  
Repository mutation policy: no commit, stash, push, or GitHub fork was created.
Publication status: revised release-prep candidate approved; commit, annotated
tag, and manual GitHub pre-release are authorized after final doc-only delta.

## 1. Architecture summary

The legacy EasyEDA-to-KiCad conversion path remains separate and is selected
when only legacy options such as `--lcsc_id`, `--symbol`, `--footprint`, `--3d`,
or `--full` are used. Additive metadata options select a new orchestration path:

```text
exact user/LCSC identity
  -> LCSC catalogue metadata + DigiKey metadata + Mouser metadata
  -> conservative exact-MPN/manufacturer validation
  -> one merged model with provenance, conflicts, and safe diagnostics
  -> EasyEDA-only CAD identity verification and conversion
  -> full JSON / BOM-compatible CSV / existing native KiCad properties
```

DigiKey and Mouser never supply CAD. LCSC catalogue metadata uses a dedicated
anonymous JLCPCB client; EasyEDA remains the sole CAD source. Provider results
are normalized into `PartIdentity`, `DistributorRecord`, `CadRecord`, and
`MergedPart`. Cache schema v3 binds credential-redacted raw evidence to its
normalized result by request, generation ID, timestamp, and SHA-256.

Detailed contracts and decisions are in `architecture.md`,
`PROVIDER_CONTRACT.md`, and `DECISIONS.md`.

## 2. Changed files

The new candidate starts from the source hashes audited in the closed RC2 cycle.
`docs/oracle/release_candidate.diff` remains RC2's immutable snapshot. The new
diff, canary, answer, and Codex disposition are recorded separately under
`docs/oracle/` and do not overwrite the RC2 evidence.

```text
.gitignore
AGENTS.md
MANIFEST.in
NOTICE
README.md
setup.py
easyeda2kicad/__main__.py
easyeda2kicad/easyeda/easyeda_api.py
easyeda2kicad/kicad/export_kicad_symbol.py
easyeda2kicad/kicad/parameters_kicad_symbol.py
easyeda2kicad/metadata/__init__.py
easyeda2kicad/metadata/cache.py
easyeda2kicad/metadata/cad_identity.py
easyeda2kicad/metadata/manifest.py
easyeda2kicad/metadata/merge.py
easyeda2kicad/metadata/models.py
easyeda2kicad/metadata/service.py
easyeda2kicad/metadata/symbol_fields.py
easyeda2kicad/providers/__init__.py
easyeda2kicad/providers/base.py
easyeda2kicad/providers/digikey.py
easyeda2kicad/providers/easyeda.py
easyeda2kicad/providers/lcsc.py
easyeda2kicad/providers/lcsc_client.py
easyeda2kicad/providers/mouser.py
docs/architecture.md
docs/CODEX_RESULT.md
docs/CURRENT_STATE.md
docs/DECISIONS.md
docs/FIELD_TABLE_AUDIT.md
docs/PROVIDER_CONTRACT.md
docs/examples/CAD_NOT_FOUND.mock.manifest.json
docs/examples/LM321MF-NOPB.manifest.json
docs/examples/OPA333AIDBVR.manifest.json
docs/oracle/README.md
docs/oracle/UNAVAILABLE.md
docs/oracle/architecture_review.md
docs/oracle/cli_help.txt
docs/oracle/consultations/001-manufacturer-alias.diff
docs/oracle/consultations/001-manufacturer-alias-identity.md
docs/oracle/example_validation.md
docs/oracle/legacy_compatibility.md
docs/oracle/secret_audit.md
tests/fixtures/legacy/C2040.json
tests/fixtures/legacy/golden/LQFN-56_L7.0-W7.0-P0.4-EP.kicad_mod
tests/fixtures/legacy/golden/legacy_c2040.kicad_sym
tests/fixtures/providers/digikey_keyword_lm321.json
tests/fixtures/providers/digikey_keyword_opa333.json
tests/fixtures/providers/mouser_search_lm321.json
tests/fixtures/providers/mouser_search_opa333.json
tests/test_cli_metadata.py
tests/test_cli_metadata_e2e.py
tests/test_custom_fields.py
tests/test_documented_examples.py
tests/test_easyeda_api.py
tests/test_easyeda_identity.py
tests/test_jlcpcb_search.py
tests/test_legacy_offline_golden.py
tests/test_metadata_cache.py
tests/test_metadata_manifest_fields.py
tests/test_metadata_merge.py
tests/test_metadata_models.py
tests/test_metadata_service.py
tests/test_provider_base.py
tests/test_provider_digikey.py
tests/test_provider_identity_types.py
tests/test_provider_lcsc_easyeda.py
tests/test_provider_live.py
tests/test_provider_mouser.py
tests/test_symbol_lib_helpers.py
```

## 3. Implemented features

- Exact MPN search with separator/suffix preservation and no fuzzy substitution.
- Exact optional manufacturer constraint and mandatory part-scoped LCSC
  evidence when an explicit or inferred label differs from EasyEDA CAD.
- Fatal LCSC-ID/MPN mismatch and ambiguous/truncated provider-result handling.
- Official DigiKey Product Information V4 OAuth/search and official Mouser
  Search API V2 adapters with retry/rate-limit handling.
- LCSC catalogue metadata separated from EasyEDA CAD retrieval.
- Provider-specific records, prices, stock, MOQ, packaging, currency, retrieval
  time, provenance, conflicts, and credential-safe diagnostics.
- Metadata-only `CAD_NOT_FOUND`; `--require-cad` changes that state to exit 1
  after writing the selected manifest.
- Provider-scoped 24-hour metadata cache with strict `--offline`, metadata-only
  `--refresh-metadata`, corrupt-pair detection, and secret stripping.
- JSON manifest and BOM-compatible CSV with formula-injection protection.
- Existing native KiCad identity properties only; Provider, status,
  sales/cache/diagnostic fields stay Manifest-only.
- Action-aware symbol/footprint/3D parsing, portable output validation, collision
  prevention, and symbol-pin/footprint-pad comparison.
- AGPL-3.0 retention with a dated `NOTICE` packaged beside `LICENSE`.

## 4. CLI examples

Exact-MPN enrichment with all distributor providers:

```bash
easyeda2kicad --full \
  --mpn OPA333AIDBVR \
  --manufacturer "Texas Instruments" \
  --providers lcsc,digikey,mouser \
  --manifest-json ./build/OPA333AIDBVR.json \
  --manifest-csv ./build/OPA333AIDBVR.csv \
  --output ./libs/project_parts
```

Unchanged legacy form:

```bash
easyeda2kicad --full --lcsc_id C30878 --output ./libs/project_parts
```

Strict cached execution and metadata-only refresh are separate operations:

```bash
easyeda2kicad --mpn OPA333AIDBVR --providers lcsc,digikey,mouser \
  --offline --manifest-json ./build/offline.json

easyeda2kicad --mpn OPA333AIDBVR --providers lcsc,digikey,mouser \
  --refresh-metadata --manifest-json ./build/refreshed.json
```

Require verified CAD while retaining a diagnostic manifest:

```bash
easyeda2kicad --mpn EXAMPLE-NO-CAD-001 \
  --manufacturer "Example Semiconductor" --providers digikey \
  --require-cad --manifest-json ./build/no-cad.json
```

The final help capture is `oracle/cli_help.txt`; `--help` exits 0.

## 5. Existing CLI compatibility

- The metadata path is opt-in; legacy argument dispatch and conversion classes
  remain in place.
- A direct baseline/current C2040 comparison produced identical SHA-256 for
  symbol, footprint, footprint SVG, and symbol SVG.
- A checked-in no-network legacy CLI golden asserts exit 0, one stdout banner,
  empty stderr, byte-identical symbol/footprint, and no unwanted 3D directory.
- Baseline Python 3.9.25 and 3.14.3 each pass `177` tests with `69` inherited
  resource skips. Full details are in `oracle/legacy_compatibility.md`.

## 6. Test and static-analysis results

Final source-change matrix:

| Gate | Result |
| --- | --- |
| Python 3.9.25 pytest | `702 passed, 71 skipped` |
| Python 3.12.13 pytest | `702 passed, 71 skipped` |
| Python 3.14.3 pytest | `702 passed, 71 skipped` |
| Ruff format check | PASS, `59 files already formatted` |
| Ruff lint | PASS |
| Python 3.9 strict mypy | PASS, 59 source files |
| `git diff --check` | PASS; only Git LF/CRLF working-tree notices |
| Manifest example test | `4 passed` |
| Legacy offline golden | `1 passed` |

The current 71 skips are the 69 inherited missing-reference skips plus two
explicit live-provider skips. No test is failing.

## 7. Real component E2E and Manifest examples

Both public runs completed on Windows with exit 0 and generated symbol,
footprint, WRL, STEP, JSON, and CSV outputs:

| Part | LCSC | Public providers executed | Root/CAD status | Example |
| --- | --- | --- | --- | --- |
| OPA333AIDBVR | C30878 | LCSC catalogue + EasyEDA CAD | `VERIFIED` / `VERIFIED` | [`examples/OPA333AIDBVR.manifest.json`](examples/OPA333AIDBVR.manifest.json) |
| LM321MF/NOPB | C131103 | LCSC catalogue + EasyEDA CAD | `VERIFIED` / `VERIFIED` | [`examples/LM321MF-NOPB.manifest.json`](examples/LM321MF-NOPB.manifest.json) |

The third required state is represented by the explicitly mocked
[`examples/CAD_NOT_FOUND.mock.manifest.json`](examples/CAD_NOT_FOUND.mock.manifest.json).
It has distributor metadata, no CAD artifacts, root/CAD status
`CAD_NOT_FOUND`, and explicit user manufacturer authority. Tests verify both
normal success and `--require-cad` exit 1 after manifest output.

All three checked-in examples pass lossless model/schema, exact-MPN, safe URL,
cache-key, portable-path, hidden-property-boundary, and CAD-semantics checks.

## 8. KiCad Symbol Fields Table boundary

Reference and Value retain existing display behavior. Metadata mode reuses only
the native `Manufacturer`, `MPN`, `LCSC Part`, and `Datasheet` properties and
adds no Provider-specific or status custom property. `Datasheet` preserves the
existing source value unless `--datasheet-link` is explicitly selected.

Provider part numbers/URLs, manufacturer datasheet, package, lifecycle, CAD
source/status, provenance, diagnostics, cache state, price, stock, MOQ,
packaging, currency, and retrieval time remain Manifest-only. The real
OPA333AIDBVR and LM321MF/NOPB audit found zero new symbol columns, byte-identical
legacy/metadata symbols and footprints, and byte-identical repeated
`--overwrite` output. Details are in `FIELD_TABLE_AUDIT.md`.

## 9. DigiKey and Mouser authentication

Credentials are read lazily from environment variables and are never written to
source, manifests, cache keys, diagnostics, or logs.

| Provider | Required | Optional public context |
| --- | --- | --- |
| DigiKey | `DIGIKEY_CLIENT_ID`, `DIGIKEY_CLIENT_SECRET` | `DIGIKEY_LOCALE_SITE` (default `US`), `DIGIKEY_LOCALE_LANGUAGE` (default `en`), `DIGIKEY_LOCALE_CURRENCY` (default `USD`) |
| Mouser | `MOUSER_API_KEY` | none |

DigiKey access tokens stay in memory. The Mouser key is placed only in the
official request URL at transport time and is scrubbed from errors/cache data.
Missing credentials produce visible `AUTH_MISSING` diagnostics and do not stop
available providers or verified CAD.

## 10. Real API execution status

- Public anonymous JLCPCB catalogue and EasyEDA CAD: **executed successfully**
  for both required real parts.
- DigiKey: **not executed live** because both credential variables were absent;
  its live smoke test skipped explicitly.
- Mouser: **not executed live** because its credential variable was absent; its
  live smoke test skipped explicitly.
- Both distributor adapters are covered by saved official-response-shape
  fixtures plus authentication, exact-match, ambiguity/truncation, retry,
  rate-limit, cache, and redaction tests.

## 11. Packaging and license

The current package builds both sdist and wheel. Each contains `LICENSE` and the
dated `NOTICE`; the wheel also contains every metadata/provider module,
including `providers/lcsc_client.py`. Importing directly from the built wheel
and invoking its `--help` succeeds. AGPL-3.0 remains unchanged.

## 12. Not implemented in this phase

- Manufacturer CAD providers.
- Ultra Librarian or SamacSys automatic download/import.
- Web scraping outside official APIs/public EasyEDA/JLCPCB behavior already used
  by the upstream project.
- Fuzzy MPN matching, suffix removal, compatible-part substitution, or a global
  manufacturer-alias table.
- Gerber or PCB-design functionality.
- Background inventory/lifecycle monitoring.

## 13. Residual risks

- **AR-RC2-1:** DigiKey and Mouser production credentials and live responses
  remain unverified in this environment.
- A real distributor-present/EasyEDA-CAD-absent part was not verified; the state
  machine and exit behavior use deterministic mocks.
- **AR-RC2-2:** Native Linux runtime E2E was unavailable. POSIX path semantics
  are unit-tested but do not replace a Linux process-level run.
- **AR-RC2-3:** Upstream's optional `tests/reference_outputs/` directory is
  absent, so 69 inherited reference-output tests skip. A focused checked-in
  C2040 golden covers the legacy path but does not recreate every omitted
  upstream golden.
- Distributor API schemas, quotas, account permissions, prices, and stock can
  change externally. The new common exact-normalization boundary fails closed
  on indeterminate or exact-but-unparseable raw candidates.

## 14. Human checks before publication

- Complete the distinct public-beta corrective RC Oracle audit and preserve its
  candidate/source-canary evidence before any publication.
- Run the opt-in DigiKey/Mouser live smoke tests with approved account
  credentials, without capturing their values in CI logs.
- Run the full suite and representative legacy/metadata commands on native
  Linux.
- Open the generated symbols/footprints in supported KiCad releases and inspect
  hidden properties and 3D paths interactively.
- Review the account-specific DigiKey/Mouser API terms, quota, and redistribution
  obligations before distributing cached sales data.
- Review the complete unstaged `oracle/release_candidate.diff` and Oracle audit
  disposition before creating any commit.

## 15. Next-phase candidates (recorded only)

- Manufacturer-official CAD Provider.
- Ultra Librarian local-file importer.
- SamacSys local-file importer.
- Multiple CAD-source comparison.
- Semi-automatic datasheet-dimension versus footprint verification.
- Bulk metadata enrichment of existing KiCad project parts.
- Scheduled stock/lifecycle monitoring.

## 16. Public-beta release preparation

- Current upstream/package version: `1.0.1`.
- Selected PEP 440 beta version: `1.1.0b1`.
- Planned annotated tag: `v1.1.0b1`.
- Display name: `easyeda2kicad +DigiMou`.
- Planned fork: `HSBL-ko-gyo/easyeda2kicad-digimou`.
- Python distribution/import/CLI name: unchanged as `easyeda2kicad`.
- PyPI: explicitly out of scope and not used.

The README, NOTICE, setup metadata, release notes, issue form, and security
reporting route were prepared without changing dependencies or CLI spellings.
The real final-tree quality matrix is `702 passed, 71 skipped` on Python
3.9.25, 3.12.13, and 3.14.3. Ruff format/lint, strict mypy over 59 files,
`git diff --check`, explicit legacy/metadata/Manifest fixtures, and release
artifact secret scans pass.

A clean temporary Git-tree snapshot produced:

- `easyeda2kicad-1.1.0b1.tar.gz`;
- `easyeda2kicad-1.1.0b1-py3-none-any.whl`;
- `RELEASE_NOTES.md`;
- `CLI_HELP.txt`; and
- `SHA256SUMS.txt`.

The wheel and sdist each contain LICENSE, NOTICE, and required package modules,
contain no tests/cache/Oracle bundle/credential files, install into separate
new Python 3.9 venvs, report version `1.1.0b1`, and run installed CLI help.
The installed metadata CLI reaches the expected typed offline/cache failure
path without network access. Artifacts remain outside the repository.

## 17. Oracle review status

Architecture Review and consultation 001 are complete, recorded, and
dispositioned. RC2's valid final re-audit remains closed as
**CANARY PASS / RELEASE BLOCKED**:

- **RB-RC2-1 — fixed in the new candidate:** one common Provider helper
  classifies every raw MPN before full parsing. Only a provably different MPN is
  skipped; indeterminate and exact-but-unparseable candidates fail
  `INVALID_RESPONSE`. Mouser missing/null `Parts` is invalid even at count zero.
- **SF-RC2-1 — fixed in the new candidate:** resolved preflight rejects a
  manifest that equals or is an ancestor of selected CAD output before any
  persistent output, while a regular child manifest remains valid.
- **SF-RC2-2 — confirmed, documentation corrected:** the stale Provider-contract
  audit status was updated after the audit. No runtime source changed.
- **AR-RC2-1 through AR-RC2-3 — accepted and disclosed:** credentialed live
  provider calls, native Linux process E2E, and the missing inherited reference
  bundle remain external limitations.
- Oracle reported no required OPTIONAL item and marked the remaining audited
  compatibility, cache, secret, CAD-boundary, and licensing areas resolved.

The complete RC2 answer remains `docs/oracle/release_candidate_audit.md`; its
second/final re-audit limit is unchanged. The distinct new cycle's initial audit
is preserved separately and reported `CANARY PASS / RELEASE BLOCKED` for an
overflow exception-class gap and a manifest-below-symbol-file collision.
Re-audit 1 then reported `CANARY PASS`, no release blocker, and
`RELEASE APPROVED` subject only to one non-blocking document pointer. That
pointer is corrected, and all three full Python matrices were rerun at
`695 passed, 71 skipped`. Oracle explicitly required regenerated hashes,
diff/apply checks, and secret-document checks rather than another model
re-audit; the final evidence records those passes.

That approval applies only to the preserved RC3 candidate. The subsequent
public-beta field-table audit required runtime changes to the KiCad projection,
explicit-manufacturer evidence path, and slash-bearing overwrite lookup.

The distinct public-beta corrective initial audit is now preserved in
`docs/oracle/release_candidate_audit_beta1.md`. Oracle CLI 0.16.0 used browser
foreground mode, `--browser-manual-login`, GPT-5.6 Sol, and ten individual
attachments with no bundle/cache. It reported CANARY PASS, no RELEASE BLOCKER,
no SHOULD FIX, and RELEASE APPROVED; post-answer canaries matched 10/10 direct
attachments and 17/17 source-table entries.

Release preparation subsequently changed the version and package/repository
metadata and added release documentation/templates. No dependency, runtime
behavior, test, CLI spelling, API, cache schema, or output format changed.

Re-audit 1 is preserved in
`docs/oracle/release_candidate_audit_beta1_reaudit1.md`. Oracle verified seven
individual current attachments with `bundled: null`, the 74-path candidate
SHA-256 `93f312f93119140709116d036597d9e4ca78f3e97879e2ef644b9784c5474bf4`,
the 12-path release-prep delta SHA-256
`68187df63a7a093d536c4d48232b56fd2482a37366f4684f959cf946daf84f25`,
and source tree `334715a99d5ee514338199e27e685db1a78de81e`.
It reported CANARY PASS, no RELEASE BLOCKER, no SHOULD FIX, no OPTIONAL item,
and approved commit/tag/manual GitHub pre-release without PyPI.

Post-answer canaries match 23/23 source-table entries, 7/7 direct attachments,
and the package-input candidate tree. The mandatory operational constraint is
to push `feature/multi-distributor-metadata` and annotated tag `v1.1.0b1`
without pushing the version-changing commit to `master`.
