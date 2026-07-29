# Oracle review log

Oracle is used as an independent second designer/reviewer. Its responses are
advisory and are checked against code, official API behavior, and tests before
adoption. No Oracle browser profile, session cache, cookie, API key, client
secret, or access token is copied into this repository.

## Tool discovery

- Command run before first use: `npx -y @steipete/oracle --help`
- Oracle CLI version: `0.16.0`
- Date: 2026-07-22 (Asia/Tokyo)
- Available engines reported: `api`, `browser`
- Selected execution for all successful reviews: `browser`, foreground,
  `--browser-manual-login`
- Model policy: verified non-Pro/standard model only; the historical failed Pro
  attempts below predate this repository rule and were not reused.

## Architecture Review

Status: **completed, saved, and dispositioned**.

### Execution

The complete review used one ChatGPT conversation in two Oracle captures:

1. `easyeda-architectu-full-review`
   - 2026-07-22 20:27:26–21:08:01 JST
   - engine/mode: browser foreground with manual login
   - Oracle model ID: `gpt-5.5`
   - browser picker evidence: requested and resolved `Thinking 5.5`, verified
     `yes`
   - input: 20 selectors expanded and packed as 40 files, approximately
     139,498 tokens
   - result: the browser response outlived Oracle's capture timeout; only a
     preamble was captured, so no answer was accepted from this attempt
2. `easyeda-architectu-review-followup`
   - 2026-07-22 21:08:55–21:44:25 JST
   - same browser conversation and the same already-attached 40-file bundle
   - Oracle model ID: `gpt-5.5`
   - final capture: 6.97k answer tokens
   - model-picker evidence on the follow-up itself reports requested
     `Thinking 5.5`, resolved unavailable, verified `no`; this is recorded
     rather than overstated. The parent attachment turn had already verified
     `Thinking 5.5`, and Oracle still reports the completed session model as
     `gpt-5.5`.

Answer: `docs/oracle/architecture_review.md`

### Files passed

The parent session packed exactly these 40 files:

- `README.md`
- `pyproject.toml`
- `setup.py`
- `LICENSE`
- `easyeda2kicad/__main__.py`
- `easyeda2kicad/easyeda/easyeda_api.py`
- `easyeda2kicad/easyeda/easyeda_importer.py`
- `easyeda2kicad/kicad/parameters_kicad_symbol.py`
- `easyeda2kicad/metadata/__init__.py`
- `easyeda2kicad/metadata/cache.py`
- `easyeda2kicad/metadata/cad_identity.py`
- `easyeda2kicad/metadata/manifest.py`
- `easyeda2kicad/metadata/merge.py`
- `easyeda2kicad/metadata/models.py`
- `easyeda2kicad/metadata/service.py`
- `easyeda2kicad/metadata/symbol_fields.py`
- `easyeda2kicad/providers/__init__.py`
- `easyeda2kicad/providers/base.py`
- `easyeda2kicad/providers/digikey.py`
- `easyeda2kicad/providers/easyeda.py`
- `easyeda2kicad/providers/lcsc.py`
- `easyeda2kicad/providers/mouser.py`
- `docs/architecture.md`
- `docs/PROVIDER_CONTRACT.md`
- `docs/DECISIONS.md`
- `tests/test_cli_metadata.py`
- `tests/test_cli_metadata_e2e.py`
- `tests/test_easyeda_identity.py`
- `tests/test_metadata_cache.py`
- `tests/test_metadata_manifest_fields.py`
- `tests/test_metadata_merge.py`
- `tests/test_metadata_models.py`
- `tests/test_metadata_service.py`
- `tests/test_provider_base.py`
- `tests/test_provider_digikey.py`
- `tests/test_provider_lcsc_easyeda.py`
- `tests/test_provider_mouser.py`
- `tests/test_custom_fields.py`
- `tests/test_easyeda_api.py`
- `tests/test_regression.py`

### Prompts sent

Parent prompt:

> Act as the independent second designer for this AGPL-3.0 Python 3.9+
> extension of uPesy/easyeda2kicad.py baseline
> fff10a38619963d7cb1c57d779655a9ea4572e95. Review the attached upstream
> architecture, CLI compatibility, Provider boundaries, common models,
> conservative exact MPN matching, LCSC ID and MPN mismatch behavior, DigiKey
> and Mouser authentication and secret boundaries, provider-scoped raw and
> normalized caching, offline and refresh semantics, EasyEDA-only CAD
> responsibility, hidden stable KiCad properties without volatile sales
> fields, manifests and provenance, Windows/Linux paths, AGPL preservation,
> and tests. Find unnecessary refactoring, weak or excessive abstractions,
> false matches, mixed CAD/sales responsibilities, secret leakage, legacy CLI
> or KiCad output breakage, and missing tests. The exact MPN rule is NFKC plus
> uppercase plus outer/internal whitespace handling plus Unicode-dash
> conversion while preserving hyphen underscore slash suffixes and separator
> positions. Classify every actual finding under BLOCKER, SHOULD FIX, or
> OPTIONAL; give affected files, reasoning, smallest compatible fix, and
> distinguish fix-now items from post-implementation checks.

Follow-up prompt:

> Continue the Architecture Review now using the files already attached in
> this ChatGPT conversation. Your previous assistant turn only stated an
> intention to trace the implementation and did not provide the requested
> review. Return the complete review in this response with no process preamble.
> Classify every concrete finding under BLOCKER, SHOULD FIX, or OPTIONAL; for
> each give affected files, reasoning, the smallest backward-compatible fix,
> and whether it must be fixed now or checked after implementation. Explicitly
> cover legacy CLI and KiCad compatibility, Provider and CAD responsibilities,
> exact MPN and LCSC ID verification, DigiKey and Mouser authentication and
> result truncation, raw and normalized cache plus offline and refresh,
> secrets, hidden stable properties without volatile sales data, manifest
> provenance and paths, AGPL-3.0, and test gaps.

