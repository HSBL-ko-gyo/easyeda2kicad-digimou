# Release Candidate Audit attempt 1 — Codex validation

Date: 2026-07-22; transport evidence finalized 2026-07-23 (Asia/Tokyo)

## Status

The Oracle answer is preserved verbatim in
`release_candidate_audit_attempt1_stale.md`. It is **not accepted as an audit of
the current candidate** because its executable/source claims match the earlier
Architecture Review snapshot rather than the current implementation. The first
browser capture timed out after 40 minutes and was harvested from the same
conversation. Oracle session metadata later confirmed the transport root cause:
Windows `npx` did not forward the long `--file` arguments, the session received
zero files, and only the first line of the multiline prompt was transmitted.
The model itself was correctly verified as non-Pro `GPT-5.6 Sol`.

An early locally prepared candidate-diff draft included a historical scoped
consultation diff and the prior Architecture Review answer, but that draft was
not actually delivered in this browser attempt. With no current files attached,
Oracle followed stale Architecture context and reported the already-fixed
B0–B9 and S1–S8 findings again. It also claimed that current provider fixtures
were absent even though they were present in the local candidate and test
collection.

## Finding-by-finding validation against current files

| Attempt-1 finding | Current evidence | Disposition |
| --- | --- | --- |
| B0 `sanitize_public_url` absent/import failure | `easyeda2kicad/metadata/cache.py:620` defines it. Three runtimes collect 737 tests and each report `666 passed, 71 skipped`; the built wheel imports and `--help` exits 0. | **Stale-source false positive.** |
| B1 different manufacturer retained | `metadata/service.py:448-455` assigns `MANUFACTURER_UNVERIFIED`, retains only a safe diagnostic/rejected display, and `continue`s before append. `tests/test_metadata_service.py` covers exclusion. | **Already fixed; false for current source.** |
| B2 DigiKey truncation accepted | `providers/digikey.py:350-405` rejects declared count mismatch and truncation, covering the 10/1 case alleged by attempt 1. The valid final audit later found a distinct mixed valid/unparseable-candidate gap. | **Attempt-1 claim fixed; separate RB-RC2-1 remains.** |
| B3 Mouser truncation accepted | `providers/mouser.py:232-252` rejects ordinary count/list disagreement, covering the 10/1 case alleged by attempt 1. The valid final audit later found dropped malformed candidates and zero-count missing/null `Parts`. | **Attempt-1 claim fixed; separate RB-RC2-1 remains.** |
| B4 LCSC metadata calls CAD | `metadata/service.py:145-159` constructs a dedicated `JlcpcbCatalogueClient`; `providers/lcsc.py` imports that client and contains no `get_cad_data_of_component` call. `EasyedaProvider` remains the CAD boundary. | **Already fixed.** |
| B5 normalized cache works without raw | Cache schema 2 validates both envelopes and their generation/request/timestamp/hash binding at `metadata/cache.py:500-551`. Corrupt/missing-pair offline tests expect `CACHE_CORRUPT`. | **Already fixed.** |
| B6 non-string MPN accepted | `metadata/models.py:28` defines strict `identity_text`; provider and model identity-type matrices reject bool/numeric/list/object inputs in `tests/test_provider_identity_types.py`. | **Already fixed.** |
| B7 manifest can overwrite CAD | `__main__.py:633-634` invokes selected-artifact collision validation before output and covers the attempt-1 scenarios. The valid final audit later isolated the reverse manifest-as-ancestor case. | **Attempt-1 claim mostly fixed; SF-RC2-1 remains.** |
| B8 no legacy/fixture/Python 3.9 evidence | All four DigiKey/Mouser fixtures and C2040 fixture/goldens are checked in. Baseline Python 3.9/3.14 is `177/69`; current Python 3.9/3.12/3.14 is `666/71`; `tests/test_legacy_offline_golden.py` is non-skipped. | **Already supplied.** |
| B9 no AGPL modification notice | Top-level `NOTICE` gives date, baseline, scope, contributor attribution, and AGPL continuation; `README.md` links it; `setup.py` packages `LICENSE` and `NOTICE`; both built archives contain them. | **Already fixed.** |
| S1 volatile symbol status/selection | `metadata/symbol_fields.py` reads status only from `CadRecord`; provider errors do not change it. DigiKey and Mouser use stable lexical distributor-number selection. | **Already fixed.** |
| S2 provider errors invisible | Default warnings contain safe code/operation/status; JSON/CSV include `provider_errors` plus structured `provider_diagnostics`. | **Already fixed.** |
| S3 corrupt offline CAD cache becomes miss | Service preserves `CACHE_CORRUPT`; `tests/test_metadata_service.py` asserts the blocking category and no network. | **Already fixed.** |
| S4 datasheet validation incomplete | `sanitize_public_url` is present; `symbol_fields.py:150-176` compares normalized public product/datasheet URLs and rejects equality. | **Already fixed.** |
| S5 project-relative path failure | `__main__.py:620-631` resolves paths and requires project containment; tests cover relative, outside-root, Windows cross-drive, and POSIX behavior. | **Already fixed.** |
| S6 all CAD parsers required | Current verification is action-aware; tests cover symbol-only, footprint-only, 3D-only, SVG-only, and manifest-only paths. Pin/pad comparison runs only for combined symbol+footprint requests. | **Already fixed.** |
| S7 U+2212 unhandled | `metadata/models.py:16-23` explicitly maps U+2212 and other documented presentation equivalents while preserving separator positions. | **Already fixed.** |
| S8 DigiKey client ID not scrubbed | Cache/provider redactors cover `client_id`, `clientId`, header variants, and prefixed suffixes. The final security correction also covers `oauthAccessToken` and `myClientSecret`. | **Already fixed.** |

The first audit's OPTIONAL items remain dispositioned in `docs/DECISIONS.md`:
O1 is intentionally deferred compatibility duplication, O2 was corrected in
documentation, and O3 is inherited upstream behavior unused by metadata mode.

## Corrective action for the review package

No runtime source change was required by the stale findings. The audit package
was corrected instead:

1. `release_candidate.diff` was regenerated from the same tested candidate.
2. Historical Oracle answers, availability logs, and the scoped consultation
   diff were excluded from that code-review diff.
3. The clean diff contains one current version of each product/test file and
   applies to the upstream baseline with `git apply --cached --check` exit 0.
4. Its SHA-256 is
   `cf4527f61101258a14cfff487f987a86111da87e453f06760eadb156066a421b`.
5. It was rescanned with zero high-confidence secret findings.
6. The valid final re-audit used short `-f` arguments, attached current source
   files directly, and stated that they were authoritative over all historical
   review records.

The completed three-runtime full test matrix and static gates remain valid
because this correction changed only generated review artifacts, not source,
tests, fixtures, or packaging inputs.
