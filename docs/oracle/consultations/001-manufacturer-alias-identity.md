## Verdict

**BLOCKER — Architecture B1 stands as a safety requirement, but its prescribed rule should be narrowed.**

The current implementation is unsafe because DigiKey/Mouser are queried and revalidated using only the **user-supplied** manufacturer, not the manufacturer inferred from the verified EasyEDA/LCSC identity. The merge likewise enforces manufacturer equality only when `--manufacturer` was supplied.  

The tests currently codify both the legitimate TI alias case and the unsafe general case where `"Acme Devices"` and `"Other Devices"` are both retained under the same MPN.  

B1 is therefore correct that an **unproven** disagreement must not become a purchasing match. However, “exclude every differing normalized display value” is too broad because exact, part-scoped alias evidence can exist without fuzzy matching or a global alias table.

## Smallest backward-compatible algorithm

Use an **exact manufacturer evidence set tied to the verified part identity**.

### 1. Preserve the explicit-manufacturer path

When `--manufacturer` is supplied, retain the current hard-filter semantics:

```text
normalize(candidate.manufacturer)
    == normalize(user_manufacturer)
```

No behavior change is required for existing explicit-manufacturer calls. The provider contract already specifies exact normalized equality and deliberately excludes fuzzy matching and alias tables. 

### 2. Establish the part anchor

For an inferred-manufacturer request, first establish:

```text
verified LCSC ID + exact normalized MPN
```

Only manufacturer names obtained from identity-bearing fields that have been reconciled to this same anchor may enter the trusted evidence set.

For example:

```text
trusted_names = {
    EasyEDA c_para.Manufacturer,
    LCSC catalogue componentBrandEn,
    LCSC catalogue brand,
}
```

A value is included only when it came from the exact EasyEDA/LCSC record already verified against the same canonical LCSC ID and exact MPN.

The LCSC contract already identifies `brand` and `componentBrandEn` as catalogue manufacturer fields. 

The implementation should prefer `componentBrandEn` as the LCSC record’s normal distributor-facing manufacturer when it is a valid nonempty string, while preserving the localized `brand` value as evidence/provenance. This allows:

```text
EasyEDA: TI(德州仪器)
LCSC componentBrandEn: Texas Instruments
DigiKey: Texas Instruments
```

without asserting a global rule that `TI` always means `Texas Instruments`.

### 3. Validate each external distributor record

After exact-MPN validation:

```python
candidate_manufacturer = normalize_manufacturer(record.manufacturer)

verified = candidate_manufacturer in {
    normalize_manufacturer(value)
    for value in trusted_manufacturer_evidence
}
```

* Match found: accept the record.
* No match: exclude it as `MANUFACTURER_UNVERIFIED`.
* Missing manufacturer: also `MANUFACTURER_UNVERIFIED`.
* Do not infer equivalence from abbreviations, parentheses, descriptions, package, datasheet title, or consensus between distributors.

### 4. Resolve aliases lazily when necessary

For an explicit LCSC-ID run where only DigiKey or Mouser was selected, the current service may have only the EasyEDA localized manufacturer and may skip the LCSC catalogue lookup.

When an external manufacturer differs from the sole EasyEDA value:

1. Perform one exact LCSC catalogue ID lookup.
2. Verify its LCSC ID and MPN as already required elsewhere.
3. Add its identity-bearing manufacturer values to the evidence set.
4. Re-evaluate the external record.

This avoids an extra lookup when names already agree while supporting the OPA333AIDBVR and LM321MF/NOPB cases.

If the lookup is unavailable or provides no matching exact manufacturer evidence, exclude the external record and return a nonfatal `PARTIAL` result. Do not guess.

## Publication rules

| Surface                               |       Proven alias | Unverified disagreement |
| ------------------------------------- | -----------------: | ----------------------: |
| `distributor_records`                 |                Yes |                  **No** |
| BOM/CSV distributor row               |                Yes |                  **No** |
| DigiKey/Mouser KiCad properties       |                Yes |                  **No** |
| Package/lifecycle/datasheet selection |     May contribute | **Must not contribute** |
| Positive field provenance             |                Yes |                  **No** |
| Rejection diagnostic/provenance       |       Not required |                 **Yes** |
| Overall merged status                 | Normally unchanged |               `PARTIAL` |

