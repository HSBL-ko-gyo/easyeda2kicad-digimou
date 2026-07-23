# New RC re-audit 1 source canary

Generated: 2026-07-23 JST

This is re-audit 1 of the distinct new RC cycle. It is not part of the
historical RC2 cycle. RC2 remains closed as
`CANARY PASS / RELEASE BLOCKED`.

Oracle must verify the attached files and invariants before reviewing the
fixes. If an attachment is absent, a hash differs, or the current fixes cannot
be located, answer `ORACLE INPUT UNAVAILABLE` and do not audit stale context.

The canary itself is not self-hashed. The nine other planned direct
attachments are the delta, initial answer, quality record, secret audit,
`providers/base.py`, `metadata/cache.py`, `metadata/service.py`, `__main__.py`,
and `tests/test_cli_metadata.py`; every one is hashed below. The table also
hashes the individual current model, Provider tests, cache/service tests, and
contract documents represented in the delta so the pre/post audit source
freeze can cover them without exceeding Oracle's individual-attachment limit.

| File | SHA-256 |
| --- | --- |
| `docs/oracle/rc3_reaudit1_delta_from_initial.diff` | `695245d3ddde1a8607af0d17ac887170b7c8de0eb7b6861fa113201260a62b68` |
| `docs/oracle/release_candidate_audit_rc3.md` | `2a2c63dcbe6c21597bcaaaee42242dd81a2887a1eaef1187ed6efca6135edebb` |
| `docs/oracle/rc3_reaudit1_quality.md` | `4657a0640349b22f11f81b08bcd231723f02d0119566cccec3b339782b4220e6` |
| `docs/oracle/rc3_reaudit1_secret_audit.md` | `d3dc32da52671ef0cc6637620a506b97df947b550682eec954ec64f16b910346` |
| `easyeda2kicad/providers/base.py` | `3d1911f96c1a8463e2fcaaed83ca440a4caa4bf312b9e13baf1191f12e84b1a4` |
| `easyeda2kicad/metadata/models.py` | `17db0c9883158586fe54a06ae636c5667b3e2a2646514cf3adaa08c28717fa07` |
| `easyeda2kicad/metadata/cache.py` | `da6ce91e6397999865f05d6e8f699f79e7844e4d18b680f6fe5d1e865d98d2ed` |
| `easyeda2kicad/metadata/service.py` | `ac8e3d9729477bc2e40e5650fea6f12607ff585f4f7e26b47fce379a9d763513` |
| `easyeda2kicad/__main__.py` | `def4de34ac2fd5513a431db692c3e0ff1329a41146c285c941f1c9b008689b8f` |
| `tests/test_provider_base.py` | `41288b36d243cf8863cd761389ad40866e4d9ea8a3b2a2308bef3631bb0da85d` |
| `tests/test_provider_digikey.py` | `79b199a198884b5c0886e24b7f8db577b921bffa6545163f58fb1d011b0368e2` |
| `tests/test_provider_mouser.py` | `0168e5b5ab3e4c182cd3555e115881619e363d30413a65f246cc6b77a5b4c9a8` |
| `tests/test_provider_lcsc_easyeda.py` | `ea8d4ea7794522204321f8327180dc9bedaa10146b5dba3c5115b0987235d9a5` |
| `tests/test_metadata_cache.py` | `d050f39ec7083c0a43e3747f13fe84533f5db5d8b71fdb73b1b04c8d600bf0c3` |
| `tests/test_metadata_service.py` | `d04b9959cbb4f11bf8c5ed5827d5906b51b206fc241212fcb2c64708ebde8d0d` |
| `tests/test_cli_metadata.py` | `2788f02aacd2c9b3bce96c931ade4a35d7bd0744e9ba893c347a3098e23bab7b` |
| `docs/oracle/legacy_compatibility.md` | `d45857285bb206f02a071d0f345ee50d71fb0103fc234c208bb3e4ebf2fd036f` |
| `docs/DECISIONS.md` | `852e2acf92e163eb1a7c78df280c410867f19748180d52fb2aac43ad0f8ab372` |
| `docs/PROVIDER_CONTRACT.md` | `8381d67f907311ee15cbc5de66ef491463c782bca5d7e21d7ea465d02515263e` |
| `docs/architecture.md` | `78f4f3e04d00231548dae4dd0a9c11cd7ee9d634226fdb7444ee903c063cecb1` |

## Candidate identities

- Initial new-RC candidate tree:
  `a0b205f0d830594132e2da1e106a90aba99229c6`
- Revised candidate tree:
  `1a0aa8090a395ccf54b6b8d8bbb4ed024d3a007b`
- Initial-to-revised delta: 19 files, 37,269 bytes, SHA-256
  `695245d3ddde1a8607af0d17ac887170b7c8de0eb7b6861fa113201260a62b68`
- Revised full candidate: 63 files, 723,055 bytes, SHA-256
  `2c25cedc3f3720a3c9b54bc8563688b993d988e5ab75ba6791dc9c24dc23e6c5`
- Both diffs pass clean-index `git apply --cached --check
  --whitespace=nowarn`.

The full candidate is retained as the release artifact. The smaller delta plus
the current affected source, tests, contracts, quality evidence, secret audit,
and initial Oracle answer are attached individually so Oracle does not invoke
bundle mode and does not exceed its recommended context size.

## Required fix invariants

- `BaseMetadataProvider._normalize_exact_candidates` catches
  `OverflowError`, `TypeError`, and `ValueError` at raw identity, full record,
  and normalized record boundaries.
- `optional_int` rejects non-finite floats. `optional_float` rejects
  non-finite results and converts integer-to-float overflow to `ValueError`.
- The normalized model converts oversized numeric input to `ValueError`.
  Cache validation and service reconstruction also catch residual
  `OverflowError`.
- DigiKey, Mouser, and LCSC overflowing exact candidates produce typed
  `INVALID_RESPONSE/exact-normalize` for live-shaped execution and direct raw
  replay.
- A schema-3 overflowing normalized exact entry becomes an online miss/refetch,
  offline `CACHE_CORRUPT`, and refresh bypass. Provider failures still publish
  neither raw nor normalized entries.
- Manifest collision preflight marks the symbol output as a file. It rejects a
  manifest equal to, ancestral to, or below that file. Directory outputs still
  allow ordinary child manifests.
- JSON and CSV child-of-symbol-file CLI tests exit 1 before metadata resolution
  and leave no planned parent, symbol, manifest, or cache output.
- Historical `666 passed` rows are labelled `RC2 pre-RC3 tree`.
- New blocker probes: `8 passed`; related set: `280 passed`.
- Python 3.9, 3.12, and 3.14 each report `695 passed, 71 skipped`.
- Ruff format/check, strict mypy, diff/apply checks, and revised secret audit
  pass.

## Scope guard

Re-audit 1 must review the initial findings `RB-RC3-1`, `SF-RC3-1`, and
`DOC-RC3-1`, regressions in the already-authorized `RB-RC2-1`/`SF-RC2-1`
scope, and release-blocking consequences only. No unrelated API, CLI,
output-format, dependency, or Provider/CAD responsibility change is present or
authorized.
