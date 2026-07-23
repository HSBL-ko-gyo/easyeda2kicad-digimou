# New Release Candidate Source Canary

Generated: 2026-07-23 JST

This is the authoritative input canary for the new Release Candidate audit
cycle authorized after the historical RC2 cycle closed as
`CANARY PASS / RELEASE BLOCKED`. This audit is a new initial audit, not a third
RC2 re-audit.

Oracle must verify the files and invariants below before classifying the
candidate. If an attached file is missing, a SHA-256 value differs, or an
invariant cannot be located, the response must be `ORACLE INPUT UNAVAILABLE`
instead of an audit of stale context.

The canary file itself is not self-hashed. To avoid Oracle's automatic bundle
mode, the direct attachments are this canary plus the candidate diff, quality
record, and secret-audit record. Those three files are hashed below. The same
table also hashes every individual current source, contract, and regression
test used for the pre/post audit source-freeze check; their complete content is
present in the candidate diff.

| File | SHA-256 |
| --- | --- |
| `docs/oracle/rc3_release_candidate.diff` | `64b95ce3b63cd281c51e1bb200c8519d769503d69451bcd0b02d7336901a4ecb` |
| `docs/oracle/rc3_quality.md` | `8bd1fdff57777e56b61d6dceace8faab65dcf2445eab188e99487210900759f2` |
| `docs/oracle/rc3_secret_audit.md` | `72e24bf6a51cc3d305b966315415dcd746ed5d85a43ceebfef1fc4590e048f03` |
| `docs/CODEX_RESULT.md` | `85a2841c19a5a7c0f9cb6e67a8d3146243f731e36bc44481939cc6aac29d29d4` |
| `docs/architecture.md` | `b4431bd61316aa459c506215e94a2ef2f70d0d1202fef9d756dbca09f4c40f5f` |
| `docs/PROVIDER_CONTRACT.md` | `da3726852dc8b69088be6f9ce9f2f8bc677f3241b0443036361a137116171ceb` |
| `docs/DECISIONS.md` | `d7e114c575d747a445fb58b48193f358ad83410e5b84884468aa48a2c74da281` |
| `easyeda2kicad/__main__.py` | `4a4deae9716cdae5333cc9006b1405cc0e9dccf75c5450a4a477f6f9551ecd74` |
| `easyeda2kicad/providers/base.py` | `44d407077c8446caaa86146c6c2c379d9d059c1346ae2edeefbf6088512bce89` |
| `easyeda2kicad/metadata/cache.py` | `1978ed641fdfb02b67c18435ec7f5cd5e4eb2393ae413d69c90137b977ca1d3b` |
| `easyeda2kicad/metadata/service.py` | `f3d18d452ad4c4eb3cbb352f332f4cc4ec6b5bc3c3b6036b92dd9619be3f3da7` |
| `easyeda2kicad/providers/digikey.py` | `30f74148da3ecc3ebfa3b104a8b37409de1af2c9cdbfa42f7f3bbd09faa65d1f` |
| `easyeda2kicad/providers/mouser.py` | `986df7fde6aab89071f507e152f63e566a127ca6571be9faf2bf6f7689d55ffb` |
| `easyeda2kicad/providers/lcsc.py` | `54380d884456c3b638fca64f75c7381ed004372b59a8dbb9ce3d838abd5e78a5` |
| `tests/test_cli_metadata.py` | `54b94a58fb6052b40c74eca862f1102cb2e02193ffcae225a23c07ecc03e2872` |
| `tests/test_metadata_cache.py` | `b1cb6b48586d5247c31beed65ec65fddf588b7fae171d626e841c5a67185a174` |
| `tests/test_metadata_service.py` | `fd81925a4798ad337d2f6009e0e3742c09ef9a5cb54e950c4a8b18741993e301` |
| `tests/test_provider_digikey.py` | `fc2d624d6ca59f2ce080746f32a2433f934a51fda8045330db81af78f6746d80` |
| `tests/test_provider_mouser.py` | `10f0b9abec55167b3c771c01b3042ff19cafa8eebec3de7b1bf6926cd64f53cf` |
| `tests/test_provider_lcsc_easyeda.py` | `86cf200e76cba401384a0cd89ce1339de127f65b1009ffd4bd22f0b6a18625fb` |

## Candidate identity and required invariants

- Candidate diff: 62 files, 708,139 bytes, SHA-256
  `64b95ce3b63cd281c51e1bb200c8519d769503d69451bcd0b02d7336901a4ecb`.
- `BaseMetadataProvider._normalize_exact_candidates` classifies a raw MPN
  before full model parsing for DigiKey, Mouser, and LCSC.
- Only a candidate whose normalized raw MPN provably differs from the request
  may be excluded without full parsing.
- A missing, inaccessible, empty, or unnormalizable raw MPN fails the response
  with typed `InvalidResponseError`; it is not silently dropped.
- A raw exact-MPN candidate whose full parse fails also fails the response; a
  second valid candidate cannot turn that response into exact success.
- Mouser requires a list-valued `SearchResults.Parts`; missing or null `Parts`
  is invalid even when the reported count is zero.
- `CACHE_SCHEMA_VERSION` is `3`; schema-2 normalized entries cannot satisfy the
  new exact lookup, and invalid exact responses are not written to raw or
  normalized cache.
- LCSC ID/MPN mismatch rejection remains covered and unchanged.
- Manifest preflight rejects when the manifest path is the CAD directory or
  any ancestor of it, after normalized path resolution. A normal manifest
  child path remains allowed, and collision failure occurs before output
  creation or metadata resolution.
- Focused acceptance probes: `22 passed, 192 deselected`.
- Related regression set: `252 passed`.
- Full Python results, each with unchanged skips:
  Python 3.9, 3.12, and 3.14 each report `687 passed, 71 skipped`.
- Ruff format/check, strict mypy, real-worktree `git diff --check`, clean-index
  candidate application, and secret audit all pass.

## Scope guard

The authorized new-RC delta is limited to `RB-RC2-1`, `SF-RC2-1`, their
regression tests, new audit/state/decision evidence, and preservation of the
already-corrected `SF-RC2-2` documentation. The audit must flag unrelated API,
CLI, output-format, dependency, or refactoring changes if any are present.
