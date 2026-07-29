# Provider contract

Status: public-beta corrective Release Candidate; complete quality matrix
passes and the new Oracle audit is pending

## Interface

Metadata providers implement the following operations:

```python
class MetadataProvider(Protocol):
    name: str

    def search_exact_mpn(
        self, manufacturer: str | None, mpn: str
    ) -> DistributorRecord: ...

    def get_part_by_distributor_id(self, part_id: str) -> DistributorRecord: ...
    def normalize_response(self, response: dict[str, Any]) -> list[DistributorRecord]: ...
    def validate_exact_match(
        self,
        candidates: list[DistributorRecord],
        manufacturer: str | None,
        mpn: str,
    ) -> DistributorRecord: ...
    def get_cache_key(self, request: Mapping[str, JSONValue]) -> str: ...
    def get_cache_context(self) -> Mapping[str, str]: ...
    def describe_auth_requirements(self) -> AuthRequirements: ...
```

The EasyEDA CAD adapter has a separate `CadProvider` protocol and returns a
`CadRecord` plus the unchanged raw CAD object used by current importers. A
distributor provider must never produce or claim CAD.

## Exact match

`normalize_mpn` applies only Unicode NFKC, uppercase conversion, outer trimming,
internal whitespace collapsing, and conversion of Unicode dash punctuation plus
documented presentation-equivalent minus forms (including U+2212) to ASCII `-`.
It preserves separator positions and distinguishes ASCII `-`, `_`, and `/`. It
does not remove suffixes or use prefix matching. The normalized candidate MPN
must equal the normalized query.
All three provider adapters send this same non-empty normalized MPN to remote
exact-search endpoints, while retaining original display MPNs in records and
merged user identity.

Provider MPN, manufacturer, provider/distributor ID, LCSC ID, and EasyEDA
component ID values must be non-empty strings when present. A boolean, number,
list, or object in any identity field is `INVALID_RESPONSE`; providers and model
deserializers must not coerce it to text. Descriptive fields are not identity
evidence and may use separate lenient parsing.

Every raw candidate is classified against the requested normalized MPN before
the rest of its model is parsed. A candidate with a valid, provably different
MPN may be excluded without parsing unrelated fields. A missing, non-string,
empty, or otherwise unnormalizable raw MPN is indeterminate and makes the
response `INVALID_RESPONSE`. A candidate whose raw MPN is exact must produce a
complete record with the same normalized MPN; otherwise the response is also
`INVALID_RESPONSE`. The common Provider boundary therefore cannot infer
uniqueness from silently dropped candidates. Mouser `SearchResults.Parts` must
be present and list-valued even when `NumberOfResult` is zero.

When a manufacturer is supplied, its normalized value must match every
distributor result. The manufacturer normalizer applies NFKC, uppercase
conversion, and removes whitespace and punctuation, but it has no fuzzy
matching or alias table. EasyEDA CAD may carry a different display label only
when a catalogue record proves that the same canonical LCSC ID and exact MPN
also match the explicit manufacturer. That mandatory part-scoped lookup fails
closed when unavailable or mismatching.

When the user does not supply a manufacturer, DigiKey/Mouser manufacturer values
must match an exact, part-scoped evidence value obtained from EasyEDA CAD or an
LCSC catalogue record reconciled to the same canonical LCSC ID and exact MPN.
An explicit-ID run may perform one lazy LCSC catalogue lookup when the external
display differs from the sole EasyEDA value. A value with no such evidence is
excluded as `MANUFACTURER_UNVERIFIED`; it may appear only as rejection evidence
inside the structured manufacturer conflict, never as a published distributor
record or positive selected-field provenance.

Description, alternate names, substitute lists, package similarity, and API
ranking never establish identity. Zero exact candidates raises `NotFoundError`.
More than one distinct exact candidate raises `AmbiguousMatchError`.

## Common models

All models are dataclasses containing JSON-safe primitives.

### PartIdentity

- `manufacturer`
- `manufacturer_normalized`
- `mpn`
- `mpn_normalized`
- `package`
- `lifecycle`
- `manufacturer_datasheet_url`

### DistributorRecord

- `provider`
- `distributor_part_number`
- `product_url`
- `manufacturer`
- `mpn`
- `description`
- `package`
- `lifecycle`
- `datasheet_url`
- `stock`
- `minimum_order_quantity`
- `packaging`
- `currency`
- `price_breaks`
- `retrieved_at`
- `raw_response_cache_key`

### CadRecord

- `source`
- `lcsc_part_number`
- `easyeda_component_id`
- `symbol_name`
- `footprint_name`
- `model_3d`
- `symbol_path`
- `footprint_path`
- `model_3d_path`
- `verification_status`

