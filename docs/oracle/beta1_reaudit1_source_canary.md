# Public-beta release-prep re-audit 1 source canary

Generated: 2026-07-23 (Asia/Tokyo)

This is re-audit 1 of the distinct public-beta corrective RC cycle. Historical
RC2 remains closed as `CANARY PASS / RELEASE BLOCKED`; preserved RC3 remains
unchanged. The valid initial public-beta answer is
`docs/oracle/release_candidate_audit_beta1.md` and reported `CANARY PASS`, no
release blocker, and `RELEASE APPROVED`.

Release preparation changed version/package metadata and public documentation,
so the initial answer is not silently reused for the final tag candidate.

## Candidate identity

- upstream baseline:
  `fff10a38619963d7cb1c57d779655a9ea4572e95`;
- initial public-beta candidate tree:
  `0c7b7f01e3389ef7efbecec40574619d292bdf78`;
- revised audited source tree:
  `334715a99d5ee514338199e27e685db1a78de81e`;
- revised full candidate: 74 files, 803,147 bytes, SHA-256
  `93f312f93119140709116d036597d9e4ca78f3e97879e2ef644b9784c5474bf4`;
- initial-to-revised release-prep delta: 12 files, 63,485 bytes, SHA-256
  `68187df63a7a093d536c4d48232b56fd2482a37366f4684f959cf946daf84f25`;
- clean temporary-index candidate apply and applied-tree equality: PASS;
- clean build-snapshot package inputs equal revised candidate package inputs:
  PASS.

The revised candidate deliberately excludes generated Oracle answer/canary,
secret-audit, and nested candidate-diff artifacts from its source tree. Those
records remain preserved in the repository and are attached individually where
needed. This prevents recursive diff growth without omitting runtime, tests,
public release files, architecture/contracts/decisions, or state documents.

## Direct Oracle attachments

Use these seven files as individual `-f` attachments in one continuation of the
new-cycle review. Do not use bundle mode, an old bundle cache, or a stale
conversation snapshot.

1. `docs/oracle/beta1_reaudit1_source_canary.md`
2. `docs/oracle/beta1_reaudit1_release_candidate.diff`
3. `docs/oracle/beta1_reaudit1_delta_from_initial.diff`
4. `docs/oracle/release_candidate_audit_beta1.md`
5. `docs/oracle/beta1_reaudit1_quality.md`
6. `docs/oracle/beta1_reaudit1_secret_audit.md`
7. `.github/workflows/publish.yml`

README, setup, version, release notes, the issue form, security policy, NOTICE,
and all other release-prep files are present in both revised diff files and
named in the table below.

## SHA-256 table