### Disposition

The detailed B1–B9, S1–S9, and O1–O3 decision table is in
`docs/DECISIONS.md`.

- Adopted: B1–B7, B9, and S1–S9.
- B8: checked-in C2040 offline goldens plus baseline/current Python 3.9 and
  current-Python Windows evidence were added. Native Linux execution was not
  available and is disclosed to the RC audit as a residual risk.
- O1: deferred; the service cache has one authority while provider methods
  remain compatibility wrappers.
- O2: adopted as documentation cleanup.
- O3: not changed because the image helper predates this extension and the new
  metadata path never calls it.

## Stuck Consultation 001 — manufacturer alias identity

Status: **completed, implemented, and verified**.

- Session: `manufactur-alias-identity-consultati`
- Time: 2026-07-22 21:50:32–21:58:02 JST
- Mode: browser foreground with `--browser-manual-login`
- Oracle model ID: `gpt-5.6`
- Browser picker: requested/resolved `GPT-5.6 Sol`, verified `yes`
- Tokens: 44.64k input, 2.23k output
- Files:
  - `docs/oracle/consultations/001-manufacturer-alias.diff`
  - `docs/oracle/architecture_review.md`
  - `docs/PROVIDER_CONTRACT.md`
  - `docs/architecture.md`
- Answer: `docs/oracle/consultations/001-manufacturer-alias-identity.md`

Prompt sent:

> Stuck Consultation: resolve Architecture Review B1 only. Symptom: with no
> explicit --manufacturer, EasyEDA/LCSC may establish manufacturer display
> `TI(Chinese localized name)` while DigiKey/Mouser return
> `Texas Instruments`; normalize_manufacturer intentionally has no alias table,
> so the same exact MPN produces a manufacturer conflict. Expected: prevent a
> distributor record for a genuinely different manufacturer from being
> attached to the wrong EasyEDA CAD, while still supporting the required
> OPA333AIDBVR and LM321MF/NOPB integrations despite common distributor display
> aliases. Actual current behavior: user-supplied manufacturer is a hard exact
> filter; inferred manufacturer disagreement is retained as a structured
> conflict and the exact-MPN distributor record remains in manifests/symbol
> projection. Architecture Review B1 says exclude every differing inferred
> manufacturer record as MANUFACTURER_UNVERIFIED; doing that also excludes
> legitimate TI alias records and there is no way for the user to provide a
> manufacturer spelling that matches both LCSC/EasyEDA and DigiKey. Tried:
> exact NFKC/punctuation normalization, no fuzzy matching, no alias table,
> structured conflict/provenance, provider-local exact MPN validation,
> conservative ambiguity/truncation handling. Tests cover TI localized display
> versus Texas Instruments and genuine disagreements. There is no runtime error
> log; the design ambiguity is the blocker. Review the scoped diff and
> contracts. Recommend one smallest backward-compatible algorithm, state
> whether the record may appear in distributor_records, BOM, KiCad properties,
> and provenance, and identify any additional evidence that can safely
> distinguish alias from different manufacturer without fuzzy matching.
> Classify as BLOCKER / SHOULD FIX / OPTIONAL and explain whether Architecture
> B1 should stand or be narrowed.

Adopted: Oracle's narrowed B1 rule. Only exact manufacturer names from EasyEDA
and the exact same canonical LCSC catalogue record form the part-scoped evidence
set. Unverified external records are excluded and reported as
`MANUFACTURER_UNVERIFIED`. No fuzzy/global alias table was added. Optional
datasheet hashes/global identifiers were not implemented because they are not
needed for this scope.

## Historical unavailable/stalled attempts

The initial uninitialized-profile failure and subsequent stalled captures are
preserved in `docs/oracle/UNAVAILABLE.md`. They are historical; the Architecture
Review was later recovered. The active failure policy remains: record an Oracle
failure and continue before RC, but do not pass the RC boundary without the
required review.

## Release Candidate Audit

Status: **completed; CANARY PASS / RELEASE BLOCKED**.

The valid answer is stored in
`docs/oracle/release_candidate_audit.md`. It reports one RELEASE BLOCKER, two
SHOULD FIX items, three ACCEPTABLE RISK items, and no required OPTIONAL item.
This was the second and final permitted re-audit, so the current RC cycle stops
for human direction.

### Execution record

- Oracle CLI version: `0.16.0`
- Valid audit session: `easyeda-rc-final-reaudit-2-2`
- Time: 2026-07-23 00:14:00–00:34:52 JST (UTC+09:00)
- Elapsed: 20 minutes 51 seconds
- Engine/mode: browser foreground with `--browser-manual-login`
- Oracle model ID: `gpt-5.6`
- Browser picker: requested/resolved `GPT-5.6 Sol`, verified `yes`
- Usage reported by Oracle: 315,452 input tokens and 2,809 output tokens
- Files received: 20; Oracle created a transient browser attachment bundle,
  which was not copied into the repository
- Candidate snapshot: 62 files, 16,977 lines, 678,259 bytes; SHA-256
  `cf4527f61101258a14cfff487f987a86111da87e453f06760eadb156066a421b`
- Candidate validation: `git apply --cached --check` exit 0 and zero
  high-confidence secret findings
- Source-canary result: **PASS**, including the current cache schema, URL
  sanitizer, MPN-minus set, manufacturer rejection path, truncation errors, and
  dedicated JLCPCB client

### Transport attempts and re-audit count

