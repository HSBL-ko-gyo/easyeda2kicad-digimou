# Multi-distributor metadata architecture

Status: public-beta corrective Release Candidate; complete quality matrix
passes and the new Oracle audit is pending  
Baseline: upstream commit `fff10a38619963d7cb1c57d779655a9ea4572e95`  
License: GNU AGPL-3.0 remains unchanged

## Goals and constraints

This extension adds exact-MPN metadata from LCSC, DigiKey, and Mouser without
changing EasyEDA's role as the only CAD source. It must preserve the current
`--lcsc_id` conversion path, generated KiCad geometry, default datasheet value,
and command exit behavior when none of the new metadata options are used.

It deliberately does not download CAD from distributor or third-party library
sites, scrape product pages, choose substitutes, remove package or temperature
suffixes, or persist credentials and access tokens.

## Upstream architecture

The upstream CLI is a small `argparse` application in
`easyeda2kicad/__main__.py`. `EasyedaApi` obtains CAD JSON and optional 3D data,
EasyEDA importers convert it to internal objects, and KiCad exporters serialize
symbols, footprints, and 3D models. The symbol exporter already supplies native
Manufacturer, MPN, LCSC, and Datasheet properties and can accept explicit user
custom fields. The existing cache is opt-in (`--use-cache`) and stores EasyEDA
resources below `.easyeda_cache/`.

The unmodified baseline test result is 177 passed and 69 skipped on both the
original Python 3.12 run and the release-evidence Python 3.9.25 run. Most skips
belong to the upstream network/reference-output matrix. This extension adds a
checked-in real C2040 offline fixture and representative baseline-generated
symbol/footprint goldens that do not skip.

## Compatibility boundary

The CLI has two explicit execution paths:

1. **Legacy path**: `--lcsc_id` is present and no metadata-specific option is
   present. The current validation, EasyEDA calls, export ordering, output paths,
   datasheet behavior, and exit codes remain in place.
2. **Metadata path**: activated by `--mpn`, `--manufacturer`, `--providers`, manifest output,
   `--require-cad`, `--offline`, `--refresh-metadata`, `--show-conflicts`,
   `--no-price`, `--no-stock`, or an explicit `--datasheet-link`. It resolves a
   `MergedPart`, then invokes the existing CAD import/export functions when an
   exact LCSC CAD source is available.

`--lcsc_id` becomes optional but at least one of `--lcsc_id` or `--mpn` is
required. Existing multiple-LCSC-ID runs remain supported on the legacy path.
The metadata path accepts at most one LCSC ID because one manifest represents
one exact identity. Combining `--mpn` with an LCSC ID requires exact agreement;
neither value wins on mismatch.

## Modules

```text
easyeda2kicad/
  metadata/
    models.py          mutable common dataclasses and JSON serialization
    cache.py           provider-scoped redacted-raw and normalized JSON cache
    cad_identity.py    identity evidence extraction from actual CAD payloads
    merge.py           exact identity merge, conflicts, provenance
    manifest.py        JSON and BOM-compatible CSV output
    service.py         cache/provider/CAD orchestration
    symbol_fields.py   native KiCad identity fields and datasheet selection
  providers/
    base.py            provider protocol, errors, exact-match helpers, retry
    lcsc.py            LCSC metadata normalization/exact-match adapter
    lcsc_client.py     anonymous official JLCPCB catalogue transport
    easyeda.py         CAD adapter around EasyedaApi
    digikey.py         official Product Information V4 client
    mouser.py           official Search API V2 client
```

The current EasyEDA importers and KiCad exporters remain authoritative. LCSC
catalogue HTTP is isolated in its own client; the historical `EasyedaApi`
catalogue method remains only as a forwarding compatibility facade. Existing
CAD calls remain compatible.

## Data flow

```text
CLI identity input
  -> provider responses (credential-stripped redacted-raw cache)
  -> provider normalization
  -> provider-side exact MPN/manufacturer validation
  -> MergedPart (conflicts + field provenance)
  -> existing native symbol properties + selected Datasheet
  -> existing EasyEDA-to-KiCad exporters
  -> JSON manifest and/or BOM-compatible CSV
```

Distributor price, stock, MOQ, packaging, currency, and retrieval time flow only
to manifests. They never flow to `symbol_fields.py`.

