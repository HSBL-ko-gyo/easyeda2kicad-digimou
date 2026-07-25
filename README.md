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
| DigiKey | Official Product Information V4 API metadata | No DigiKey CAD retrieval; CAD remains EasyEDA-only | User-owned DigiKey developer app credentials |
| Mouser | Official Search API V2 metadata | No Mouser CAD retrieval; CAD remains EasyEDA-only | User-owned Mouser API key |

`--providers` currently selects **metadata providers**, not alternative CAD
sources. CAD acquisition is fixed to EasyEDA and requires an exact LCSC
mapping. Ultra Librarian delivery through DigiKey and SamacSys delivery through
Mouser are not yet implemented for discovery, download, or import. Until those
paths are implemented and validated, this project does not provide complete
DigiKey or Mouser CAD support.

This beta preserves the existing `easyeda2kicad` Python package, CLI command,
public API, legacy `--lcsc_id` path, and legacy KiCad output while adding
LCSC/DigiKey/Mouser distributor metadata. Exact MPN matching is fail-closed.
JSON and CSV Manifests retain complete metadata; raw/normalized caches support
`--offline` and `--refresh-metadata`. KiCad receives only stable native
Manufacturer/MPN/LCSC/Datasheet identity properties—price, stock, provider
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
DigiKey, and Mouser while continuing to obtain CAD only from EasyEDA:

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

Metadata cache entries are provider-scoped under
`.easyeda_cache/metadata/<provider>/<sha256>/`, with a credential-stripped
`redacted_raw` envelope and normalized JSON stored as one generation-bound
pair. They are fresh for 24 hours online; offline mode accepts a stale pair only
after its request/generation/hash binding validates and never falls through to
HTTP.

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