1. Initial audit, `easyeda-release-candidate-audit`, ran 2026-07-22
   23:06:22–23:46:41 JST. The picker verified `GPT-5.6 Sol`, but Windows `npx`
   did not forward the long `--file` arguments and split the multiline prompt.
   Oracle metadata records zero files and only this transmitted prompt:

   > このeasyeda2kicad拡張のRelease Candidateを監査してください。

   The resulting answer followed stale Architecture context and is preserved
   verbatim in `docs/oracle/release_candidate_audit_attempt1_stale.md`; Codex's
   source-by-source rejection is in
   `docs/oracle/release_candidate_audit_attempt1_disposition.md`.
2. Re-audit 1, `easyeda-rc-audit-reaudit-1`, ran 2026-07-22 23:50:52–2026-07-23
   00:11:47 JST. The same long-option transport defect again produced zero
   files and truncated the actual transmitted prompt to:

   > Release Candidate re-audit 1です。前回回答は、candidate diff内に保存されていた過去のArchitecture Review／consultation diffを最新版と誤認し、既に修正済みのB0-B9/S1-S8を再掲しました。前回回答は release_candidate_audit_attempt1_stale.md に保存し、Codexの現行照合結果は release_candidate_audit_attempt1_disposition.md にあります。

   Oracle correctly declined to classify the current RC without current input.
   The response is saved in
   `docs/oracle/release_candidate_audit_attempt2_input_mismatch.md`.
3. A second-re-audit transport preflight,
   `easyeda-rc-final-reaudit-2`, started at 2026-07-23 00:12:21 JST. Verbose
   evidence immediately showed zero files and a truncated prompt, so it was
   cancelled before an audit answer. It is recorded as a transport failure,
   not counted as a completed review.
4. Re-audit 2/final, `easyeda-rc-final-reaudit-2-2`, used individual short
   `-f` arguments and a single-line prompt in a new conversation. Oracle
   received all 20 files, passed the canary, and completed the valid audit.

Thus the completed review sequence is the initial audit plus re-audits 1 and 2.
The preflight cancellation did not produce a review, and no third re-audit is
being hidden or requested.

### Files passed to the valid final audit

1. `docs/oracle/release_candidate.diff`
2. `docs/oracle/rc2_current_source_canary.md`
3. `docs/oracle/release_candidate_audit_attempt1_disposition.md`
4. `docs/CODEX_RESULT.md`
5. `docs/architecture.md`
6. `docs/PROVIDER_CONTRACT.md`
7. `docs/DECISIONS.md`
8. `docs/oracle/cli_help.txt`
9. `docs/oracle/legacy_compatibility.md`
10. `docs/oracle/secret_audit.md`
11. `docs/oracle/example_validation.md`
12. `docs/examples/OPA333AIDBVR.manifest.json`
13. `docs/examples/LM321MF-NOPB.manifest.json`
14. `docs/examples/CAD_NOT_FOUND.mock.manifest.json`
15. `easyeda2kicad/metadata/cache.py`
16. `easyeda2kicad/metadata/models.py`
17. `easyeda2kicad/metadata/service.py`
18. `easyeda2kicad/providers/digikey.py`
19. `easyeda2kicad/providers/mouser.py`
20. `easyeda2kicad/providers/lcsc.py`

The historical Oracle answers and the consultation diff were intentionally not
part of the authoritative candidate source. The separately named
`docs/oracle/rc2_current_cf4527f6.diff` is a line-equivalent cache-avoidance
copy retained only as transport evidence; the authoritative snapshot is
`docs/oracle/release_candidate.diff`.

### Prompt sent to the valid final audit

> これは規定上2回目かつ最終のRelease Candidate re-auditです。Windows npxで長い--fileがOracleへ渡らない送信障害を特定したため、今回は短い-fで個別添付します。権威入力はrelease_candidate.diff（SHA-256 cf4527f61101258a14cfff487f987a86111da87e453f06760eadb156066a421b）と直接添付した現行ソースです。最初にrc2_current_source_canary.mdを照合し、sanitize_public_url、CACHE_SCHEMA_VERSION = 2、_MPN_MINUS_EQUIVALENTSとMINUS SIGN、MANUFACTURER_UNVERIFIED直後のcontinue、keyword-search-truncated、part-search-truncated、JlcpcbCatalogueClientが全て読める場合だけCANARY PASSとして監査してください。一つでも読めなければORACLE INPUT UNAVAILABLEとして監査しないでください。過去のattachments-bundleやarchitecture_reviewは今回の添付ではないため無視してください。目的は既存CLIとEasyEDA→KiCad変換を壊さずexact MPNを軸にDigiKey・Mouserの販売店メタデータを追加することです。既存CLI互換性、偽exact MPN、LCSC ID/MPN不一致、Provider責務、cache/offline/refresh、秘密漏洩、KiCadへの価格在庫混入、カスタムproperty互換、CAD_NOT_FOUND/--require-cad、Windows/Linux path、テストと文書、侵襲性を確認してください。回答はCANARY CHECKの後、RELEASE BLOCKER / SHOULD FIX / ACCEPTABLE RISK / OPTIONAL / RESOLVEDに分類し、各未解決指摘へ現行ファイル行、最小修正、再監査要否を示してください。前回B0-B9/S1-S8を根拠なく再掲せず、この応答で監査を完結してください。

### Answer files

- Valid final answer: `docs/oracle/release_candidate_audit.md`
- Initial stale-input answer:
  `docs/oracle/release_candidate_audit_attempt1_stale.md`
- Codex validation of that stale answer:
  `docs/oracle/release_candidate_audit_attempt1_disposition.md`
- Re-audit 1 input-mismatch answer:
  `docs/oracle/release_candidate_audit_attempt2_input_mismatch.md`

### Disposition