`provider_errors` preserves stable category strings. The additive
`provider_diagnostics` map carries only a category, optional internal operation,
and optional numeric HTTP status; request URLs, headers, bodies, and exception
messages never cross that boundary.

## Exact identity

MPNs are normalized only by Unicode NFKC, case folding to uppercase, trimming,
collapsing internal whitespace, and mapping Unicode dash punctuation plus the
documented presentation-equivalent minus forms (including U+2212 MINUS SIGN)
to ASCII hyphen (`-`). Separator positions are preserved, and ASCII hyphen (`-`),
underscore (`_`), and slash (`/`) remain distinct. No terminal characters or
semantic suffixes are removed. Thus `AB-12` does not equal `A-B12`, and the
normalizer cannot convert one ordering code, package, or temperature grade into
another.

Provider identity fields are a strict trust boundary. MPN, manufacturer,
provider/distributor part number, LCSC ID, and EasyEDA component ID must be
non-empty JSON strings when present. Booleans, numbers, lists, and objects are
`INVALID_RESPONSE`; they are never converted with `str(...)` into apparent
exact matches. Descriptive fields retain their independent, more permissive
parsers.

Manufacturer names are NFKC/case/whitespace/punctuation normalized.
`--manufacturer` remains an exact hard filter at every distributor boundary.
EasyEDA and LCSC can use different display labels for the same part. When an
explicit manufacturer differs from the CAD display, the service must obtain an
LCSC catalogue record that matches the same canonical LCSC ID, exact MPN, and
explicit manufacturer before accepting the CAD identity; unavailable or
mismatching evidence fails closed. Without an explicit manufacturer, accepted
aliases likewise come only from the reconciled EasyEDA CAD payload and an LCSC
catalogue record tied to the same canonical LCSC ID and exact MPN. Thus
`TI(德州仪器)` and `Texas Instruments` can coexist when exact same-part
evidence proves both values, without a fuzzy or global alias table. An unproven
DigiKey/Mouser manufacturer is excluded as `MANUFACTURER_UNVERIFIED`,
contributes no merged field, BOM row, KiCad property, or positive provenance,
remains visible in a structured manufacturer conflict, and makes the result
`PARTIAL`.

A provider may use a remote API's exact option, but it must still validate the
returned `ManufacturerPartNumber`/equivalent field locally. Description text,
alternate part numbers, suggested replacements, and similarity scores are never
match evidence. Zero valid candidates is `NOT_FOUND`; more than one distinct
exact identity is `AMBIGUOUS`. Multiple distributor packaging variations for the
same manufacturer and MPN remain auditable in the redacted-raw cache. DigiKey
and Mouser select the lexically smallest stable distributor part number, with
stable URL fallback, and preserve the selected record's sales fields. MOQ,
stock, and price never influence identity or KiCad-field selection.

## Authentication and HTTP boundary

DigiKey uses the official Product Information V4 `KeywordSearch` endpoint and
official OAuth 2.0 two-legged token endpoint. Credentials are read at request
time from `DIGIKEY_CLIENT_ID` and `DIGIKEY_CLIENT_SECRET`. Optional locale
settings are `DIGIKEY_LOCALE_SITE` (default `US`),
`DIGIKEY_LOCALE_LANGUAGE` (default `en`), and `DIGIKEY_LOCALE_CURRENCY`
(default `USD`). Tokens remain in memory only and are never cache-key input,
cache content, exception text, or debug output.

References:

- https://developer.digikey.com/tutorials-and-resources/oauth-20-2-legged-flow
- https://developer.digikey.com/products/product-information-v4/productsearch/keywordsearch

Mouser uses only the official Search API V2
`/api/v2/search/partnumberandmanufacturer` endpoint with
`partSearchOptions=Exact`. Its key is read from `MOUSER_API_KEY`. The query URL
is never logged because the official API places the key in the query string.

References:

- https://api.mouser.com/api/docs/ui/index?urls.primaryName=api%2Fdocs%2FV2
- https://www.mouser.com/api-search/

The implementation uses the Python standard library (`urllib`) and injects the
transport and sleeper in tests. It retries HTTP 429, 500, 502, 503, and 504 up to
three attempts, honoring a bounded numeric `Retry-After`; authentication and
other 4xx responses are not retried. Error messages include provider, category,
and status, but not request headers, body credentials, access token, or full
Mouser URL.

