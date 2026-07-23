# KiCad Symbol Fields Table audit

Date: 2026-07-23 (Asia/Tokyo)  
Parts: `OPA333AIDBVR` / `C30878`, `LM321MF/NOPB` / `C131103`  
Result: **FIELD TABLE PASS after the documented runtime corrections**

`kicad-cli` was not available in the audit environment. KiCad's Symbol Fields
Table treats every distinct symbol property key as a possible column even when
the property is hidden, so the audit used the complete property-key set from
the generated KiCad S-expressions. Footprint properties were inspected
separately.

## Commands

Each command ran in a fresh temporary directory with a relative `library`
output, so the legacy and metadata artifacts had the same path context.

```text
python -m easyeda2kicad --lcsc_id C30878 --symbol --footprint --output library
python -m easyeda2kicad --lcsc_id C30878 --mpn OPA333AIDBVR \
  --manufacturer "Texas Instruments" --providers lcsc --symbol --footprint \
  --manifest-json manifest.json --manifest-csv manifest.csv --output library

python -m easyeda2kicad --lcsc_id C131103 --symbol --footprint --output library
python -m easyeda2kicad --lcsc_id C131103 --mpn LM321MF/NOPB \
  --manufacturer "Texas Instruments" --providers lcsc --symbol --footprint \
  --manifest-json manifest.json --manifest-csv manifest.csv --output library
```

The first audit failed. Metadata mode added five hidden custom properties:
`LCSC Product URL`, `Manufacturer Datasheet`, `Package`, `CAD Source`, and
`Verification Status`. The explicit manufacturer also could not pass both the
LCSC `Texas Instruments` display and the same-part EasyEDA
`TI(德州仪器)` display. A separate repeat probe found that `--overwrite`
duplicated `LM321MF/NOPB` because the library lookup used the unsanitized slash
name while KiCad stored `LM321MF_NOPB`.

The corrections keep Provider/CAD/sales information in manifests, accept the
manufacturer display difference only after exact part-scoped LCSC evidence,
preserve the existing non-empty CAD Manufacturer property, and use the same
sanitized KiCad symbol ID for library lookup and writing.

## Symbol properties

### OPA333AIDBVR

| Property | Value kind | Legacy | Metadata | New column | Hidden | Classification |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| Reference | reference designator | Yes | Yes | No | No | KiCad standard |
| Value | CAD symbol value | Yes | Yes | No | No | KiCad standard |
| Footprint | library/footprint reference | Yes | Yes | No | Yes | KiCad standard |
| Datasheet | existing EasyEDA/LCSC link | Yes | Yes | No | Yes | KiCad standard |
| Manufacturer | existing CAD display | Yes | Yes | No | Yes | Stable native |
| MPN | exact manufacturer part number | Yes | Yes | No | Yes | Stable native |
| LCSC Part | exact LCSC ID | Yes | Yes | No | Yes | Existing legacy field |
| ki_keywords | existing CAD keywords | Yes | Yes | No | Yes | Existing legacy field |

### LM321MF/NOPB

| Property | Value kind | Legacy | Metadata | New column | Hidden | Classification |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| Reference | reference designator | Yes | Yes | No | No | KiCad standard |
| Value | CAD symbol value | Yes | Yes | No | No | KiCad standard |
| Footprint | library/footprint reference | Yes | Yes | No | Yes | KiCad standard |
| Datasheet | existing EasyEDA/LCSC link | Yes | Yes | No | Yes | KiCad standard |
| Manufacturer | existing CAD display | Yes | Yes | No | Yes | Stable native |
| MPN | exact manufacturer part number | Yes | Yes | No | Yes | Stable native |
| LCSC Part | exact LCSC ID | Yes | Yes | No | Yes | Existing legacy field |
| ki_keywords | existing CAD keywords | Yes | Yes | No | Yes | Existing legacy field |
| ki_description | existing CAD description | Yes | Yes | No | Yes | Existing legacy field |

Metadata mode adds **zero** property keys for both audited parts. The exporter
already supplies `Manufacturer` and `MPN` in the legacy artifacts, so adding
aliases would be duplication rather than enrichment. There are no
`Manufacturer_Name`, `Manufacturer_Part_Number`, `LCSC`, `LCSC_ID`,
`Datasheet_URL`, Provider-specific, diagnostic, cache, or volatile sales
properties.

The matching legacy/metadata artifact hashes are:

| Part | Artifact | SHA-256 |
| --- | --- | --- |
| OPA333AIDBVR | `library.kicad_sym` | `7c6987e3283d6439db20784392a937d84f039a87b5a831336b88642cad3e18aa` |
| OPA333AIDBVR | `.kicad_mod` | `5cc7149d13f6364eb716222d534e614f42813a28f62a46136a423262ddd8b626` |
| LM321MF/NOPB | `library.kicad_sym` | `dbaf992ced899d9166151d4cb5781569224bd48270791d4670ebd48879df5ccf` |
| LM321MF/NOPB | `.kicad_mod` | `2fe093ab299a1405586b13dc2b9501b5cea63f48b0e2e6a57114ba40ec75bed7` |

Each footprint contains only its existing `LCSC Part` property, with the same
value and bytes in legacy and metadata mode.

## Manifest-only data

JSON and CSV retain the complete metadata model without projecting these
categories into KiCad symbol properties:

- Provider name, distributor part number, product URL, and Provider result;
- package, lifecycle, manufacturer datasheet, and CAD source/status;
- exact-match evidence, conflicts, provenance, operation/status diagnostics;
- raw-cache linkage, refresh/offline state, and retrieval time;
- price breaks, stock, MOQ, packaging, currency, and other volatile sales data.

The two generated JSON manifests round-trip through `MergedPart`. Their CSV
manifests each contain one LCSC row and the documented deterministic column
set. The explicit Manifest manufacturer is `Texas Instruments`; the KiCad
Manufacturer remains the existing CAD value `TI(德州仪器)` rather than being
silently overwritten.

## Collision and idempotency checks

- Same-name/same-value native properties remain single entries.
- Empty native properties are filled by verified values in a focused unit test.
- A differing non-empty CAD Manufacturer is preserved with a safe warning.
- Differing non-empty MPN or LCSC ID values fail before export.
- A metadata `--custom-field Manufacturer:Override` request exits 1 before
  creating a cache, manifest, or CAD artifact.
- Re-running each real metadata command with `--overwrite` leaves every symbol,
  footprint, JSON Manifest, and CSV Manifest byte-identical.
- Root symbol count remains one for both `OPA333AIDBVR` and the slash-bearing
  `LM321MF/NOPB`; property counts remain 8 and 9 respectively.

These checks establish the required no-new-column, no-duplicate, no-silent
overwrite, legacy-compatibility, and repeatability boundaries.