| Oracle item | Codex decision |
| --- | --- |
| RB-RC2-1: malformed candidates can be discarded before exact selection | **Adopted, unresolved RELEASE BLOCKER.** Source inspection and read-only probes reproduced mixed-candidate acceptance for DigiKey/Mouser and missing/null Mouser `Parts`; LCSC has the same skip structure. A new RC cycle must fail the entire response on any unparseable candidate and add three-provider regression tests. |
| SF-RC2-1: manifest can be an ancestor of CAD output | **Adopted, unresolved SHOULD FIX.** A read-only probe confirmed preflight accepts the reverse containment case. A new RC cycle must reject both directions and test no partial writes. |
| SF-RC2-2: Provider-contract status was stale | **Adopted and corrected.** The status and current conformance gap are now explicit in `docs/PROVIDER_CONTRACT.md`. |
| AR-RC2-1: no credentialed DigiKey/Mouser live run | **Accepted risk.** Credentials were absent; fixture coverage and explicit skips remain documented. |
| AR-RC2-2: no native Linux process E2E | **Accepted risk.** Windows E2E and POSIX unit coverage are recorded without claiming equivalence. |
| AR-RC2-3: 69 inherited reference-output skips | **Accepted risk.** The upstream bundle is absent; the focused checked-in legacy golden remains the available substitute. |
| OPTIONAL | Oracle required none. Future fork/version naming is recorded as possible later work only. |

No finding from the valid final answer was rejected. The initial stale answer was
not adopted because it received no current files and contradicted direct source
and passing tests; the first re-audit made no finding because it detected input
mismatch. Those are transport-invalid attempts, not silently discarded review
opinions. Per D025, the confirmed blocker plus the maximum re-audit count ends
this RC cycle.

## Distinct new RC cycle — 2026-07-23

This section does not reopen or alter the historical RC2 cycle above. The user
authorized a new candidate from RC2's verified source-canary state, with one
initial audit and at most two re-audits.

### Initial audit

- Oracle CLI: `0.16.0`
- Session: `easyeda-new-rc-initial-audit`
- Time: 2026-07-23 16:16:03–16:50:19 JST (UTC+09:00)
- Engine/mode: browser foreground with `--browser-manual-login`
- Requested/resolved model: `GPT-5.6 Sol` / `GPT-5.6 Sol`
- Model picker verification: yes
- Files: 4 individual uploads; bundle mode was not used
- Usage: 201,240 input tokens; 3,790 output tokens
- Candidate: 62 files, 708,139 bytes, SHA-256
  `64b95ce3b63cd281c51e1bb200c8519d769503d69451bcd0b02d7336901a4ecb`
- Pre/post source canary: 20/20 matched
- Answer: `docs/oracle/release_candidate_audit_rc3.md`, SHA-256
  `2a2c63dcbe6c21597bcaaaee42242dd81a2887a1eaef1187ed6efca6135edebb`
- Verdict: **CANARY PASS / RELEASE BLOCKED**

Files:

1. `docs/oracle/rc3_release_candidate.diff`
2. `docs/oracle/rc3_source_canary.md`
3. `docs/oracle/rc3_quality.md`
4. `docs/oracle/rc3_secret_audit.md`

A 21-file dry-run was rejected before submission because Oracle would have
converted it to `attachments-bundle.txt`. The four-file dry-run reported
`bundled: null`, and the complete candidate diff contained all source, tests,
contracts, CLI help, and examples. No bundle or Oracle session cache was copied
to the repository.

Prompt sent:

> This is the INITIAL audit of a newly authorized easyeda2kicad Release Candidate cycle, not a third re-audit of the historical RC2 cycle. RC2 remains permanently closed as CANARY PASS / RELEASE BLOCKED. Use only the four files individually attached to this new conversation; do not use any old Oracle bundle, bundle cache, prior conversation, or stale snapshot. First inspect rc3_source_canary.md, verify candidate SHA-256 64b95ce3b63cd281c51e1bb200c8519d769503d69451bcd0b02d7336901a4ecb and locate every listed invariant in rc3_release_candidate.diff; if the current input is missing or inconsistent, answer ORACLE INPUT UNAVAILABLE and do not audit. The 62-file candidate diff is the complete current candidate and includes source, tests, architecture/contracts/decisions/CODEX_RESULT, CLI help, manifests, and examples. The authorized change scope is only RB-RC2-1, SF-RC2-1, required regression tests, new-RC audit/state/decision records, and preservation of the already-fixed SF-RC2-2 documentation; flag any unrelated refactor, API change, CLI change, output-format change, or dependency update. For RB-RC2-1, verify that DigiKey, Mouser, and LCSC classify each raw candidate MPN before full model conversion; only a provably nonmatching MPN may be excluded; a missing/inaccessible/empty/unnormalizable MPN or a raw exact-MPN candidate that cannot be fully parsed must produce a typed Provider/parse failure and must not degrade to exact success or simple not-found; a provably mismatching candidate with unrelated malformed fields must not unnecessarily reject a valid exact candidate; LCSC ID/MPN validation must remain strict. Verify identical fail-closed semantics for live response, raw-cache replay, normalized cache, offline, and refresh; schema 3 must invalidate unsafe schema-2 normalized entries and invalid exact responses must not be cached. For SF-RC2-1, verify normalized relative/absolute/dot/dot-dot and Windows-aware path comparison rejects a manifest file path equal to or ancestral to the CAD output directory before CAD, manifest, cache, or other persistent output begins; a normal manifest child and adjacent same-prefix path must remain allowed; collision must leave no partial output. Also audit existing CLI compatibility, EasyEDA-to-KiCad behavior, exact-MPN false positives, Provider responsibility separation, credential leakage, absence of price/stock in KiCad symbols, custom-property compatibility, CAD_NOT_FOUND/--require-cad behavior, Windows/Linux paths, test sufficiency, documentation/code agreement, and invasiveness. Quality evidence reports focused 22 passed, related 252 passed, and Python 3.9/3.12/3.14 each 687 passed and 71 skipped, plus Ruff, strict mypy, diff/apply checks, and secret audit PASS. Preserve as existing ACCEPTABLE RISK unless new concrete evidence changes them: 69 inherited reference-output skips, unrun credentialed DigiKey/Mouser real APIs, and unrun native Linux E2E. Begin with CANARY PASS or ORACLE INPUT UNAVAILABLE. Then classify every finding as RELEASE BLOCKER / SHOULD FIX / ACCEPTABLE RISK / OPTIONAL / RESOLVED, with stable IDs, exact file/evidence references, the smallest required fix, and the re-audit requirement. Do not silently carry forward an old finding: re-establish it from this candidate. End with a single release verdict.