Missing DigiKey/Mouser credentials produce
`GUEST_LOOKUP_UNSUPPORTED`, a sanitized official setup URL, and no HTTP request.
The implementation does not fall back to product-page scraping. The merge
records a partial result and continues other requested providers; it does not
pretend that the provider returned `NOT_FOUND`. `--require-providers` changes
only the final CLI requirement check, not provider selection or acquisition:
every provider explicitly selected by `--providers` must have a normalized
record or the command returns nonzero after writing requested manifests.

## Cache semantics

Metadata cache files live below
`.easyeda_cache/metadata/<provider>/<sha256>/` and are separate from the existing
CAD cache. Cache schema version 3 retains the `raw.json` filename for layout
compatibility but marks its envelope `payload_type: redacted_raw`: its `data` is
the credential-stripped response projection, not byte-for-byte API evidence.
Schema-v2 keys and envelopes are not reused, so an older normalized success
that omitted an indeterminate raw candidate cannot cross the new fail-closed
boundary.
`normalized.json` is the selected common-model projection. Both envelopes carry
the same canonical non-secret request, `retrieved_at`, cryptographically random
`generation_id`, and SHA-256 of the stored redacted-raw payload (`raw_sha256`).
The cache key is computed from provider, operation, schema version, normalized
manufacturer/MPN, and public locale/options. No credential, token,
Authorization header, or raw URL containing the Mouser key is included.
Credential-name filtering handles separated, concatenated, and prefixed
camelCase suffixes (for example `oauthAccessToken`) without removing unrelated
fields such as `accessTokenExpiresAt` or `tokenizer`.

Metadata cache is enabled for metadata runs and considered fresh for 24 hours.
`--refresh-metadata` bypasses metadata reads but does not bypass or invalidate CAD
cache. `--offline` forbids all provider and CAD network calls and accepts a stale
pair only after the same evidence checks. If neither envelope exists it returns
`OFFLINE_CACHE_MISS`; if exactly one exists, or either envelope is malformed or
mismatched, it returns `CACHE_CORRUPT`. `--offline` and `--refresh-metadata` are
mutually exclusive. Pair writes fully prepare and flush both temporary siblings
before publishing either file. Because the two filesystem replacements cannot
be one atomic operation, the shared generation/hash/request binding ensures an
interrupted or concurrent mixed generation is never accepted. Corrupt online
cache is ignored and refetched.

Every normalized hit requires its redacted-raw partner. Both envelopes must
match the requested provider/cache key, canonical request, timestamp,
generation, and declared raw hash, and the actual redacted-raw data must hash to
that declaration. The normalized model is then revalidated against exact MPN,
optional user manufacturer, distributor ID, and raw-response cache key.
DigiKey site/language/currency are public cache-key inputs. Multi-page LCSC raw
responses are stored as an ordered page list so normalized selection remains
auditable.

## Merge and provenance

The user's exact MPN is authoritative when supplied. Otherwise the exact LCSC
record establishes identity. Provider records are never flattened: distributor
part number, URL, stock, MOQ, packaging, currency, and price breaks remain under
their provider.

The orchestration layer passes an inferred manufacturer seed, its source, the
part-scoped evidence set, and rejected diagnostic values into the merge once.
The merge calculates the selected display, conflicts, and positive provenance
together; it does not rewrite manufacturer identity after those structures are
built.

Provenance is recorded for selected merged identity fields and non-empty CAD
identity, artifact, and status fields. `cad.source` itself carries the CAD
origin. Each distributor record likewise carries its own `provider`; its scalar
values are not duplicated field-by-field in the top-level provenance map. A
`source_field` names the normalized adapter/common-model field (or explicit user
input), not necessarily a raw API JSON path. Non-empty disagreements in package,
lifecycle, and datasheet become structured conflicts and are not overwritten
silently. Manufacturer datasheets are preferred only when they use an HTTP(S)
URL with an authority and are not a distributor product-page URL. Provider URLs
are normalized before cache/model output: userinfo, fragments, and secret query
parameters are removed, public query parameters remain, and malformed or
non-HTTP(S) public links are omitted. Provenance remains available after this
normalization.