### MergedPart

- `identity`
- `distributor_records`
- `cad`
- `conflicts`
- `verification_status`
- `provenance`
- `provider_errors` (additive diagnostic field; never a match result)
- `provider_diagnostics` (additive credential-safe `{code, operation, status}`)

Selected merged identity fields and non-empty CAD identity, artifact, and status
fields have provenance entries of `{provider, source_field}`. `cad.source` and
each distributor record's `provider` carry record-level origin rather than
duplicating every scalar in the top-level provenance map. Unless a mapping
explicitly says otherwise, `source_field` describes a normalized
adapter/common-model field or explicit user input, not a guaranteed raw API JSON
path. `provider_errors` preserves the stable category string for compatibility;
`provider_diagnostics` adds safe provider operation and HTTP status when the
originating exception supplied them. Both are diagnostic state, not provenance
or match evidence.

## Error taxonomy

### Provider and cache diagnostics

- `NOT_FOUND`: provider returned no locally validated exact identity.
- `AMBIGUOUS`: multiple distinct exact identities or CAD IDs remain.
- `AUTH_MISSING`: required environment variables are absent.
- `AUTH_FAILED`: provider rejected credentials/token.
- `RATE_LIMITED`: retries exhausted after HTTP 429.
- `NETWORK_ERROR`: retryable/non-retryable transport failure.
- `INVALID_RESPONSE`: JSON or required identity fields are malformed.
- `CACHE_CORRUPT`: an offline entry or evidence pair is incomplete, mismatched,
  or cannot be parsed/validated.
- `OFFLINE_CACHE_MISS`: offline mode has neither evidence-envelope file.

### Identity, orchestration, and output diagnostics

- `MPN_MISMATCH`: explicit LCSC ID identity differs from `--mpn`.
- `LCSC_ID_MISMATCH`: fetched CAD identity differs from the explicit LCSC ID.
- `MANUFACTURER_MISMATCH`: an explicit manufacturer differs from a distributor
  result or the mandatory same-ID LCSC evidence.
- `MANUFACTURER_UNVERIFIED`: an inferred DigiKey/Mouser manufacturer has no
  exact part-scoped EasyEDA/LCSC evidence; the record is excluded and the result
  is nonfatally `PARTIAL`.
- `IDENTITY_UNRESOLVED`: a metadata-only provider cannot be queried because no
  trusted MPN was established.
- `CACHE_WRITE_ERROR`: a normalized provider result could not be persisted.
- `DATASHEET_UNAVAILABLE`: the explicitly selected source supplied no valid
  sanitized HTTP(S) datasheet URL, or supplied its product-page URL instead.
- `EXPORT_FAILED`: the existing KiCad exporter failed after resolution.
- `CAD_PIN_PAD_MISMATCH`: verified symbol pin and footprint pad sets differ.

`CAD_NOT_FOUND` is a verification status, not a provider error. `PARTIAL` is
also a status and exits successfully only when no blocking diagnostic is set.

Structured diagnostics contain provider/category/operation/status context only.
They must not contain
headers, credentials, tokens, request bodies containing secrets, or the full
Mouser URL (whose query string contains the API key).

Secret-name matching includes separated and concatenated spellings such as
`client_id`, `clientId`, client-secret, access-token, Authorization, and
DigiKey client-ID header variants. A known secret suffix also removes prefixed
camelCase names such as `oauthAccessToken`, `myClientSecret`, and
`databasePassword`; `accessTokenExpiresAt` and `tokenizer` remain public.
Malformed HTTP(S) strings are replaced by a fixed placeholder during diagnostic
scrubbing rather than passed through.

## KiCad projection boundary

The generated symbol reuses only the existing native `Manufacturer`, `MPN`,
`LCSC Part`, and `Datasheet` properties. Metadata mode adds no Provider-specific
or status custom property. Provider part numbers and URLs, package, lifecycle,
CAD source/status, provenance, cache state, diagnostics, price, stock, MOQ,
packaging, currency, and retrieval time are JSON/CSV Manifest data only.

An empty native field may be filled from verified identity. A non-empty field is
not silently replaced: an exact same-part Manufacturer display difference keeps
the existing CAD value with a safe warning, while an MPN or LCSC ID difference
fails before export. The exporter uses one sanitized KiCad symbol identifier for
both existing-entry lookup and writing, including MPNs containing `/`.

## Authentication