Disposition:

| Finding | Codex decision |
| --- | --- |
| `RB-RC3-1` untyped numeric overflow | **Adopted and fixed.** Common Provider/model/cache/service boundaries now preserve typed failure semantics; three-Provider and cache-mode tests were added. |
| `SF-RC3-1` manifest below symbol file | **Adopted and fixed.** The symbol output is an explicit file and rejects both containment directions before output. |
| `DOC-RC3-1` historical rows labelled current | **Adopted and fixed.** Rows are labelled `RC2 pre-RC3 tree`. |
| `AR-RC3-1` through `AR-RC3-3` | **Accepted risks retained.** No new evidence changed the inherited skips, credentialed live-run, or Linux E2E limitations. |
| OPTIONAL | None. |

### Re-audit 1

- Oracle CLI: `0.16.0`
- Session: `easyeda-new-rc-reaudit-one`
- Time: 2026-07-23 17:08:00–17:22:34 JST (UTC+09:00)
- Engine/mode: browser foreground with `--browser-manual-login`
- Requested/resolved model: `GPT-5.6 Sol` / `GPT-5.6 Sol`
- Model picker verification: yes
- Files: 10 individual uploads; bundle mode was not used
- Usage: 46,480 input tokens; 1,890 output tokens
- Revised audited candidate: 63 files, 723,055 bytes, SHA-256
  `2c25cedc3f3720a3c9b54bc8563688b993d988e5ab75ba6791dc9c24dc23e6c5`
- Initial-to-revised delta: 19 files, 37,269 bytes, SHA-256
  `695245d3ddde1a8607af0d17ac887170b7c8de0eb7b6861fa113201260a62b68`
- Pre/post source canary: 20/20 matched
- Answer: `docs/oracle/release_candidate_audit_rc3_reaudit1.md`, SHA-256
  `5fcc6f18d4f6f204e28ac82953cffa1592303f44a0b64d009a4e1935bf05e720`
- Verdict: **CANARY PASS / no RELEASE BLOCKER / RELEASE APPROVED**, subject
  only to the non-blocking `DOC-RC3-1` pointer correction

Files:

1. `docs/oracle/rc3_reaudit1_source_canary.md`
2. `docs/oracle/rc3_reaudit1_delta_from_initial.diff`
3. `docs/oracle/release_candidate_audit_rc3.md`
4. `docs/oracle/rc3_reaudit1_quality.md`
5. `docs/oracle/rc3_reaudit1_secret_audit.md`
6. `easyeda2kicad/providers/base.py`
7. `easyeda2kicad/metadata/cache.py`
8. `easyeda2kicad/metadata/service.py`
9. `easyeda2kicad/__main__.py`
10. `tests/test_cli_metadata.py`

A 21-file dry-run again detected automatic bundle conversion and was not sent.
The ten-file dry-run reported `bundled: null` and approximately 45,731 tokens.
The delta contained every Provider/model/test/contract change not attached as
an individual current file.

Prompt sent:

> This is RE-AUDIT 1 of the separately authorized new easyeda2kicad RC cycle. It is not RC2 and not a third RC2 re-audit; historical RC2 remains closed as CANARY PASS / RELEASE BLOCKED. Use only the ten files individually attached to this new conversation and do not use an old Oracle bundle, bundle cache, prior conversation, or stale snapshot. Begin by verifying rc3_reaudit1_source_canary.md, the delta SHA-256 695245d3ddde1a8607af0d17ac887170b7c8de0eb7b6861fa113201260a62b68, the revised full-candidate SHA-256 2c25cedc3f3720a3c9b54bc8563688b993d988e5ab75ba6791dc9c24dc23e6c5 recorded there, and every listed fix invariant against the attached current source and delta; if current input is absent or inconsistent, answer ORACLE INPUT UNAVAILABLE and do not audit. The initial new-RC answer is attached and must be used only to identify RB-RC3-1, SF-RC3-1, DOC-RC3-1, and the unchanged accepted risks. Re-establish each disposition from the revised source and tests. For RB-RC3-1, verify overflowing or non-finite numeric data cannot escape as untyped OverflowError at raw exact candidate parsing, model reconstruction, cache validation, service reconstruction, live-shaped execution, raw replay, normalized online/offline, or refresh; failures must retain typed Provider/cache semantics and publish no invalid cache success. Verify DigiKey, Mouser, and LCSC coverage in the attached delta. For SF-RC3-1, verify symbol output is treated as a file and a manifest equal to, ancestral to, or below that file is rejected before metadata, CAD, manifest, cache, or parent output; verify normal manifest children of footprint/3D/SVG directories and adjacent prefixes remain allowed, and JSON/CSV tests leave no partial output. For DOC-RC3-1, verify 666-pass rows are labelled historical RC2 and current quality points to 695 passed. Check that the changes remain limited to the authorized RB-RC2-1/SF-RC2-1 scope and introduce no API, CLI spelling, output-format, dependency, cache-schema, Provider/CAD responsibility, exact-MPN, LCSC-ID/MPN, or legacy conversion regression. The authoritative quality evidence is 8 blocker probes, 280 related tests, and Python 3.9/3.12/3.14 each 695 passed and 71 skipped, plus Ruff, strict mypy, diff/apply, and secret audit PASS. Preserve AR-RC3-1 through AR-RC3-3 as ACCEPTABLE RISK unless new concrete evidence changes them: 69 inherited reference-output skips, unrun credentialed DigiKey/Mouser APIs, and unrun native Linux process E2E. Begin with CANARY PASS or ORACLE INPUT UNAVAILABLE. Then classify all items as RELEASE BLOCKER / SHOULD FIX / ACCEPTABLE RISK / OPTIONAL / RESOLVED with stable IDs and exact evidence. If no release blocker remains, state that explicitly and end with one release verdict. If a blocker remains, give the smallest in-scope fix and re-audit requirement.