CSV is defined as one row per published distributor record, so exclusion from `distributor_records` must also exclude the candidate from BOM rows. 

Likewise, distributor part numbers and URLs are projected into KiCad fields, so an unverified record must not reach those properties or influence package, lifecycle, or datasheet selection. 

The rejected candidate may appear in audit output, but only as rejection evidence—for example:

```json
{
  "provider": "digikey",
  "code": "MANUFACTURER_UNVERIFIED",
  "candidate_manufacturer": "Other Devices",
  "trusted_manufacturers": [
    {
      "value": "TI(德州仪器)",
      "provider": "easyeda",
      "source_field": "dataStr.head.c_para.Manufacturer"
    },
    {
      "value": "Texas Instruments",
      "provider": "lcsc",
      "source_field": "componentBrandEn"
    }
  ]
}
```

It must not appear as provenance supporting the selected identity or any selected merged field. Current provenance semantics distinguish selected-field evidence from provider diagnostics; that distinction should remain. 

## Evidence that is safe without fuzzy matching

### Safe

* **Schema-defined localized and English manufacturer fields from the same exact LCSC record**, preferably backed by the same provider brand identifier when available.
* Multiple reconciled manufacturer fields inside the same EasyEDA CAD payload, provided the payload proves the same LCSC ID and MPN.
* An **explicit user-declared exact alias**, such as a future repeatable `--manufacturer-alias "Texas Instruments"` used alongside a canonical `--manufacturer`. This is user authority, not automatic fuzzy matching.
* A documented globally stable manufacturer identifier shared by both sources. Current provider-local DigiKey/Mouser manufacturer IDs are not automatically cross-provider identifiers.

### Not sufficient by itself

* Both DigiKey and Mouser returning the same manufacturer.
* Same package, lifecycle, description, parametric values, or distributor category.
* Shared datasheet hostname such as `ti.com`.
* Similar product URLs or datasheet filenames.
* Extracting `TI` from `TI(德州仪器)`.
* Prefix, substring, token, acronym, edit-distance, or transliteration matching.

An exact identical manufacturer-controlled datasheet URL or identical downloaded document hash could be useful corroboration, but it is a larger network/cache feature and should not be required for B1.

## Classification

### BLOCKER

**Unverified inferred-manufacturer disagreements currently enter `distributor_records`, manifests, merge-field selection, and symbol projection.**

Fix now by applying the exact evidence-set check before appending each DigiKey/Mouser record. Set:

```text
provider_errors[provider] = MANUFACTURER_UNVERIFIED
verification_status = PARTIAL
```

and preserve the rejected manufacturer value in structured diagnostics.

The existing alias-retention tests and the generic “retain two genuinely different manufacturers” test must be replaced. Architecture Review B1 already requires that disagreeing records not reach KiCad or BOM outputs. 

### SHOULD FIX

**Narrow the wording of B1, D011, and the provider/architecture contracts.**

Replace the current rule:

> Inferred manufacturer disagreements do not filter exact-MPN records.

with:

> An inferred manufacturer disagreement filters the record unless the differing display value is supported by exact, part-scoped manufacturer evidence tied to the same verified LCSC ID and MPN.

D011 currently states that all inferred disagreements remain conflicts without filtering, which is the unsafe behavior B1 identified. 

An additive `--manufacturer-alias` option is also reasonable if live LCSC data does not consistently expose an English manufacturer field. It is not necessary for B1 when the exact LCSC record supplies `componentBrandEn`.

### OPTIONAL

Additional manufacturer identifiers, exact datasheet-content hashes, or manufacturer-domain ownership metadata may strengthen future validation. They are not needed to resolve B1 and should not delay the evidence-set fix.

**Final disposition:** B1 remains a **fix-now blocker**, but should be narrowed from “exclude every different display string” to “exclude every different display string that lacks exact, part-scoped alias evidence.”