| File | SHA-256 |
| --- | --- |
| `docs/oracle/beta1_reaudit1_release_candidate.diff` | `93f312f93119140709116d036597d9e4ca78f3e97879e2ef644b9784c5474bf4` |
| `docs/oracle/beta1_reaudit1_delta_from_initial.diff` | `68187df63a7a093d536c4d48232b56fd2482a37366f4684f959cf946daf84f25` |
| `docs/oracle/release_candidate_audit_beta1.md` | `b81d034ac0579294cc13a901320823e9b917f2a78b97ba905ac2573abebb65f7` |
| `docs/oracle/beta1_reaudit1_quality.md` | `2e698b6d9b8f916c526f169dc546a5f6a67a8a309ddaa137a071fe8a31b5659b` |
| `docs/oracle/beta1_reaudit1_secret_audit.md` | `b7acf67e4088f1b604e17e6600fe72d72f2a63f2719a93d1ea0d598be6deecb3` |
| `README.md` | `abbc3e63a7ac0653dc907fc71f260c1f679083cc8a977fdf9a9a2f12f29d23cf` |
| `NOTICE` | `bcea3811643bbd866db870d7671a0952aa620af4875d42be3040b88598477b2d` |
| `setup.py` | `243cdab3570e367897fec01302ee735e36491ec3afc9af382eb98762736b16fc` |
| `easyeda2kicad/_version.py` | `85ff8b512a6941881e5afc41e9e5f360f4eec9041e1d35af7790ab36527daa71` |
| `docs/releases/v1.1.0b1.md` | `ec4615ae81bda5cc90fabd76a4bc9c37e8e3d8dc7b4d714c7f199ac031076b32` |
| `.github/ISSUE_TEMPLATE/bug_report.yml` | `152dfd428a61da7045c92d7a2c7cacaba0c01f6852c2f39cc0d36f28fcd6f95f` |
| `.github/ISSUE_TEMPLATE/config.yml` | `8f89dfe1103f427afea3d9eeda0585b0652356e1ae5e43de9ed3a1cc05fbed9f` |
| `SECURITY.md` | `c6af052094568fb5015baae4131bf75aa22a4a62507ccf6ee4397c4b9192c7d7` |
| `.github/workflows/publish.yml` | `60099b0ebe117f9fdda6c8a19bb49e320c301fbe62ca1d24d608329a5a0c77f4` |
| `easyeda2kicad/metadata/symbol_fields.py` | `831123695997468dfa15d3f485668089a891ed73b71a70511e172c755e24bf24` |
| `easyeda2kicad/metadata/service.py` | `75e1c186e4893d5fd137d12f708f1a9c9f8db526ce2ef08d9a9b503a4f160d06` |
| `easyeda2kicad/__main__.py` | `f8cfcaddf5f74ec4ae7db83c05d92ef9733ad7b83d3c08f30d35788f2089626b` |
| `easyeda2kicad/kicad/export_kicad_symbol.py` | `299255e1ed112bc7ddef6977c5ce0d5014fb4026933146ebb64e8037c4098361` |
| `tests/test_metadata_manifest_fields.py` | `04407e82c5fcde504b64fb4fa6c455ec9f568a7a3c499f9b4069d1d259c1ca1f` |
| `tests/test_custom_fields.py` | `eaaf3d333763256be9ca7021e47c3df1d6b9d9887d1fc20af6d62eee1b970bf1` |
| `tests/test_metadata_service.py` | `de24d384661695055746aa3d0a0a4f3aca35a9e70da892fe5ac9ef3543d2718a` |
| `tests/test_symbol_lib_helpers.py` | `d1c1df8c771b89a422014e65741197d29230f3457bc62f800374dea0fb2a14f2` |

## Required invariants

Oracle should report `ORACLE INPUT UNAVAILABLE` instead of auditing if any
direct attachment is absent, either revised diff hash differs, or the following
cannot be established from the attached current files:

1. Every `B1-*` resolved item from the initial answer remains unchanged; the
   four runtime and four focused test hashes above match the initial canary.
2. The version is PEP 440 `1.1.0b1`, which follows stable `1.0.1`; the intended
   annotated tag is `v1.1.0b1`.
3. The distribution/import/CLI name and entrypoint remain `easyeda2kicad`;
   only the display name and GitHub slug identify +DigiMou.
4. README/NOTICE/setup clearly identify an unofficial AGPL-3.0 derivative at
   upstream baseline `fff10a3`, explain exact-MPN fail-closed behavior,
   manifests/cache/offline/refresh, native-only KiCad projection, environment
   credentials, and no credential persistence.
5. DigiKey/Mouser/LCSC are not presented as endorsing or owning this project.
   PyPI is explicitly excluded from the beta release.
6. The issue form requests the required environment/reproduction fields and
   forbids API keys, secrets, tokens, Authorization headers, credential URLs,
   and raw cache. Security reports have a private route.
7. Python 3.9/3.12/3.14 each report `702 passed, 71 skipped`; Ruff, 59-file
   strict mypy, diff/apply, build, dual fresh-venv install, CLI help, explicit
   fixtures, worktree-leak, source secret, and release artifact secret gates
   pass.
8. The sdist/wheel contain LICENSE, NOTICE, and required package modules, omit
   tests/cache/Oracle/credential/build material, and have the SHA-256 values in
   the quality record.
9. The accepted risks remain exactly: 69 inherited reference-output skips,
   unrun credentialed DigiKey/Mouser live E2E, and unrun native Linux process
   E2E.

Recompute every table entry immediately after the Oracle answer. Any mismatch
is `SOURCE CANARY FAIL` and invalidates the answer.