Disposition:

| Finding | Codex decision |
| --- | --- |
| `RB-RC3-1` | **RESOLVED.** Accepted after current source/test verification. |
| `SF-RC3-1` | **RESOLVED.** Accepted after current preflight and no-output test verification. |
| `COMP-RC3-1` | **RESOLVED.** No public API, CLI, output-format, dependency, schema, or Provider/CAD-boundary change was found. |
| `QG-RC3-1` | **RESOLVED.** Quality and integrity evidence matched. |
| `DOC-RC3-1` stale quality pointer | **Adopted and corrected.** The pointer now names `rc3_reaudit1_quality.md`; all three full suites were rerun. Oracle explicitly required regenerated diff/apply and secret checks, not another model re-audit. |
| `AR-RC3-1` through `AR-RC3-3` | **Accepted risks retained.** |
| OPTIONAL | None. |

No Oracle finding in either valid new-cycle answer was rejected. Re-audit 2 was
not used because re-audit 1 found no release blocker and explicitly made the
only remaining document correction non-blocking and non-re-audit-requiring.

## Public-beta corrective RC cycle — 2026-07-23

This is a distinct cycle after the preserved RC3 approval. The real Symbol
Fields Table audit required runtime changes, so the RC3 approval was not reused.
The cycle allows one initial audit and, if needed, at most two re-audits.

### Initial audit

- Oracle CLI: `0.16.0`
- Session: `easyeda-beta-corrective-audit`
- Time: 2026-07-23 18:49:12–19:12:25 JST (UTC+09:00)
- Elapsed: 23 minutes 13 seconds
- Engine/mode: browser foreground with `--browser-manual-login`
- Requested/resolved model: `GPT-5.6 Sol` / `GPT-5.6 Sol`
- Model picker verification: yes
- Files: 10 individual uploads; bundle mode was not used
- Dry-run transport: `inlineFileCount: 0`, `bundled: null`
- Usage: approximately 252,010 input tokens and 2,150 output tokens
- Candidate: 68 files, 750,327 bytes, SHA-256
  `5c848efe9e3dcbbb4dcc632f150cca0e7e824384230de250a18e644a907945d3`
- RC3-to-candidate delta: 17 files, 64,625 bytes, SHA-256
  `04004f17a6a90cf0c308acb3d3a11696163bbe98c96cf9100dab000a7420c3d7`
- Candidate tree: `0c7b7f01e3389ef7efbecec40574619d292bdf78`
- Pre/post canary: 10/10 direct attachments and 17/17 source-table entries
- Answer: `docs/oracle/release_candidate_audit_beta1.md`, SHA-256
  `b81d034ac0579294cc13a901320823e9b917f2a78b97ba905ac2573abebb65f7`
- Verdict: **CANARY PASS / no RELEASE BLOCKER / RELEASE APPROVED**

Files:

1. `docs/oracle/beta1_source_canary.md`
2. `docs/oracle/beta1_release_candidate.diff`
3. `docs/oracle/beta1_delta_from_rc3.diff`
4. `docs/oracle/beta1_quality.md`
5. `docs/oracle/beta1_secret_audit.md`
6. `docs/FIELD_TABLE_AUDIT.md`
7. `easyeda2kicad/metadata/symbol_fields.py`
8. `easyeda2kicad/metadata/service.py`
9. `easyeda2kicad/__main__.py`
10. `easyeda2kicad/kicad/export_kicad_symbol.py`

The Oracle answer was first written to a temporary path outside the repository.
Only the final assistant response was preserved. No Oracle profile, session
cache, authentication material, or bundle was copied into the source tree.

Prompt sent:

> This is the INITIAL Release Candidate audit of a distinct public-beta
> corrective cycle for easyeda2kicad +DigiMou. Historical RC2 remains closed
> CANARY PASS / RELEASE BLOCKED and preserved RC3 remains unchanged; this is
> not another audit of either old cycle. Use only the ten current files
> individually attached to this new conversation. Do not use bundle mode, any
> old bundle cache, prior conversation, or stale snapshot. First verify
> beta1_source_canary.md, full candidate SHA-256
> 5c848efe9e3dcbbb4dcc632f150cca0e7e824384230de250a18e644a907945d3,
> delta SHA-256
> 04004f17a6a90cf0c308acb3d3a11696163bbe98c96cf9100dab000a7420c3d7,
> candidate tree 0c7b7f01e3389ef7efbecec40574619d292bdf78, and every
> listed invariant against the attached files. If input is absent or
> inconsistent, begin ORACLE INPUT UNAVAILABLE and do not audit. Audit the
> native-only KiCad field projection, Manifest-only Provider/volatile data,
> actual OPA333AIDBVR and LM321MF/NOPB byte/idempotency evidence, fail-closed
> part-scoped manufacturer proof, native collision policy, slash-bearing
> overwrite identity, compatibility, cache/path/secret boundaries, the
> 702-passed/71-skipped quality matrix, and the three unchanged accepted risks.
> Begin with CANARY PASS or ORACLE INPUT UNAVAILABLE; classify RELEASE BLOCKER /
> SHOULD FIX / ACCEPTABLE RISK / OPTIONAL / RESOLVED with stable IDs and finish
> with one explicit release verdict.

