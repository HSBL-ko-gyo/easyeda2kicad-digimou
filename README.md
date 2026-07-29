# easyeda2kicad +DigiMou

> **Public beta `1.1.0b1` — unofficial derivative.** This project modifies
> [uPesy/easyeda2kicad.py](https://github.com/uPesy/easyeda2kicad.py) from
> baseline `fff10a38619963d7cb1c57d779655a9ea4572e95`. The modifications and
> attribution are described in [NOTICE](NOTICE); the entire work remains
> licensed under GNU AGPL-3.0. It is not an official DigiKey, Mouser, LCSC,
> EasyEDA, or upstream release and is not presented as their successor.

[![Public beta](https://img.shields.io/badge/public_beta-1.1.0b1-orange)](https://github.com/HSBL-ko-gyo/easyeda2kicad-digimou/releases)
[![License: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-blue)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](setup.py)
[![Git hook: pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://github.com/pre-commit/pre-commit)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

## Current capabilities

| Provider path | Distributor metadata | CAD acquisition today | Account requirement |
| --- | --- | --- | --- |
| LCSC / JLCPCB + EasyEDA | Exact LCSC/JLCPCB catalogue metadata | Symbol, footprint, and 3D model from EasyEDA | None |
| DigiKey | Official Product Information V4 API metadata | API-only exact model discovery and sanitized Ultra Librarian handoff, plus safe local import of the user-downloaded native KiCad ZIP; download remains manual | User-owned DigiKey developer app credentials; user review of the Ultra Librarian agreement and official-site download |
| Mouser | Official Search API V2 metadata | Exact official Product Detail handoff plus safe local import of a user-exported native KiCad SamacSys package; download remains manual | User-owned Mouser API key; user-owned MyMouser/SamacSys session or Library Loader for package export |

`--providers` currently selects **metadata providers**, not alternative CAD
sources. CAD acquisition defaults to EasyEDA and requires an exact LCSC
mapping. `--cad-source` is a separate CAD contract: an explicit `digikey` or
`mouser` selection never falls back to EasyEDA. Local package validation and
import are available. DigiKey can discover one exact Ultra Librarian model
handoff from the official Product Information V4 `Media` response, and its
Phase C real-package path has passed KiCad CLI and GUI validation. Mouser can
return the sanitized exact Product Detail URL supplied by the official Search
API, but it does not scrape that page or automate SamacSys search, login,
requests, or download. Until the Mouser path and final multi-source behavior are
validated end to end with a real package in KiCad, this project does not provide
complete DigiKey or Mouser CAD support.

This beta preserves the existing `easyeda2kicad` Python package, CLI command,
public API, legacy `--lcsc_id` path, and legacy KiCad output while adding
LCSC/DigiKey/Mouser distributor metadata. Exact MPN matching is fail-closed.
JSON and CSV Manifests retain complete metadata; provider-permitted
raw/normalized caches support `--offline` and `--refresh-metadata`, while
Mouser remains live-only under its current API terms. KiCad receives only
stable native Manufacturer/MPN/LCSC/Datasheet identity properties—price, stock, provider
state, provenance, diagnostics, and other volatile sales data remain
Manifest-only. DigiKey and Mouser credentials are environment variables and
are never written to logs, Manifests, cache keys, cache payloads, or KiCad
properties.

A Python script that converts any electronic components from [EasyEDA](https://easyeda.com/) or [LCSC](https://www.lcsc.com/) to a KiCad library including **3D model** in color. This tool will speed up your PCB design workflow especially when using [JLCPCB SMT assembly services](https://jlcpcb.com/caa). **It supports KiCad v6 and newer.**

<p align="center">
  <img src="https://raw.githubusercontent.com/uPesy/easyeda2kicad.py/master/ressources/demo_symbol.png" width="500">
</p>
<div align="center">
  <img src="https://raw.githubusercontent.com/uPesy/easyeda2kicad.py/master/ressources/demo_footprint.png" width="500">
</div>

## 💾 Installation

The public beta is distributed only through its
[GitHub pre-release](https://github.com/HSBL-ko-gyo/easyeda2kicad-digimou/releases).
Install the downloaded wheel in the environment that runs KiCad:

```bash
python -m pip install ./easyeda2kicad-1.1.0b1-py3-none-any.whl
```

This beta is not published to PyPI. Installing the `easyeda2kicad` distribution
name from PyPI installs the separate upstream release, not +DigiMou. For an
editable checkout instead:

```bash
python -m pip install -e .
```

### Installation using the KiCad Command Prompt

Use the Python interpreter that will run this CLI, and install either the
downloaded +DigiMou wheel or an editable checkout. Do not substitute a PyPI
package name in these commands.

**Windows:** Open *KiCad Command Prompt*, then install the downloaded wheel:

```powershell
python -m pip install C:\path\to\easyeda2kicad-1.1.0b1-py3-none-any.whl
```

**Linux:** Install the downloaded wheel with the same system Python used by
KiCad:

```bash
python3 -m pip install ./easyeda2kicad-1.1.0b1-py3-none-any.whl
```

**macOS:** KiCad bundles its own Python. Install into it with:

```bash
/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 \
  -m pip install ./easyeda2kicad-1.1.0b1-py3-none-any.whl
```

> **Tip:** In the PCB Editor, open *Tools → Scripting Console* and run
> `import sys; print(sys.executable)` to find KiCad's Python path. Use that
> interpreter with the downloaded wheel path or `-m pip install -e
> /path/to/this/checkout`.

After installation, run `easyeda2kicad` from the same terminal or KiCad Command Prompt.

## 💻 Usage

```bash
# Symbol + footprint + 3D model
easyeda2kicad --full --lcsc_id=C2040
# Individual parts
easyeda2kicad --symbol --lcsc_id=C2040
easyeda2kicad --footprint --lcsc_id=C2040
easyeda2kicad --3d --lcsc_id=C2040
# Multiple components at once
easyeda2kicad --full --lcsc_id C2040 C20197 C163691
# Custom output path
easyeda2kicad --full --lcsc_id=C2040 --output ~/libs/my_lib
# SVG preview (no KiCad conversion)
easyeda2kicad --svg --lcsc_id=C2040 --output ~/libs/my_lib
```

### Exact-MPN distributor metadata

The extended CLI can resolve an exact manufacturer part number through LCSC,
DigiKey, and Mouser. Without `--cad-package`, CAD still defaults to EasyEDA:

An API is the machine-readable product-search interface used by this CLI; it is
not the same as browsing a public product page. DigiKey and Mouser require
credentials issued for the user's own account/application. This project does
not provide shared credentials:

- DigiKey requires `DIGIKEY_CLIENT_ID` and `DIGIKEY_CLIENT_SECRET` from a
  [DigiKey developer application](https://developer.digikey.com/products). The
  CLI performs the short-lived OAuth token exchange; do not paste or persist an
  access token manually.
- Mouser requires `MOUSER_API_KEY` requested through the
  [Mouser API portal](https://www.mouser.com/en/apihome/).

The three-provider example below can still exit with status `0` and generate
valid EasyEDA CAD when either credential is missing. In that case the overall
result can be `PARTIAL`; inspect `distributor_records`, `provider_errors`, and
`provider_diagnostics` in the JSON manifest before treating all requested
metadata providers as successful.

Create the parent directory named by `--output` before conversion (for example,
`mkdir -p ./libs` on Linux/macOS or `New-Item -ItemType Directory -Force ./libs`
in PowerShell). Manifest writers create their own parent directories.

```bash
easyeda2kicad --full \
  --mpn OPA333AIDBVR \
  --providers lcsc,digikey,mouser \
  --output ./libs/project_parts \
  --manifest-json ./build/OPA333AIDBVR.json \
  --manifest-csv ./build/OPA333AIDBVR.csv
```

The existing form remains valid and uses the unchanged legacy execution path
when no metadata option is present:

```bash
easyeda2kicad --full --lcsc_id C30878 --output ./libs/project_parts
```

### Discover the DigiKey / Ultra Librarian CAD handoff

With user-owned DigiKey developer credentials configured, request the exact
official model handoff and write the typed result to a Manifest:

```bash
easyeda2kicad \
  --manufacturer "Analog Devices Inc." \
  --mpn AD5314BRM \
  --providers digikey \
  --cad-source digikey \
  --manifest-json ./build/AD5314BRM-handoff.json
```

An opt-in live smoke test exercises only the exact DigiKey lookup and official
`Media`/exact-product handoff. It is skipped by the normal suite when the two
DigiKey variables are absent, makes a single attempt per operation, does not
fetch the returned page, and writes no response or credential artifact:

```bash
python -m pytest -q -m network \
  tests/test_provider_live.py::test_digikey_live_ad5314_cad_handoff_smoke
```

After the owner downloads the real ZIP, set
`DIGIKEY_AD5314_CAD_PACKAGE` to its local path. The checked-in sanitized
evidence file is bound to the reviewed package SHA-256; a re-download with a
different hash requires a newly reviewed evidence file. Then run the
package-gated smoke:

```bash
python -m pytest -q -m network \
  tests/test_provider_live.py::test_digikey_live_ad5314_package_project_e2e
```

That test uses only a disposable temporary project. It proves fail-closed
package identity, atomic/idempotent import, project-table registration,
portable paths and hashes, then parses and renders the real symbol and
footprint with the locally installed KiCad 7, 9, and 10 CLIs. It never modifies
an existing project and does not persist or commit the provider ZIP. Visual
symbol/pin, footprint/pad/courtyard, and STEP geometry/alignment inspection was
also completed in the KiCad 10 GUI using that disposable project.

The command calls only the official Product Information V4 API. It revalidates
the exact manufacturer and full MPN. One unambiguous recognized URL whose
`MediaType` is `Model` is preferred. When the API returns no model entry, the
sanitized exact `ProductUrl` from that same authenticated record is returned as
the manual product-page handoff; an unknown or ambiguous model entry still
fails closed. The CLI never fetches or scrapes either page. A manual discovery
reports `CAD_MANUAL_DOWNLOAD_REQUIRED`, exits nonzero, and stores the same
credential-free URL under `cad_discovery.action_required.setup_url`.

Open that URL, verify the exact manufacturer and MPN, review the model download
agreement, select KiCad v6+ and STEP or WRL, and download the ZIP. If
credentials are missing, the typed result is `CAD_AUTH_REQUIRED` with the
DigiKey OAuth setup page. Unsafe, malformed, or ambiguous official handoffs
produce `CAD_DOWNLOAD_UNAVAILABLE`; the CLI never guesses a URL or falls back
to EasyEDA.

The primary validation candidate is Analog Devices `AD5314BRM`. On 2026-07-29,
authenticated exact API discovery succeeded, the API `Media` response contained
no recognized model entry, and the exact official product-page handoff was
used. DigiKey then permitted a guest download from the public models page
(the completion dialog showed two guest downloads remaining that day). The
unmodified KiCad v6+ and STEP package passed archive, exact-identity,
registration, idempotency, and KiCad CLI 7/9/10 parse/render checks. API
metadata still requires the user's developer credentials, and guest download
limits can change. The real package's symbol and all ten pins were inspected in
the KiCad 10 Symbol Editor. The selected footprint's ten pads and courtyard,
plus STEP geometry and alignment, were then confirmed in the KiCad 10 GUI. This
completes the Phase C DigiKey real-service acquisition, intake, registration,
CLI, and GUI validation path; Issue #7 remains open for its Mouser and final
multi-source phases.

### Discover the Mouser / SamacSys CAD handoff

With a user-owned Mouser API key configured, resolve the exact part through the
official Search API and write its sanitized Product Detail handoff:

```bash
easyeda2kicad \
  --manufacturer Rectron \
  --mpn FM220A-W \
  --providers mouser \
  --cad-source mouser \
  --manifest-json ./build/FM220A-W-handoff.json
```

The command makes only the official exact-part API request. It revalidates the
manufacturer and full MPN and accepts only a credential-free HTTPS
`mouser.com` Product Detail URL from that response. It never fetches or scrapes
the returned page. Successful discovery reports
`CAD_MANUAL_DOWNLOAD_REQUIRED`, exits nonzero, and prints the same sanitized
URL stored under `cad_discovery.action_required.setup_url`.

Open that Product Detail page yourself and use its ECAD Model/Library Loader
flow with your own MyMouser or SamacSys session. Export a native KiCad package
containing the symbol, footprint, and STEP or WRL model, then import it with
`--cad-source mouser --cad-package-format samacsys-kicad`. SamacSys automated
search, login, request, and download are intentionally not implemented because
its current terms prohibit automated agents/scripts from generating searches,
requests, or queries.

If `MOUSER_API_KEY` is missing, the typed result is `CAD_AUTH_REQUIRED` with
the Mouser API setup page. If the official API supplies no safe exact Product
Detail handoff, the result is `CAD_DOWNLOAD_UNAVAILABLE`. Explicit
`--cad-source mouser` never falls back to EasyEDA.

Mouser API lookups are live-only: current API terms prohibit caching or storing
API content, so neither the raw response nor normalized Mouser record is
written to `.easyeda_cache`. `--offline` therefore makes no Mouser request and
reports an offline provider diagnostic instead of replaying stored API data.

An opt-in live smoke makes one exact API request and validates the FM220A-W
handoff without opening the returned page:

```bash
python -m pytest -q -m network \
  tests/test_cad_mouser_live.py::test_mouser_live_fm220a_cad_handoff_smoke
```

After the owner exports the real package, set `MOUSER_FM220A_CAD_PACKAGE` to
its local path and run:

```bash
python -m pytest -q -m network \
  tests/test_cad_mouser_live.py::test_mouser_live_fm220a_package_project_e2e
```

The package smoke performs no network access and uses only a disposable
temporary project. It checks fail-closed identity, provenance, hashes, portable
model paths, atomic/idempotent project registration, and KiCad CLI 7/9/10
symbol/footprint rendering. It neither retains nor commits the provider
package. Final symbol/pin, footprint/pad, and 3D alignment inspection in the
KiCad GUI remains an explicit owner-visible check.

The primary candidate remains `Rectron / FM220A-W`; no replacement was chosen.
On 2026-07-26 the public LCSC exact-MPN lookup returned no match, but the
official Mouser page labelled the ECAD action **“Build or request PCB Symbol,
Footprint or Model”**. The Library Loader handoff still exists, but an already
downloadable package is therefore not proven and the candidate condition may
have changed. The credential- and package-gated smokes are ready but have not
run. Phase D cannot claim end-to-end completion unless the owner can obtain the
real FM220A-W package through the official flow.

### Import a locally downloaded CAD package

The local importer is an intermediate handoff for packages that the user
obtained through an official DigiKey/Ultra Librarian or Mouser/SamacSys
workflow. It does not automate provider website search, login, agreements, or
download, and it does not make the DigiKey/Mouser CAD service path complete.
Only native KiCad `.kicad_sym` and `.kicad_mod` packages with STEP/STP or WRL
models are accepted; legacy `.lib` conversion and Library Loader internals are
not guessed.

Create the output parent first, then provide the exact manufacturer and full
ordering MPN. If the untouched official package omits provider/manufacturer
properties, also provide a separately reviewed, sanitized JSON receipt that
binds the official product/model URLs and exact identity to the package hash:

```bash
mkdir -p ./libs
easyeda2kicad \
  --manufacturer "Example Manufacturer" \
  --mpn "EXACT-MPN-INCLUDING-SUFFIX" \
  --cad-source digikey \
  --cad-package ./downloads/official-ultralibrarian-kicad.zip \
  --cad-package-format ultralibrarian-kicad \
  --cad-package-evidence ./docs/evidence/issue-7c-digikey-ad5314brm.json \
  --output ./libs/project_parts \
  --manifest-json ./build/cad-package.json
```

Use `--cad-source mouser --cad-package-format samacsys-kicad` for the
corresponding SamacSys handoff. `--cad-package-format auto` is the default and
accepts a package only when exactly one supported adapter is proven by package
notices/layout or a matching hash-bound receipt plus the versioned provider
layout. Receipt JSON rejects unknown fields, unsafe/secret-bearing URLs,
identity/source/format mismatches, and a different package hash. The receipt
does not turn the delivery partner into the model creator; distributor,
delivery partner, and model creator remain separate provenance fields.

The ZIP is inspected before extraction: absolute, UNC, drive and parent paths,
links, duplicate/case-colliding paths, nested archives, more than 4096 entries,
more than 512 MiB expanded data, files over 256 MiB, and compression ratios
over 200:1 are rejected. Normally manufacturer and exact MPN must be proven by
native symbol properties. For an official package with a hash-bound manual
handoff receipt, the native symbol must still independently contain at least
two exact full-MPN signals before missing Manufacturer/MPN fields are added
from the receipt; CLI input alone is insufficient. Provider footprint variants
are selected only when the symbol's Footprint value and exactly one package
filename match exactly. Ambiguous symbols, footprints or models, malformed
KiCad data, and pin/pad mismatches fail closed.
Installation stages and validates all files before atomically replacing the
target `.kicad_sym`, `.pretty`, and `.3dshapes` paths. Existing non-empty,
conflicting Manufacturer/MPN values are never overwritten.

### Deterministic automatic CAD source selection

`--cad-source auto` keeps verified EasyEDA CAD first. When EasyEDA has no
usable exact CAD, pass one or both already-downloaded provider packages as
repeatable, source-labelled candidates:

```bash
easyeda2kicad \
  --manufacturer "Example Manufacturer" \
  --mpn "EXACT-MPN-INCLUDING-SUFFIX" \
  --providers lcsc,digikey,mouser \
  --cad-source auto \
  --cad-candidate digikey=./downloads/ultralibrarian-kicad.zip \
  --cad-candidate mouser=./downloads/samacsys-kicad.zip \
  --full \
  --output ./libs/project_parts \
  --manifest-json ./build/auto-selection.json
```

Use `--cad-candidate-evidence digikey=PATH` or
`--cad-candidate-evidence mouser=PATH` when the corresponding official package
needs the same reviewed, hash-bound evidence accepted by
`--cad-package-evidence`. Candidate paths are never inferred from a product
URL.

Every candidate passes the complete archive, exact manufacturer/full-MPN,
KiCad syntax, symbol/footprint, pin/pad, and 3D validation path before any
output changes. A product or model landing URL is only an actionable handoff;
it is not an available CAD source. If two validated packages materially differ
in pin/pad sets, footprint package, or primary 3D link, auto selection returns
`CAD_SOURCE_CONFLICT` and installs neither. Otherwise the fixed order is
EasyEDA, DigiKey/Ultra Librarian, then Mouser/SamacSys. Explicit
`--cad-source digikey` and `--cad-source mouser` remain no-fallback paths.

When an external package is selected, the CLI atomically writes
`<output>.cad-source-lock.json` unless `--cad-source-lock PATH` specifies a
different location. The schema contains only exact manufacturer, full MPN,
selected source, and package SHA-256—never an absolute package path or
credential. The JSON manifest records the same selected `cad.source`,
provider-separated provenance, package hash, and artifact hashes. A later run
with the same output and local candidates must match the lock exactly; it does
not switch because EasyEDA or another provider later becomes available.

The locked local package can be rebuilt without provider access:

```bash
easyeda2kicad \
  --manufacturer "Example Manufacturer" \
  --mpn "EXACT-MPN-INCLUDING-SUFFIX" \
  --cad-source auto \
  --cad-candidate digikey=./downloads/ultralibrarian-kicad.zip \
  --offline \
  --full \
  --output ./libs/project_parts \
  --manifest-json ./build/offline-rebuild.json
```

The archive hash is rechecked immediately before installation, so a candidate
changed after validation fails before output. Source locks and manifests cannot
share a path or occupy a selected CAD output tree.

`--providers` is a comma-separated list of distributor metadata to return.
Metadata mode defaults to `lcsc` when the option is omitted. In MPN-only mode,
the LCSC resolver is still consulted to map the exact MPN to an LCSC ID for
EasyEDA CAD, even when `lcsc` is omitted from `--providers`; this does not make
LCSC a CAD provider. `--manufacturer` is an optional hard exact-match
constraint at distributor boundaries. If the same part uses a different
manufacturer display in EasyEDA CAD, the run succeeds only after an LCSC
catalogue record proves the same canonical LCSC ID, exact MPN, and explicit
manufacturer; missing or mismatching evidence fails closed. When both
`--lcsc_id` and `--mpn` are supplied, the MPN embedded in the fetched EasyEDA
CAD payload must match; neither input silently overrides the other. MPN
comparison preserves ordering-code suffixes and the positions of `-`, `_`, and
`/`, so similar parts are not substituted automatically.
An explicit distributor choice in `--datasheet-link` automatically appends that
source to the provider selection when necessary, while preserving the order
given in `--providers`.

Without `--manufacturer`, a DigiKey/Mouser manufacturer must still match exact
same-part evidence from the reconciled EasyEDA/LCSC identity. A differing name
is accepted only when that canonical LCSC record proves the alias (for example,
localized `TI(德州仪器)` and `Texas Instruments`). Otherwise the distributor
record is excluded from manifests, BOM rows, and KiCad fields as
`MANUFACTURER_UNVERIFIED`, and the successful result is marked `PARTIAL` with a
structured conflict diagnostic. No fuzzy or global manufacturer alias table is
used.

DigiKey and Mouser use their official APIs only. Configure credentials through
environment variables; values and access tokens are never stored in manifests,
cache keys, symbol properties, or logs:

| Provider | Required environment variables | Optional public settings |
| --- | --- | --- |
| DigiKey | `DIGIKEY_CLIENT_ID`, `DIGIKEY_CLIENT_SECRET` | `DIGIKEY_LOCALE_SITE`, `DIGIKEY_LOCALE_LANGUAGE`, `DIGIKEY_LOCALE_CURRENCY` |
| Mouser | `MOUSER_API_KEY` | none |
| LCSC / EasyEDA | none | none |

A missing distributor credential produces a visible provider error and a
`PARTIAL` result while available metadata and CAD continue. It is not reported
as product `NOT_FOUND`. JSON/CSV manifests retain the compatibility error code
and a separate credential-safe diagnostic object containing only `code`,
optional provider operation, and optional HTTP status.

Useful metadata options include:

- `--manifest-json PATH` and `--manifest-csv PATH` for full/BOM-compatible
  output;
- `--datasheet-link manufacturer|lcsc|digikey|mouser` to explicitly replace the
  symbol Datasheet link (without it, the EasyEDA value is preserved). An
  explicit choice must provide a valid public HTTP(S) datasheet URL and must not
  resolve to that distributor's product page;
- `--offline` to prohibit all network access and accept stale cache entries;
  missing external-provider metadata is reported as a visible provider error,
  while missing or corrupt LCSC/CAD cache needed to establish identity or CAD
  can block the run;
- `--refresh-metadata` to bypass distributor metadata cache without refreshing
  CAD;
- `--require-cad` to make confirmed `CAD_NOT_FOUND` return exit status 1;
- `--no-price` and `--no-stock` to omit volatile values from manifests only;
- `--show-conflicts` to print deterministic conflict/provider diagnostics.

The UTF-8 JSON manifest is the complete merged model: `identity`,
`distributor_records`, optional `cad`, `conflicts`, `verification_status`,
`provenance`, `provider_errors`, and `provider_diagnostics`. The BOM-compatible
UTF-8 CSV emits one row per distributor record (or one stable row when no
distributor record exists), repeating merged identity/CAD columns on each row.
`Price Breaks`, `Conflicts`, `Provenance`, `Provider Errors`, and
`Provider Diagnostics` are deterministic compact JSON strings inside their CSV
cells. CSV cells that spreadsheet programs could interpret as formulas are
prefixed with an apostrophe; the JSON representation remains unchanged.
Manifest paths must be distinct, must not contain one another, and must not be
placed inside a selected `.pretty`, `.3dshapes`, or `.svgs` output tree.

Provider product and datasheet URLs are normalized before cache or output:
userinfo, fragments, and secret-bearing query parameters are removed while
ordinary public query parameters are retained. Malformed or non-HTTP(S) public
links are omitted, including on the first uncached run.

Where a provider permits persistent caching, metadata cache entries are
provider-scoped under `.easyeda_cache/metadata/<provider>/<sha256>/`, with a
credential-stripped `redacted_raw` envelope and normalized JSON stored as one
generation-bound pair. They are fresh for 24 hours online; offline mode accepts
a stale pair only after its request/generation/hash binding validates and never
falls through to HTTP. Mouser is excluded from persistent caching under its
current API terms and is therefore unavailable in offline mode.

Generated symbols reuse only the existing native `Manufacturer`, `MPN`,
`LCSC Part`, and `Datasheet` properties. Provider part numbers and URLs,
manufacturer datasheet, package, lifecycle, CAD source/status, provenance,
diagnostics, cache state, price, stock, MOQ, packaging, currency, and retrieval
timestamps remain in JSON/CSV manifests. A differing non-empty CAD Manufacturer
display is preserved rather than silently overwritten after exact same-part
evidence; MPN or LCSC ID conflicts fail before export. The generated
[OPA333AIDBVR manifest](docs/examples/OPA333AIDBVR.manifest.json) and
[LM321MF/NOPB manifest](docs/examples/LM321MF-NOPB.manifest.json) are real public
LCSC/EasyEDA runs; DigiKey and Mouser were not queried live because credentials
were unavailable, although fixture tests and credential-conditioned live smoke
tests cover those adapters. Their generated machine paths were normalized to
portable repository-relative example paths after the runs; the referenced CAD
binaries are not part of these manifest examples. A clearly labeled
[mock CAD_NOT_FOUND manifest](docs/examples/CAD_NOT_FOUND.mock.manifest.json)
documents metadata-only output when EasyEDA CAD cannot be confirmed.

Metadata-mode exit status is `0` for non-blocking `VERIFIED`/`PARTIAL` results
and for optional confirmed `CAD_NOT_FOUND`. Blocking partial failures such as an
unresolved required LCSC/CAD identity, invalid cache or CAD, export errors,
pin/pad mismatch, or CAD absence with `--require-cad` return `1`.
Input-validation errors raised after parsing also return `1`; argparse syntax
errors return `2`.

By default, all libraries are saved in `~/Documents/Kicad/easyeda2kicad/` (Linux/macOS) or `C:/Users/your_name/Documents/Kicad/easyeda2kicad/` (Windows), with:

- `easyeda2kicad.kicad_sym` file for symbol library (KiCad v6+)
- `easyeda2kicad.pretty/` folder for footprint libraries
- `easyeda2kicad.3dshapes/` folder for 3D models (`.wrl` and `.step` format)

If you want to save components symbol/footprint in your own libs, you can specify the output lib path by using `--output` option.

```bash
easyeda2kicad --full --lcsc_id=C2040 --output ~/libs/my_lib
```

This command will save:

- the symbol in `~/libs/my_lib.kicad_sym` file for symbol library. The file will be created if it doesn't exist.
- the footprint in `~/libs/my_lib.pretty/` folder for footprint libraries. The folder will be created if it doesn't exist.
- the 3d models in `~/libs/my_lib.3dshapes/` folder for 3d models. The folder will be created if it doesn't exist. The 3D models will be saved both in .WRL and .STEP format.

Use `--overwrite` to replace an existing symbol, footprint, or 3D model already in the library:

```bash
easyeda2kicad --full --lcsc_id=C2040 --output ~/libs/my_lib --overwrite
```

### Project-relative 3D model paths

When working in a KiCad project folder, run the command from that project root
and use `--project-relative` together with `--output` to store 3D model paths
relative to `${KIPRJMOD}`:

```bash
cd ~/myproject
easyeda2kicad --full --lcsc_id=C2040 --output ./libs/my_lib --project-relative
```

This stores the 3D path as `${KIPRJMOD}/libs/my_lib.3dshapes/...` instead of an
absolute filesystem path, making the project portable. The resolved output must
remain inside the current project directory; out-of-tree and different-drive
paths are rejected before conversion.

### Registering libraries in one KiCad project

Project library registration is opt-in. Pass either one `.kicad_pro` file or a
directory containing exactly one `.kicad_pro`, keep the output inside that
project, and add `--register-project-libraries`:

```bash
easyeda2kicad --full --lcsc_id=C2040 \
  --output ./myproject/libs/my_lib \
  --project ./myproject \
  --register-project-libraries
```

On PowerShell, the same operation can use explicit Windows paths:

```powershell
easyeda2kicad --full --lcsc_id=C2040 `
  --output C:\work\myproject\libs\my_lib `
  --project C:\work\myproject\board.kicad_pro `
  --register-project-libraries
```

After successful CAD generation and validation, the command adds `my_lib` to
the project's `sym-lib-table` and `fp-lib-table` using
`${KIPRJMOD}/libs/my_lib.kicad_sym` and
`${KIPRJMOD}/libs/my_lib.pretty`. It does not edit the `.kicad_pro` file.
An identical registration is an idempotent no-op. A reused nickname or path
that points somewhere else is a conflict and stops without changing either
table. Existing entries, their order, and unknown table fields are preserved.

Preview the exact target files and entries without making a network request,
generating CAD, writing a Manifest, or changing project tables:

```bash
easyeda2kicad --full --lcsc_id=C2040 \
  --output ./myproject/libs/my_lib \
  --project ./myproject \
  --register-project-libraries \
  --dry-run
```

`--project-relative` by itself only makes generated 3D paths portable; it never
registers libraries. Project table writes occur only after explicit
`--register-project-libraries`, use temporary sibling files plus atomic
replacement, detect concurrent changes, and roll back if either table update
fails.

### Multiple IDs at once

You can import several components in a single call:

```bash
easyeda2kicad --full --lcsc_id C2040 C20197 C163691
```

### Custom symbol fields

Use `--custom-field` to add extra properties to generated symbols:

```bash
easyeda2kicad --symbol --lcsc_id=C2040 --custom-field "Manufacturer:Texas Instruments" "Package:LQFN-56"
```

Malformed values (missing `:`) fail fast. Duplicate keys use the last value.

If EasyEDA does not provide a datasheet URL for a symbol, easyeda2kicad falls back to `https://www.lcsc.com/datasheet/<LCSC-ID>.pdf`.

### Using a proxy server

Set the `HTTPS_PROXY` environment variable — no extra argument needed:

```bash
# Linux / macOS
HTTPS_PROXY=http://proxy.example.com:8080 easyeda2kicad --full --lcsc_id=C2040
# Windows
set HTTPS_PROXY=http://proxy.example.com:8080 && easyeda2kicad --full --lcsc_id=C2040
```

### Caching and debug

`--use-cache` enables the legacy EasyEDA resource cache (including CAD and 3D
responses) and may still fall through to the network. Metadata-mode distributor
caching is automatic and separate: `--refresh-metadata` bypasses metadata reads
only, while `--offline` strictly prohibits both provider and CAD network access
(and cannot be combined with `--refresh-metadata`). Use `--debug` for verbose
log output. The legacy cache and debug flags can be combined:

```bash
easyeda2kicad --full --lcsc_id=C2040 --use-cache --debug
```

Clear the cache with `rm -rf .easyeda_cache`.

## 🔗 Add libraries in Kicad

**These are the instructions to add the default easyeda2kicad libraries in Kicad.**
Before configuring KiCad, run the script at least once to create lib files. For example :

```bash
easyeda2kicad --symbol --footprint --lcsc_id=C2040
```

- In KiCad, Go to Preferences > Configure Paths, and add the environment variables `EASYEDA2KICAD` :
  - Windows : `C:/Users/your_username/Documents/Kicad/easyeda2kicad/`,
  - Linux : `/home/your_username/Documents/Kicad/easyeda2kicad/`
- Go to Preferences > Manage Symbol Libraries, and Add the global library `easyeda2kicad` : `${EASYEDA2KICAD}/easyeda2kicad.kicad_sym`
- Go to Preferences > Manage Footprint Libraries, and Add the global library `easyeda2kicad` : `${EASYEDA2KICAD}/easyeda2kicad.pretty`
- Enjoy :wink:

## 📚 Documentation

For detailed information about the EasyEDA data format and how commands are parsed:

- **[CMD_FOOTPRINT.md](docs/CMD_FOOTPRINT.md)** - Compact reference for all footprint commands (PAD, TRACK, RECT, etc.) with field definitions and real examples
- **[CMD_SYMBOL.md](docs/CMD_SYMBOL.md)** - Compact reference for all symbol commands (P, R, C, E, A, PL, PG, PT) with field definitions and real examples
- **[CMD_3D_MODEL.md](docs/CMD_3D_MODEL.md)** - Reference for 3D model download, OBJ/STEP formats, and WRL conversion

## 🔥 Important Notes

### WARRANTY

The correctness of the symbols and footprints converted by easyeda2kicad can't be guaranteed. Easyeda2kicad speeds up custom library design process, but you should remain careful and always double check the footprints and symbols generated.
