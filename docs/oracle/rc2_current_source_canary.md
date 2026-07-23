# RC re-audit 2 current-source canary

Generated: 2026-07-23 00:12 JST

This file identifies the authoritative working-tree snapshot for the final
Oracle re-audit. The reviewer must find every canary below in
`rc2_current_cf4527f6.diff`. If any is absent, the attachment is stale and no RC
classification should be made.

## Required canaries

- `easyeda2kicad/metadata/cache.py` contains
  `CACHE_SCHEMA_VERSION = 2`, `_SECRET_NAME_SUFFIXES`, and
  `def sanitize_public_url(value: Optional[str]) -> Optional[str]:`.
- The cache validates raw/normalized `generation_id`, `raw_sha256`, canonical
  request, and timestamp as one evidence pair.
- `easyeda2kicad/metadata/models.py` contains
  `_MPN_MINUS_EQUIVALENTS`, explicitly maps `\N{MINUS SIGN}`, and defines strict
  `identity_text` for non-empty strings only.
- `easyeda2kicad/metadata/service.py` constructs
  `JlcpcbCatalogueClient`, assigns `MANUFACTURER_UNVERIFIED`, and executes
  `continue` before an unverified external record can be appended.
- `easyeda2kicad/providers/digikey.py` raises
  `AmbiguousMatchError(... operation="keyword-search-truncated")` when a strict
  result count differs from the complete returned exact-search set.
- `easyeda2kicad/providers/mouser.py` requires `SearchResults`,
  `NumberOfResult`, and `Parts`, and raises
  `part-search-truncated` on count/list mismatch.
- `easyeda2kicad/providers/lcsc.py` imports the dedicated
  `JlcpcbCatalogueClient` and does not call `get_cad_data_of_component`.
- `easyeda2kicad/__main__.py` validates project-root containment and manifest/CAD
  artifact collisions before writers run.
- The diff adds the four DigiKey/Mouser JSON fixtures, the C2040 fixture and two
  checked-in legacy goldens, top-level `NOTICE`, and schema-v2 cache tests.

## Authoritative SHA-256 values

```text
release_candidate.diff cf4527f61101258a14cfff487f987a86111da87e453f06760eadb156066a421b
rc2_current_cf4527f6.diff 87b06f090142ae9926d77d345dec1061bda924624e78839119cf98c323d2db34
easyeda2kicad/metadata/cache.py 91dad56ffc75af031c673e1b008d95e11092ae23ba2de13bc125f9f99a5efe32
easyeda2kicad/metadata/models.py 541ded7fa5f2344e1ebcd35cb11bd8876dde8c0710d09c4bf296e6f97ae35381
easyeda2kicad/metadata/service.py f3d18d452ad4c4eb3cbb352f332f4cc4ec6b5bc3c3b6036b92dd9619be3f3da7
easyeda2kicad/providers/digikey.py 2796a9c4d43f0f487fd4c8096f9da2dd15bb9428de99fe056be1beb5a9e213dc
easyeda2kicad/providers/mouser.py 4215fcbceccec32a1f5e3fc29c3287d271526ab7757e2a4bae81861b40179d88
easyeda2kicad/providers/lcsc.py b7055f07e6e8a08a2950d14a5a17dfabe1e9eaad5686d08bd32a7b0860732566
easyeda2kicad/__main__.py 8762dd14f609fb6238cd9cd9e9199efc05925911075fabfb7789461400df8395
tests/test_provider_digikey.py 5f098cc7ebec88eba6f2ad4abb65069c6fbadebb423132934f51898d32981ef8
tests/test_provider_mouser.py 467dc7942806bc744486a6d7ccd7c1d4883e66e276fd1a5a90f2ee42e898e525
tests/test_metadata_service.py 0738290638552e27e0436d0901430e980239e385c73a3af86a81adaf35f6da59
```

## Test evidence for this snapshot

- Python 3.9.25: `666 passed, 71 skipped`
- Python 3.12.13: `666 passed, 71 skipped`
- Python 3.14.3: `666 passed, 71 skipped`
- Ruff format: 59 files already formatted
- Ruff lint: pass
- Python 3.9 strict mypy: 59 source files, pass

The 71 skips are 69 inherited missing-reference skips and two credential-gated
live distributor smoke tests. No source or test changed after these runs.