Disposition:

| Finding | Codex decision |
| --- | --- |
| `B1-FT-01`, `B1-FT-02` | **RESOLVED.** Native-only KiCad fields and Manifest completeness were verified. |
| `B1-MAN-01` | **RESOLVED.** Same-ID/exact-MPN/exact-manufacturer LCSC proof is mandatory and fail-closed. |
| `B1-ID-01` | **RESOLVED.** Existing nonempty identity is never silently replaced. |
| `B1-SYM-01` | **RESOLVED.** Sanitized serialized symbol identity is used consistently. |
| `B1-BYTE-01` | **RESOLVED.** Real legacy/metadata and repeated-output hashes match. |
| `B1-COMP-01`, `B1-QA-01` | **RESOLVED.** Scope, compatibility, secrets, and quality evidence matched. |
| `B1-AR-01` through `B1-AR-03` | **Accepted risks retained.** |
| RELEASE BLOCKER / SHOULD FIX / OPTIONAL | None. |

No initial-audit finding was rejected. Release preparation later changed
version/package metadata and added release documentation/templates, so the
revised tag candidate is sent as re-audit 1 rather than silently inheriting
this approval.

### Re-audit 1

- Oracle CLI: `0.16.0`
- Session: `easyeda-beta-release-reaudit`
- Time: 2026-07-23 19:32:53–19:43:19 JST (UTC+09:00)
- Elapsed: 10 minutes 26 seconds
- Engine/mode: browser foreground with `--browser-manual-login`
- Requested/resolved model: `GPT-5.6 Sol` / `GPT-5.6 Sol`
- Model picker verification: yes
- Files: 7 individual uploads; bundle mode was not used
- Usage: approximately 247,340 input tokens and 2,470 output tokens
- Revised candidate: 74 files, 803,147 bytes, SHA-256
  `93f312f93119140709116d036597d9e4ca78f3e97879e2ef644b9784c5474bf4`
- Initial-to-revised delta: 12 files, 63,485 bytes, SHA-256
  `68187df63a7a093d536c4d48232b56fd2482a37366f4684f959cf946daf84f25`
- Revised audited source tree:
  `334715a99d5ee514338199e27e685db1a78de81e`
- Post-answer canary: 23/23 table entries, 7/7 direct attachments, package
  input tree exact
- Answer: `docs/oracle/release_candidate_audit_beta1_reaudit1.md`, SHA-256
  `59f03f9d8a93a8b1c0c60db6a95fbcd9bb656f44ad30617f07489b388d80fa7b`
- Verdict: **CANARY PASS / no RELEASE BLOCKER / RELEASE READY**

Files:

1. `docs/oracle/beta1_reaudit1_source_canary.md`
2. `docs/oracle/beta1_reaudit1_release_candidate.diff`
3. `docs/oracle/beta1_reaudit1_delta_from_initial.diff`
4. `docs/oracle/release_candidate_audit_beta1.md`
5. `docs/oracle/beta1_reaudit1_quality.md`
6. `docs/oracle/beta1_reaudit1_secret_audit.md`
7. `.github/workflows/publish.yml`

An eleven-file dry-run was rejected before submission because Oracle would have
converted it to `attachments-bundle.txt`. The seven-file dry-run reported
`bundled: null`; README, setup, version, release notes, NOTICE, issue form, and
security policy remained available in both the full candidate and the small
release-prep delta.

Prompt sent:

> This is RE-AUDIT 1 of the distinct public-beta corrective RC cycle for
> easyeda2kicad +DigiMou. It is not RC2, not RC3, and not a reuse of either
> historical approval. Use only the seven current files individually attached;
> do not use bundle mode, old bundle cache, or a stale snapshot. First verify
> the source canary, revised full candidate SHA-256
> 93f312f93119140709116d036597d9e4ca78f3e97879e2ef644b9784c5474bf4,
> release-prep delta SHA-256
> 68187df63a7a093d536c4d48232b56fd2482a37366f4684f959cf946daf84f25,
> source tree 334715a99d5ee514338199e27e685db1a78de81e, and every
> invariant. Re-establish the unchanged B1 runtime findings, audit the exact
> 12-path release-prep delta, PEP 440 version/tag, unchanged Python identities,
> unofficial/AGPL attribution, exact-MPN/Manifest/cache/KiCad documentation,
> credential and issue/security boundaries, no-PyPI plan, inherited
> `publish.yml`, complete 702/71/build/install/content/checksum/secret evidence,
> and the three unchanged accepted risks. Begin CANARY PASS or ORACLE INPUT
> UNAVAILABLE; classify RELEASE BLOCKER / SHOULD FIX / ACCEPTABLE RISK /
> OPTIONAL / RESOLVED and end with one commit/tag/manual-pre-release verdict.

Disposition:

| Finding | Codex decision |
| --- | --- |
| `B1-RA1-CAN-01` | **RESOLVED.** All identity and canary evidence matched. |
| Initial `B1-*` findings | **RESOLVED.** Protected runtime/test hashes are unchanged. |
| `B1-RA1-VERSION-01` | **RESOLVED.** Version/tag and stable Python identities are correct. |
| `B1-RA1-DOC-01` | **RESOLVED.** Attribution, behavior, credentials, and no-PyPI scope are clear. |
| `B1-RA1-ISSUE-01` | **RESOLVED.** Debug form and private security path are safe. |
| `B1-RA1-ART-01`, `B1-QA-01` | **RESOLVED.** Quality/build/install/content/hash/secret evidence matched. |
| `B1-RA1-PUB-01` | **Adopted.** Do not push the version-changing commit to `master`; feature branch, annotated tag, and manual pre-release are safe. |
| `B1-AR-01` through `B1-AR-03` | **Accepted risks retained.** |
| RELEASE BLOCKER / SHOULD FIX / OPTIONAL | None. |