Verification status is one of `VERIFIED`, `PARTIAL`, `CAD_NOT_FOUND`, or
`CAD_PIN_PAD_MISMATCH`. Metadata can succeed with `CAD_NOT_FOUND`; only
`--require-cad` makes that state a non-zero exit. A `PARTIAL` result exits zero
only when all recorded diagnostics are non-blocking; unresolved mandatory
LCSC/CAD identity and invalid cache or CAD remain failures. Ambiguous identity
and explicit LCSC-ID/MPN mismatch always fail.

## CAD boundary

EasyEDA remains the only CAD source. An explicit LCSC ID is resolved through the
existing EasyEDA API. MPN-only mode asks the LCSC adapter for exact candidates;
one candidate supplies the LCSC ID, zero means `CAD_NOT_FOUND`, and multiple
candidate IDs are `AMBIGUOUS` rather than an arbitrary choice.

EasyEDA component responses require an explicit boolean `success` envelope and,
for success, a non-empty object `result`. A semantically invalid cached envelope
is `CACHE_CORRUPT` offline and is refetched online; a semantically invalid
network envelope is `INVALID_RESPONSE` and is never cached. Only an explicit,
non-contradictory `success: false` envelope establishes `CAD_NOT_FOUND`.

Metadata mode parses only the CAD artifacts required by the requested actions.
A symbol-only, footprint-only, 3D-only, SVG-only, or manifest-only run is not
blocked by an unrelated parser. When both symbol and footprint are requested,
their electrical pin/pad number sets are compared. A mismatch is recorded and
causes `CAD_PIN_PAD_MISMATCH`; either required parser failing is
`INVALID_RESPONSE`. The legacy path is unchanged to avoid introducing a new
failure into existing conversions.

For an ID-only metadata request, a confirmed CAD miss or a CAD payload that
proves the LCSC ID but omits MPN evidence triggers an LCSC ID metadata lookup
whenever an external provider was selected. That lookup uses only the anonymous
JLCPCB catalogue; `LcscProvider` never calls the CAD endpoint, and
`EasyedaProvider` remains the sole CAD transport boundary. The lookup establishes
the exact MPN before DigiKey/Mouser are contacted, but its LCSC record is emitted
only if `lcsc` was selected. A differing external manufacturer can also trigger
one lazy catalogue lookup to obtain exact same-part alias evidence. Missing,
ambiguous, or unavailable mandatory identity data fails closed; unavailable
alias-only evidence rejects that external record nonfatally.

Electrical pads include SMD pads (whose EasyEDA `is_plated` flag is false) and
plated through-holes; numbered non-plated mechanical holes are excluded. An
empty/unparseable pin or pad set is `INVALID_RESPONSE`, not a mismatch.

Footprint and 3D model names inherited from CAD are validated as one portable
filesystem basename before their exporters run. Separators, control characters,
Windows device names, trailing dots/spaces, and other Windows-forbidden filename
characters fail closed instead of escaping the selected output tree.

## KiCad properties

The existing exporter is reused. `Reference` and `Value` are unchanged. The
existing native fields (`Manufacturer`, `MPN`, `LCSC Part`, `Datasheet`) are the
only metadata values eligible for projection into a generated symbol. Metadata
mode adds no Provider-specific or status custom properties. Provider part
numbers and URLs, manufacturer datasheet, package, lifecycle, CAD source/status,
provenance, diagnostics, cache state, and all sales data remain in JSON/CSV
manifests.

Native identity reconciliation fills an empty CAD property, preserves an
existing equivalent value, and never silently replaces a differing non-empty
value. A differing CAD manufacturer display is preserved after exact
part-scoped evidence and emits a safe warning; a differing MPN or LCSC ID fails
before export. Library lookup and writing use the same KiCad-sanitized symbol
name, so slash-bearing MPNs such as `LM321MF/NOPB` remain idempotent under
`--overwrite`.

`--datasheet-link` selects `manufacturer`, `lcsc`, `digikey`, or `mouser`.
Without the option, the original EasyEDA/LCSC datasheet remains unchanged.
An explicitly selected source with no valid sanitized HTTP(S) datasheet URL is
an error; a distributor product-page URL is rejected rather than substituted.
When a merged manufacturer datasheet must be inferred, a valid HTTP URL on a
non-distributor host is preferred over LCSC/DigiKey/Mouser mirror hosts; ties
and all-mirror fallback retain deterministic provider priority. This is a link
quality heuristic only and never contributes identity evidence.
Reserved metadata property names cannot be overridden by `--custom-field` in
metadata mode; conflicting input is rejected explicitly. This boundary also
rejects manual sales/cache fields such as stock, price/price breaks, MOQ,
currency, packaging, retrieval time, and raw/cache keys. Those volatile values
remain manifest-only. Legacy mode retains its existing unrestricted custom-field
behavior.