| Provider | Environment variables | Persistence |
| --- | --- | --- |
| LCSC | none | none |
| EasyEDA | none | existing CAD cache only |
| DigiKey | `DIGIKEY_CLIENT_ID`, `DIGIKEY_CLIENT_SECRET`; optional public locale variables | token in memory only |
| Mouser | `MOUSER_API_KEY` | key never persisted; API records are live-only |

Environment variables are read lazily. `describe_auth_requirements` returns only
names and help URLs, never values.

## Cache

For providers whose current terms permit persistent caching, the canonical
request includes provider, operation, cache schema version,
normalized MPN/manufacturer, and public locale/feature switches. It excludes API
keys, client secrets, access tokens, Authorization headers, and secret-bearing
URLs. Cache schema version 3 stores `raw.json` and `normalized.json` as one
evidence generation. Schema-v2 keys and envelopes are not reused because their
normalized result may have lost an indeterminate raw candidate. The legacy raw
filename explicitly carries
`payload_type: redacted_raw`, because its `data` is secret-stripped before
storage. Both envelopes contain the same cryptographically random
`generation_id`, `raw_sha256`, canonical request, and retrieval timestamp.
Normalized reads require both files; validate provider, cache key/request,
generation, timestamp, and raw hash; then revalidate provider name, exact MPN,
optional user manufacturer, distributor ID, and raw-response cache key.
`get_cache_context()` returns public request variants only; DigiKey returns
site, language, and currency.

Normalized `product_url` and `datasheet_url` values use a common public-URL
boundary before both cache writes and returned records. Only HTTP(S) URLs with
an authority are accepted; userinfo, fragments, and secret query parameters are
removed, while non-secret query parameters are retained. The same boundary is
applied again at manifest and explicit Datasheet-selection sinks. Provider
product URLs remain Manifest-only.

Pair writes prepare and flush both temporary files before replacement; a mixed
generation left by interruption or concurrent replacement fails the binding.
Freshness is 24 hours online. `--offline` permits a stale valid pair and
prohibits all HTTP calls. Absence of both files is `OFFLINE_CACHE_MISS`; one
missing half or any mismatch is `CACHE_CORRUPT`. `--refresh-metadata` bypasses
only metadata reads. Corrupt cache is a fatal diagnostic offline and is
ignored/refetched online.

Non-finite or overflowing numeric values are invalid Provider data. Exact live
and raw-replay paths return typed `INVALID_RESPONSE`; they never publish a
cache pair. If such a value is present in a schema-3 normalized entry, online
mode treats it as a miss and refetches, offline mode reports `CACHE_CORRUPT`,
and refresh bypasses it.

Mouser is explicitly excluded from this persistent cache. Its current linked
Search API terms prohibit caching or storing API content, so
`MouserProvider.persistent_cache_allowed` is false, it does not retain
`last_raw_response`, and service orchestration writes neither raw nor normalized
Mouser entries. An offline Mouser lookup performs no HTTP request and reports
`OFFLINE_CACHE_MISS`; an old on-disk entry is not replayed.

## Rate limiting and retry

Providers make at most three attempts for HTTP 429, 500, 502, 503, or 504 and
transport timeouts. A numeric `Retry-After` is honored up to a bounded delay;
otherwise exponential backoff is used. Tests inject a no-op sleeper. Auth and
validation failures are not retried.

## Field mappings

### LCSC

`get_part_by_distributor_id` accepts only a canonical `C[1-9][0-9]*` ID and uses
the dedicated anonymous `JlcpcbCatalogueClient` exclusively. It performs exact
local ID validation and stores every fetched official catalogue page as raw
cache evidence. It never calls the EasyEDA CAD endpoint; the separate
`EasyedaProvider` alone returns `CadRecord` and raw CAD to the import/export
pipeline. The historical `EasyedaApi.search_jlcpcb_components()` method is only
a forwarding compatibility facade over the dedicated client. Consequently,
`--refresh-metadata` can refetch LCSC metadata without bypassing or changing CAD
cache behavior.

MPN searches use the JLCPCB result's `model`/`componentModelEn` and
`componentBrandEn` (preferred when present) or `brand`, then perform the same
local exact validation. LCSC number and product URL remain distributor-specific.
The localized `brand` remains auditable in the raw evidence page. Catalogue
totals are parsed as strict non-negative integers. Every fetched page must report
the same total, and conflicting top-level/nested totals are `INVALID_RESPONSE`;
bounded truncation remains `AMBIGUOUS`.

Every exact-MPN metadata invocation performs this lookup once even when `lcsc`
is absent from `--providers` and CAD is explicitly `digikey` or `mouser`.
Provider selection still controls which full distributor records are emitted;
the independent `JlcpcbResolution` retains only the proven canonical JLCPCB and
LCSC part numbers, lookup status/time/cache state, stock, manual action, and
sanitized exact DigiKey/Mouser sourcing candidates.