No finding was rejected. Re-audit 2 is not required. The answer permits commit,
push of `feature/multi-distributor-metadata`, annotated tag `v1.1.0b1`, and a
manual GitHub pre-release without PyPI after the matching post-answer canary.

## 1.1.0b3 release-candidate cycle — 2026-07-30

This is a distinct audit cycle for the `1.1.0b3` GitHub pre-release candidate.
It does not reuse an earlier release approval.

### Initial audit

- Oracle CLI: `0.16.1`
- Session: `digimou-b3-final-audit`
- Engine/mode: browser foreground with `--browser-manual-login`
- Requested/resolved model: `Thinking 5.5` / `Thinking 5.5`
- Model picker verification: yes
- Files: 10 individual uploads; bundle mode was not used
- Usage: approximately 50,320 input tokens
- Answer: `docs/oracle/release_candidate_audit_b3.md`
- Verdict: **CANARY PASS / RELEASE BLOCKED**

The valid answer reported five RELEASE BLOCKER and three SHOULD FIX items. All
eight were adopted. The fixes keep artifact-level fallback in the CLI-owned
path, require one handoff to contain every requested artifact, remove
evidence-free SamacSys attribution, redact configured secrets from every human
log handler, and bound the README monitor to safe counts and option names.
The monitor also treats ordinary production Python/schema changes as requiring
README review, excludes tag refs, and has hostile-input plus fallback-matrix
coverage.

The post-fix focused matrix reports `73 passed`; the full deterministic suite
reports `1003 passed, 77 skipped`. Ruff lint/format passes for 96 files, strict
mypy passes for 43 source files, both distributions pass Twine validation, and
an isolated wheel installation reports `1.1.0b3` with all three schemas.

The Windows transport failures and a login-only helper that accidentally used
Oracle's Pro default are recorded in
`docs/oracle/b3_transport_and_budget_incident.md`. The helper received only the
two-character setup prompt `HI`, no source and no audit instructions. It is not
treated as an audit. Every valid b3 audit command explicitly selects the
standard `gpt-5.5` model.

### Re-audit 1

- Session: `digimou-b3-reaudit-one`
- Elapsed: 10 minutes 36 seconds
- Engine/mode: browser foreground with `--browser-manual-login`
- Requested/resolved model: `Thinking 5.5` / `Thinking 5.5`
- Model picker verification: yes
- Files: 10 individual uploads; dry-run confirmed `bundled: null`
- Usage: approximately 50,850 input and 2,610 output tokens
- Answer: `docs/oracle/release_candidate_audit_b3_reaudit1.md`
- Verdict: **CANARY PASS / RELEASE BLOCKED**

Re-audit 1 confirmed that all five initial RELEASE BLOCKER items and all three
initial SHOULD FIX items were corrected. It found one new blocker: a parsed
symbol with zero electrical pins or a parsed footprint with zero numbered
electrical pads could bypass semantic invalidity and artifact-level fallback.
That boundary is now fixed for symbol-only, footprint-only, and full requests;
the invalid parsed member becomes the exact missing artifact, while a true
pin/pad mismatch continues to replace both members. A neutral no-match
fallback remains fail-closed.

The non-blocking monitor recommendation was also adopted. Commit subjects are
no longer collected by repository inspection, changed-path inspection has a
10,000-path fail-closed limit, and issue deduplication inspects at most the 100
most recently updated issues.

The post-fix focused matrix reports `79 passed`; the full deterministic suite
reports `1009 passed, 77 skipped`. Re-audit 2 was required because re-audit 1
found a new release blocker.

### Re-audit 2 and post-answer disposition

- Valid session: `digimou-b3-final-reaudit-two-4`
- Engine/mode: browser foreground with `--browser-manual-login`
- Requested Oracle model ID: `gpt-5.6`, an available non-Pro standard model
- Picker evidence: requested/resolved `GPT-5.6 Sol`, verified `yes`
- Answer model statement: active `GPT-5.6 Thinking`, non-Pro
- Files: 7 individual uploads; dry-run confirmed `bundled: null`
- Usage: approximately 30,170 input and 1,640 output tokens
- Answer: `docs/oracle/release_candidate_audit_b3_reaudit2.md`
- Verdict at answer time: **CANARY PASS / RELEASE BLOCKED**

Re-audit 2 confirmed `RB-B3-R1` resolved and found no remaining product-path
release blocker. It kept `SF-B3-R1` open because `_git_paths()` still captured
the complete `git diff --name-only -z` stdout before enforcing the 10,000-path
limit. The answer supplied an exact five-step minimum correction and explicitly
said no further Oracle review was requested.

That minimum correction is implemented after the answer. `_git_paths()` now
reads stdout in 64 KiB chunks, retains at most the bounded path set, and
terminates then reaps Git on the first over-limit entry. The same reader serves
ordinary and added-only queries. Its regression drives the actual reader with
an oversized chunked producer and proves termination, waiting, stdout closure,
and unread trailing data. The pre-existing inspection-level limit remains as a
defense in depth.

After the correction, the focused matrix reports `80 passed`; the full suite
reports `1010 passed, 77 skipped`. Ruff lint/format, strict mypy, build, Twine,
and isolated-wheel version/content checks all pass. This satisfies the final
answer's exact minimum fixes without requesting an unauthorized third
re-audit.