## Manifest and BOM-compatible CSV

JSON serializes the complete `MergedPart` with stable identity/CAD fields,
provider records, conflicts, verification status, provenance, compatibility
error codes, and structured safe diagnostics. CSV is a BOM-compatible tabular
form with one row per distributor record (or one stable row when none exist).
Stable fields are repeated, and `Price Breaks`, `Conflicts`, `Provenance`,
`Provider Errors`, and `Provider Diagnostics` are compact JSON strings. Paths
are serialized with `Path` semantics and UTF-8/newline handling that is tested
on Windows and POSIX-style inputs.

All manifest URL fields pass through the same public URL sanitizer used by the
normalized cache. Potential spreadsheet-formula cells in CSV are prefixed with
an apostrophe, while JSON retains the exact non-secret scalar value. Output
preflight rejects equal or ancestor/descendant JSON/CSV paths. A manifest path
that equals or is an ancestor of a selected CAD output path is rejected before
any persistent output. Because the symbol output is a regular file, a manifest
below that file path is also rejected. A normal manifest file below a
footprint, 3D, or SVG output directory is allowed.

The closed RC2 audit identified RB-RC2-1 and SF-RC2-1. The new candidate
classifies each raw MPN before full parsing through one common Provider helper,
rejects indeterminate or exact-but-unparseable candidates, and skips only a
provably different MPN. Non-finite or overflowing sales fields follow that same
typed failure boundary, including cache replay. Output preflight now resolves
planned paths and rejects the manifest-as-ancestor direction plus the impossible
manifest-below-symbol-file direction before creating the default output tree or
starting metadata/CAD work. Focused probes cover all three Providers, cache
lifecycles, Windows path semantics, relative `..`, allowed directory
descendants, adjacent prefixes, and absence of partial output.

`--project-relative` resolves both the current working directory and the model
output directory before conversion. The model directory must be contained by
the current project directory on the same path flavor/drive; otherwise input
validation fails with a clear diagnostic rather than leaking a `relative_to`
exception.

`CadRecord.model_3d_path` is the generated STEP path when STEP exists, otherwise
the WRL path. The exporter still emits both formats when a 3D model is present.
`--no-price` and `--no-stock` are serialization projections only and do not
change provider requests or cache identity.

## Test strategy

The unmodified 246-test suite remains the regression baseline. New deterministic
tests use official response-shape fixtures and injected transports; fixtures
contain no credentials. Coverage includes:

- legacy parser/path behavior plus a checked-in, no-network real C2040 fixture
  and upstream-baseline symbol/footprint goldens; the wider inherited reference
  matrix still skips when its historical bundle is absent;
- exact normalization, similar-MPN rejection, manufacturer mismatch, ambiguity;
- DigiKey and Mouser normalization, auth failures, retry/rate-limit behavior;
- raw/normalized cache separation, hit, stale refresh, corrupt entry, offline;
- LCSC ID plus MPN agreement and disagreement;
- conflicts and provenance;
- native KiCad fields, datasheet selection, and Manifest-only metadata;
- JSON and CSV manifests, Windows/POSIX path serialization;
- `CAD_NOT_FOUND`, `--require-cad`, and pin/pad mismatch;
- integration tests skipped explicitly when the documented credentials are
  absent.

Live EasyEDA E2E runs cover OPA333AIDBVR/C30878 and LM321MF/NOPB/C131103.
DigiKey/Mouser smoke cases in `tests/test_provider_live.py` run only when their
credentials exist. Mock E2E fixtures cover all providers regardless of
credentials.

The current end-to-end runtime evidence was gathered on Windows. Unit tests use
both `PureWindowsPath` and `PurePosixPath`, but a Linux runtime E2E was not run in
this Windows environment and remains an explicit release-candidate limitation.

Configured Ruff formatting/security lint, strict mypy, pytest, CLI help,
secret-pattern scanning, and diff review are release gates. AGPL-3.0 license,
the dated modification notice, and existing source notices remain intact.
