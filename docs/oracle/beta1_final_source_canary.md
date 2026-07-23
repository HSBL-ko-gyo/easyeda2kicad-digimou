# Public-beta final source canary

Generated: 2026-07-23 (Asia/Tokyo)

## Audited release source

- upstream baseline:
  `fff10a38619963d7cb1c57d779655a9ea4572e95`;
- initial public-beta candidate SHA-256:
  `5c848efe9e3dcbbb4dcc632f150cca0e7e824384230de250a18e644a907945d3`;
- revised release-prep candidate SHA-256:
  `93f312f93119140709116d036597d9e4ca78f3e97879e2ef644b9784c5474bf4`;
- release-prep delta SHA-256:
  `68187df63a7a093d536c4d48232b56fd2482a37366f4684f959cf946daf84f25`;
- revised audited source tree:
  `334715a99d5ee514338199e27e685db1a78de81e`.

Oracle re-audit 1 answer:

- file: `docs/oracle/release_candidate_audit_beta1_reaudit1.md`;
- SHA-256:
  `59f03f9d8a93a8b1c0c60db6a95fbcd9bb656f44ad30617f07489b388d80fa7b`;
- verdict: `CANARY PASS`;
- RELEASE BLOCKER: none;
- SHOULD FIX: none;
- OPTIONAL: none;
- release verdict: ready to commit, annotated-tag, and publish manually as a
  GitHub pre-release without PyPI.

The mandatory post-answer checks passed:

- source hash table: 23/23 matched;
- direct Oracle attachments: 7/7 matched;
- current package inputs re-added to the audited candidate tree: exact tree
  equality;
- no package/runtime/test file changed after the answer.

## Post-audit evidence-only delta

The answer, disposition, and preserved audit artifacts were added after the
model response. Relative to audited source tree
`334715a99d5ee514338199e27e685db1a78de81e`:

- evidence tree before this final canary:
  `2a1e22d06955bca2aab544e85f9152e2d48586af`;
- document-only delta: 41 files, 5,705,115 bytes;
- delta file: `docs/oracle/beta1_final_post_audit_doc_delta.diff`;
- delta SHA-256:
  `97223d4d80c3ac587858d00e181a1f7b9a3f575ddbdfc639f237bd634c24f61c`;
- every changed path is under `docs/`;
- clean temporary-index apply reproduced the evidence tree exactly;
- high-confidence secret scan: zero matches.

The large size is archival: the delta preserves the historical RC2/RC3 and
public-beta Oracle evidence already required by the review policy. It contains
no release runtime, package metadata, test, build, cache, profile, or
credential change.

## Protected current hashes

| File | SHA-256 |
| --- | --- |
| `README.md` | `abbc3e63a7ac0653dc907fc71f260c1f679083cc8a977fdf9a9a2f12f29d23cf` |
| `NOTICE` | `bcea3811643bbd866db870d7671a0952aa620af4875d42be3040b88598477b2d` |
| `setup.py` | `243cdab3570e367897fec01302ee735e36491ec3afc9af382eb98762736b16fc` |
| `easyeda2kicad/_version.py` | `85ff8b512a6941881e5afc41e9e5f360f4eec9041e1d35af7790ab36527daa71` |
| `easyeda2kicad/metadata/symbol_fields.py` | `831123695997468dfa15d3f485668089a891ed73b71a70511e172c755e24bf24` |
| `easyeda2kicad/metadata/service.py` | `75e1c186e4893d5fd137d12f708f1a9c9f8db526ce2ef08d9a9b503a4f160d06` |
| `easyeda2kicad/__main__.py` | `f8cfcaddf5f74ec4ae7db83c05d92ef9733ad7b83d3c08f30d35788f2089626b` |
| `easyeda2kicad/kicad/export_kicad_symbol.py` | `299255e1ed112bc7ddef6977c5ce0d5014fb4026933146ebb64e8037c4098361` |
| `tests/test_metadata_manifest_fields.py` | `04407e82c5fcde504b64fb4fa6c455ec9f568a7a3c499f9b4069d1d259c1ca1f` |
| `tests/test_custom_fields.py` | `eaaf3d333763256be9ca7021e47c3df1d6b9d9887d1fc20af6d62eee1b970bf1` |
| `tests/test_metadata_service.py` | `de24d384661695055746aa3d0a0a4f3aca35a9e70da892fe5ac9ef3543d2718a` |
| `tests/test_symbol_lib_helpers.py` | `d1c1df8c771b89a422014e65741197d29230f3457bc62f800374dea0fb2a14f2` |

## Quality and release artifacts

- Python 3.9.25: `702 passed, 71 skipped`;
- Python 3.12.13: `702 passed, 71 skipped`;
- Python 3.14.3: `702 passed, 71 skipped`;
- Ruff format/lint: PASS;
- strict mypy over 59 files: PASS;
- `git diff --check`: PASS;
- clean build, wheel install, sdist install, installed CLI help, explicit
  legacy/metadata/Manifest fixtures, source/artifact secret audit: PASS.

| Release artifact | SHA-256 |
| --- | --- |
| `easyeda2kicad-1.1.0b1.tar.gz` | `f14db949c2d3c5b7bc4e262183b1f14a8eea19e5129ddb8e90839dea8c221e32` |
| `easyeda2kicad-1.1.0b1-py3-none-any.whl` | `13b52e840ebab29b2cf8bec1de5ebb0136d171a7634baa843cb02f4261fa2be7` |
| `RELEASE_NOTES.md` | `6d82b61b7c48907bc8b7426782be5e5959547f743494f98c415bbb9b42746993` |
| `CLI_HELP.txt` | `5116b3d38867f289448cc3b14780ad420c8635ea05e891f2272b886620a03a81` |
| `SHA256SUMS.txt` | `ea7bd83977324d81284e0fb6e2d2efbd10d872bbceb9561340f29aa57d38e042` |

## Publication constraint

Commit and push only `feature/multi-distributor-metadata`, create annotated tag
`v1.1.0b1`, and create the GitHub pre-release manually. Do not push this
version-changing commit to `master`; that would match the inherited automatic
PyPI workflow trigger. PyPI publication remains prohibited.

Accepted risks remain:

- 69 inherited reference-output skips;
- DigiKey/Mouser credentialed live E2E not run;
- native Linux process E2E not run.