A canonical `C[1-9][0-9]*` result is `JLCPCB_PART_FOUND` even when stock is
zero. A successful live no-match is `MANUAL_GLOBAL_SOURCING_REQUIRED`.
Transport/cache failure, ambiguous exact results, and identity conflicts remain
`JLCPCB_LOOKUP_FAILED`, `JLCPCB_IDENTITY_AMBIGUOUS`, and
`JLCPCB_IDENTITY_CONFLICT`; they never become a false no-match or manual
sourcing recommendation. The native KiCad compatibility field remains
`LCSC Part` and contains only the proven canonical identifier.

### DigiKey Product Information V4

- MPN: `ManufacturerProductNumber`
- manufacturer: `Manufacturer.Name`
- description: `Description.ProductDescription` / `DetailedDescription`
- product URL: `ProductUrl`
- datasheet: `DatasheetUrl`
- lifecycle: `ProductStatus.Status`, `Discontinued`, `EndOfLife`
- package: selected `Parameters` package/case value when present
- stock, distributor number, MOQ, packaging, price: selected
  `ProductVariations` entry and `StandardPricing`
- currency: requested locale currency

`ExactMatches` and `Products` are both treated as untrusted candidates and
locally validated. `ProductsCount` is mandatory and strictly validated. If it
exceeds the returned unique candidate count, the bounded response is treated as
`AMBIGUOUS`; uniqueness is never claimed from a truncated page.

After exact identity validation, the adapter chooses the lexically smallest
stable variation distributor part number. If no variation supplies one, it falls
back to the product-level record. Final equal-identity candidate ordering uses
distributor part number and product URL only, never MOQ, stock, or price; sales
fields remain attached to the selected record rather than becoming identity
evidence.

### Mouser Search API V2

- MPN: `ManufacturerPartNumber`
- manufacturer: `Manufacturer` (`ActualMfrName` is not used as match evidence)
- distributor number: `MouserPartNumber`
- description: `Description`
- product URL: `ProductDetailUrl`
- datasheet: `DataSheetUrl`
- lifecycle: `LifecycleStatus` / `IsDiscontinued`
- package: relevant `ProductAttributes` value when present
- stock: parsed numeric `AvailabilityInStock` when provided
- MOQ: parsed numeric `Min`
- packaging: relevant `ProductAttributes` value or reeling signal
- price/currency: `PriceBreaks`

The official request sets `partSearchOptions` to `Exact`, but local validation
remains mandatory. `NumberOfResult` is mandatory and strictly validated. If it
exceeds the returned `Parts` count, the result is `AMBIGUOUS` rather than a
partial-page exact match. `SuggestedReplacement` is ignored. When multiple
records share one exact identity, the adapter chooses the lexically smallest
non-empty `MouserPartNumber`, using product URL only as a stable fallback. MOQ,
stock, and price never choose record identity or KiCad fields.

For explicit Mouser CAD discovery, the exact record is revalidated and its
`ProductDetailUrl` is accepted only when it is a sanitized HTTPS Mouser Product
Detail URL. The CLI returns that URL as a manual ECAD/Library Loader handoff;
it does not fetch the page or automate SamacSys search, login, requests, or
download. Distributor remains `mouser`, delivery partner is `samacsys`, and
model creator remains unknown until proven by the imported package.

## Automatic CAD selection and source lock

`--cad-source auto` first uses EasyEDA only when the exact CAD payload passes
the normal identity and requested-artifact validation. External landing URLs
are action-only discovery results and never count as an available CAD package.

External candidates must be explicit local `digikey=ZIP` or `mouser=ZIP`
inputs. Every archive is inspected through the same fail-closed package
pipeline before any output. If all material signatures agree, the fixed
external priority is DigiKey then Mouser. A material signature contains the
selected symbol pin set, footprint pad set, selected footprint/package name,
and primary 3D-link basename. Different signatures return
`CAD_SOURCE_CONFLICT`; no candidate is guessed or partially installed.

An external auto selection is content-locked by schema-1 JSON containing only
manufacturer, full MPN, selected source, and package SHA-256. Unknown fields,
identity mismatch, source/hash mismatch, and concurrent/conflicting lock writes
fail closed. The archive SHA-256 is checked again before installation. Lock
files are written atomically, contain no machine path, and allow offline
rebuild from the same already-validated local package. An existing exact lock
is an explicit reproducibility decision and takes precedence over later source
availability changes.
