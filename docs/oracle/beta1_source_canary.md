# Public-beta corrective RC source canary

Generated: 2026-07-23 (Asia/Tokyo)

This is a distinct public-beta corrective RC. Historical evidence remains:

- RC2: `CANARY PASS / RELEASE BLOCKED`, closed at its re-audit limit;
- RC3 final candidate SHA-256:
  `95e12bccfbd4b988d15416e8c337d540a07c94ff58b4e3b4bc5a4681ad9c6b75`;
- RC3 final verdict: `CANARY PASS / no RELEASE BLOCKER / RELEASE APPROVED`.

The RC3 approval is not reused for the runtime changes below.

## Candidate identity

- upstream baseline:
  `fff10a38619963d7cb1c57d779655a9ea4572e95`;
- preserved RC3 tree:
  `f01850fa5fb73007a8707f612676beb17031abf0`;
- current candidate tree:
  `0c7b7f01e3389ef7efbecec40574619d292bdf78`;
- full candidate: 68 files, 750,327 bytes, SHA-256
  `5c848efe9e3dcbbb4dcc632f150cca0e7e824384230de250a18e644a907945d3`;
- RC3-to-current delta: 17 files, 64,625 bytes, SHA-256
  `04004f17a6a90cf0c308acb3d3a11696163bbe98c96cf9100dab000a7420c3d7`;
- clean temporary-index candidate apply/check and applied-tree equality: PASS.

## Direct Oracle attachments

Use these ten files as individual `-f` attachments in one new conversation.
Do not use bundle mode, an old bundle cache, or a prior conversation.

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

## SHA-256 table

| File | SHA-256 |
| --- | --- |
| `docs/oracle/beta1_release_candidate.diff` | `5c848efe9e3dcbbb4dcc632f150cca0e7e824384230de250a18e644a907945d3` |
| `docs/oracle/beta1_delta_from_rc3.diff` | `04004f17a6a90cf0c308acb3d3a11696163bbe98c96cf9100dab000a7420c3d7` |
| `docs/oracle/beta1_quality.md` | `e3ac35b80c475cd733bd13095edde8537cd40c5b928f2f0a0dd149aaf67663f8` |
| `docs/oracle/beta1_secret_audit.md` | `1afcbad92c379247a96227a44399729eeeae756424e6124960ca2bf398fceb95` |
| `docs/FIELD_TABLE_AUDIT.md` | `f41efee3ba026ea6ada313af0a554120b5b0cfd15cbb56609b19bde7973c7559` |
| `easyeda2kicad/metadata/symbol_fields.py` | `831123695997468dfa15d3f485668089a891ed73b71a70511e172c755e24bf24` |
| `easyeda2kicad/metadata/service.py` | `75e1c186e4893d5fd137d12f708f1a9c9f8db526ce2ef08d9a9b503a4f160d06` |
| `easyeda2kicad/__main__.py` | `f8cfcaddf5f74ec4ae7db83c05d92ef9733ad7b83d3c08f30d35788f2089626b` |
| `easyeda2kicad/kicad/export_kicad_symbol.py` | `299255e1ed112bc7ddef6977c5ce0d5014fb4026933146ebb64e8037c4098361` |
| `tests/test_metadata_manifest_fields.py` | `04407e82c5fcde504b64fb4fa6c455ec9f568a7a3c499f9b4069d1d259c1ca1f` |
| `tests/test_custom_fields.py` | `eaaf3d333763256be9ca7021e47c3df1d6b9d9887d1fc20af6d62eee1b970bf1` |
| `tests/test_metadata_service.py` | `de24d384661695055746aa3d0a0a4f3aca35a9e70da892fe5ac9ef3543d2718a` |
| `tests/test_symbol_lib_helpers.py` | `d1c1df8c771b89a422014e65741197d29230f3457bc62f800374dea0fb2a14f2` |
| `docs/architecture.md` | `c599cfa0d12a589a3fa1969c1dee5da791341194845dd7c628f28bf679b2bfab` |
| `docs/PROVIDER_CONTRACT.md` | `59b598ed64e083cbca3f47662672f395bdc4d4942b67f0d1bf240b7df6b585c0` |
| `docs/DECISIONS.md` | `b27e991d1c502cef62dcded8dcbd50738eb83306a3b078474069d644bfb05ccf` |
| `docs/CODEX_RESULT.md` | `c93a024057fa8e3c692b171c69367da59479b0d474b80a02b0f6d8a73bfa6d9b` |

## Required invariants

Oracle should report `ORACLE INPUT UNAVAILABLE` instead of auditing if any
direct attachment is absent, either diff hash differs, or the following cannot
be found in the current files/candidate:

1. `build_symbol_fields()` emits no metadata custom properties; only native
   Manufacturer/MPN/LCSC/Datasheet fields are eligible for KiCad projection.
2. Provider/status/provenance/cache/sales values remain complete in JSON/CSV
   Manifests and are absent from symbol properties.
3. An explicit Manufacturer that differs from the EasyEDA display requires an
   exact LCSC record for the same canonical ID and exact MPN; unavailable or
   mismatching evidence fails closed before external Provider calls.
4. A differing non-empty CAD Manufacturer is preserved with a safe warning;
   differing non-empty MPN/LCSC identity fails before export.
5. Symbol lookup and writing use the same sanitized KiCad ID, so
   `LM321MF/NOPB` overwrite is byte-idempotent and retains one root symbol.
6. Real OPA333AIDBVR and LM321MF/NOPB legacy/metadata artifacts are
   byte-identical in the same path context, add zero property keys, and remain
   byte-identical after metadata `--overwrite`.
7. Python 3.9, 3.12, and 3.14 each report `702 passed, 71 skipped`; Ruff,
   Python 3.9 strict mypy, diff check, candidate apply/tree, and secret audits
   pass.

Recompute this table immediately after the Oracle answer. Any mismatch is
`SOURCE CANARY FAIL` and invalidates the answer.
