# New RC final source canary

Generated: 2026-07-23 JST

The historical RC2 evidence remains unchanged and closed as
`CANARY PASS / RELEASE BLOCKED`.

For the distinct new RC cycle:

- initial-audit pre/post canary: **20/20 matched**;
- re-audit 1 pre/post canary: **20/20 matched**;
- re-audit 1 verdict: **CANARY PASS / no RELEASE BLOCKER**;
- only post-audit functional-candidate correction: the exact one-line
  `DOC-RC3-1` quality-record pointer requested by Oracle;
- Python 3.9, 3.12, and 3.14 full suites were rerun after that correction and
  each returned `695 passed, 71 skipped`, exit 0.

The final source and test hashes below are unchanged from the re-audit 1 canary.
Document hashes reflect the completed pointer correction and final status
records.

| File | SHA-256 |
| --- | --- |
| `docs/oracle/rc3_final_release_candidate.diff` | `95e12bccfbd4b988d15416e8c337d540a07c94ff58b4e3b4bc5a4681ad9c6b75` |
| `docs/oracle/rc3_final_delta_from_initial.diff` | `fd12a0a2fbe5862a0a557240362b74d668fbebd501b3f1973bf62826f45a73b4` |
| `docs/oracle/rc3_final_post_audit_doc_delta.diff` | `23ab907cc50a7eb0e5c5c3dc105f0e0069dae8804b5be58c873a80b44c60e202` |
| `docs/oracle/release_candidate_audit_rc3.md` | `2a2c63dcbe6c21597bcaaaee42242dd81a2887a1eaef1187ed6efca6135edebb` |
| `docs/oracle/release_candidate_audit_rc3_reaudit1.md` | `5fcc6f18d4f6f204e28ac82953cffa1592303f44a0b64d009a4e1935bf05e720` |
| `docs/oracle/rc3_final_quality.md` | `802087f7257d266a8f177a6f83d9670b409832fa5f9b1abd183bcf90188ec29e` |
| `docs/oracle/rc3_final_secret_audit.md` | `f99b35332ee375d3de50d08b13312dcb8872e108acd2265ff28b4e27c1fe3082` |
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
| `docs/oracle/legacy_compatibility.md` | `42657ee2c98940418b2b2d7d2d28f9df93ebd66d9a5f017c5d4c13731f070a32` |
| `docs/CODEX_RESULT.md` | `18cfa8df2bab6e52d48da3bd87b6172aa69deddd3f3d07f5a72e9644c52e0957` |
| `docs/CURRENT_STATE.md` | `d34f22bebd8ebdca6982bb233f7d15bee23d7b7e933d9ccdcb688e7adc92f661` |
| `docs/DECISIONS.md` | `b953d5361331114563c2c1a3cbddffaed2aeb7a387d53ba865ab9900bd8256e0` |
| `docs/PROVIDER_CONTRACT.md` | `d7056d9c4a0b44b1a37929981079430caee6563580d6e2d082cf30f2683b13ee` |
| `docs/architecture.md` | `d9ee6e7115a6435d28e944772759f6c562cba5d11395e7576201e5ac33855a82` |
| `docs/oracle/README.md` | `7cf7e68ed0cdcd60d37ae8aa0f0af50986d3f680e40e3086ffb5ef9fb409b1b6` |

Final candidate identity:

- candidate tree: `f01850fa5fb73007a8707f612676beb17031abf0`
- full diff: 64 files, 725,556 bytes
- SHA-256:
  `95e12bccfbd4b988d15416e8c337d540a07c94ff58b4e3b4bc5a4681ad9c6b75`
- clean-index full, initial-to-final, and audited-to-final apply checks: PASS
- final secret audit: PASS
