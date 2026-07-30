# easyeda2kicad +DigiMou

> **Public beta `1.1.0b3` — unofficial derivative.** This repository modifies
> [uPesy/easyeda2kicad.py](https://github.com/uPesy/easyeda2kicad.py). See
> [NOTICE](NOTICE) for attribution. It is not an official DigiKey, Mouser,
> LCSC, EasyEDA, or upstream release.

[![Public beta](https://img.shields.io/badge/public_beta-1.1.0b3-orange)](https://github.com/HSBL-ko-gyo/easyeda2kicad-digimou/releases/tag/v1.1.0b3)
[![License: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-blue)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](setup.py)

Convert an exact electronic part into KiCad 6+ symbol, footprint, and 3D
libraries, attach exact distributor metadata, register project-local
libraries, and return machine-readable provenance.

## Current capabilities

Metadata source and CAD source are separate choices. `--providers` selects
metadata; `--cad-source` selects CAD. An explicit
`--cad-source digikey` or `--cad-source mouser` never silently falls back to
EasyEDA.

| Provider path | Metadata | CAD delivery today | Account / guest behavior | Verified evidence |
| --- | --- | --- | --- | --- |
| LCSC / JLCPCB + EasyEDA | Anonymous exact LCSC/JLCPCB catalogue lookup | Automated EasyEDA symbol, footprint, and 3D download | No account | Public OPA333AIDBVR and LM321MF/NOPB runs, 2026-07-22 |
| DigiKey-linked CAD | Product Information V4 API | Product-specific discovery of manufacturer, Ultra Librarian, and other linked sources; verified full or manufacturer footprint+3D package import | User-owned DigiKey developer app for metadata; source agreements and limits remain provider-controlled | Authenticated Same Sky MJ-2523-SMT-TR source discovery plus AD5314BRM real-package import, KiCad CLI 7/9/10, and KiCad 10 GUI, 2026-07-30 |
| Mouser-linked CAD | Search API V2 | Exact Product Detail handoff without guessing the page's ECAD provider; validated package import after separate source and format proof | User-owned Mouser API key; any account or agreement required by the ECAD source the user selects | Adapter/fixture coverage only; a real Mouser-linked package and final GUI proof are not yet complete |

```text
exact manufacturer + full MPN
  ├─ metadata: LCSC / DigiKey / Mouser
  ├─ JLCPCB/LCSC sourcing identity
  └─ CAD: EasyEDA, or a validated user-downloaded provider package
       └─ KiCad libraries + provenance + project registration
```

The Manifest records `distributor`, `delivery_partner`, and `model_creator`
separately. DigiKey is not recorded as the creator of an Ultra Librarian
model. A Mouser Product Detail URL alone does not prove a delivery partner or
model creator.

Validated local package import is implemented for Ultra Librarian, SamacSys,
and manufacturer-provided packages, but provider website search, login,
agreement acceptance, and download automation are not. Mouser's real-package
path and final dual-provider E2E remain open. Therefore this project does not
provide complete DigiKey or Mouser CAD support.

Exact manufacturer and full-MPN checks are fail-closed. The legacy
`--lcsc_id` workflow and its output remain supported.

## 60-second quick start

This path needs internet access but no distributor account.

### 1. Install this fork

Download the wheel from the
[v1.1.0b3 GitHub pre-release](https://github.com/HSBL-ko-gyo/easyeda2kicad-digimou/releases/tag/v1.1.0b3),
then install that file with the Python environment that will run the CLI:

```bash
python -m pip install ./easyeda2kicad_digimou-1.1.0b3-py3-none-any.whl
```

For a repository checkout:

```bash
python -m pip install -e .
```

This fork is not published on PyPI. Installing the generic distribution from
PyPI installs the separate upstream project, not +DigiMou.

The install identities are deliberately distinct from upstream:

| Surface | +DigiMou identity |
| --- | --- |
| Distribution / wheel | `easyeda2kicad-digimou` |
| Primary command | `easyeda2kicad-digimou` |
| Python package | `easyeda2kicad_digimou` |
| Module command | `python -m easyeda2kicad_digimou` |

The wheel does not install the upstream `easyeda2kicad` package or command, so
both projects can coexist in one environment. Confirm which command is active:

```bash
easyeda2kicad-digimou --version
```

The legacy arguments and generated KiCad naming remain compatible. In
particular, the default output directory/library name and
`${EASYEDA2KICAD}` variable are intentionally unchanged.

On Windows, use the KiCad Command Prompt or the interpreter shown by
`import sys; print(sys.executable)` in KiCad's Scripting Console. On macOS,
replace `python` with KiCad's bundled Python when that is the environment that
must import the package.

### 2. Acquire one known-good LCSC/EasyEDA part

POSIX shell:

```bash
mkdir -p ./libs ./build
python -m easyeda2kicad_digimou \
  --manufacturer "Texas Instruments" \
  --mpn OPA333AIDBVR \
  --providers lcsc \
  --cad-source easyeda \
  --full \
  --output ./libs/project_parts \
  --manifest-json ./build/OPA333AIDBVR-lcsc.json
```

PowerShell:

```powershell
New-Item -ItemType Directory -Force ./libs, ./build | Out-Null
python -m easyeda2kicad_digimou `
  --manufacturer "Texas Instruments" `
  --mpn OPA333AIDBVR `
  --providers lcsc `
  --cad-source easyeda `
  --full `
  --output ./libs/project_parts `
  --manifest-json ./build/OPA333AIDBVR-lcsc.json
```

Expected result:

- process exit `0`;
- Manifest `verification_status` is `VERIFIED`;
- exactly one `lcsc` distributor record and no `provider_errors.lcsc`;
- `project_parts.kicad_sym`, `project_parts.pretty/`, and
  `project_parts.3dshapes/` exist.

From a repository checkout, verify the exact Manifest contract:

```bash
python examples/check_provider_manifest.py \
  ./build/OPA333AIDBVR-lcsc.json \
  --manufacturer "Texas Instruments" \
  --mpn OPA333AIDBVR \
  --provider lcsc \
  --verification-status VERIFIED
```

> **Important:** optional provider failure can produce `PARTIAL` and exit
> status `0` while valid EasyEDA CAD is still generated. Before treating a
> multi-provider run as complete, inspect `distributor_records`,
> `provider_errors`, and `provider_diagnostics`. Missing DigiKey/Mouser
> credentials produce `GUEST_LOOKUP_UNSUPPORTED` without scraping or requesting
> their product pages. Use `--require-providers` for the human CLI, or repeat
> `--require-provider` in machine mode, when every requested record is required.
> The required variables are `DIGIKEY_CLIENT_ID`,
> `DIGIKEY_CLIENT_SECRET`, and `MOUSER_API_KEY`.
> When one is unavailable or rejected, the human CLI names the variables to
> configure, explains that API results require them, and prints the official
> provider setup URL. It never asks for, echoes, or persists the credential.

## API primer and credential setup

An API is a machine-readable product-search interface. Visiting a public
product page as a guest is not the same as calling the distributor's official
API. This CLI does not provide shared credentials, create accounts, bypass
login/CAPTCHA, or scrape DigiKey/Mouser product pages.

| Provider | Official interface | What you configure | What the CLI does | Output role |
| --- | --- | --- | --- | --- |
| LCSC / EasyEDA | Public JLCPCB catalogue and EasyEDA CAD endpoints | Nothing | Exact lookup and CAD download | Metadata + automated CAD |
| DigiKey | Product Information V4 | `DIGIKEY_CLIENT_ID` and `DIGIKEY_CLIENT_SECRET` | Performs OAuth 2.0 two-legged token exchange and exact search | Metadata + sanitized CAD handoff |
| Mouser | Search API V2 | `MOUSER_API_KEY` | Sends the key only to the official exact search endpoint | Metadata + sanitized Product Detail handoff |

### Obtain your own credentials

**DigiKey**

1. Sign in or create a My DigiKey/developer account at the
   [DigiKey API portal](https://developer.digikey.com/).
2. Register an application and enable
   [Product Information V4](https://developer.digikey.com/products).
3. Copy the application's client ID and secret into your secret manager.
   DigiKey's [OAuth documentation](https://developer.digikey.com/resources)
   and [FAQ](https://developer.digikey.com/faq) describe application access,
   production access, token expiry, and 401/429 responses.

The CLI requests and renews the short-lived access token in memory. Configure
the client ID/secret only; do not manually paste, persist, print, or commit an
OAuth access token.

**Mouser**

1. Sign in or create a MyMouser account.
2. Open the official
   [Search API page](https://www.mouser.com/api-search/).
3. Complete the online Search API request. Mouser sends the key and setup
   information by email.

These are distributor-side prerequisites. This repository cannot issue or approve credentials.

### Configure the current terminal only

PowerShell:

```powershell
$env:DIGIKEY_CLIENT_ID = '<client-id>'
$env:DIGIKEY_CLIENT_SECRET = '<client-secret>'
$env:MOUSER_API_KEY = '<api-key>'
```

Windows `cmd.exe`:

```bat
set "DIGIKEY_CLIENT_ID=<client-id>"
set "DIGIKEY_CLIENT_SECRET=<client-secret>"
set "MOUSER_API_KEY=<api-key>"
```

bash/zsh:

```bash
export DIGIKEY_CLIENT_ID='<client-id>'
export DIGIKEY_CLIENT_SECRET='<client-secret>'
export MOUSER_API_KEY='<api-key>'
```

Do not place secrets directly in CLI arguments, shell history, screenshots,
project files, Manifests, or committed `.env` files. For persistent use, store
them in an OS credential manager or protected CI environment and inject them
only into the process that runs the CLI.

### Safe presence check

The preferred cross-platform preflight prints booleans only:

```bash
python -m easyeda2kicad_digimou capabilities --machine-json
```

Look at:

```text
result.providers.digikey.authentication_configured
result.providers.mouser.authentication_configured
```

PowerShell presence check without values:

```powershell
'DIGIKEY_CLIENT_ID','DIGIKEY_CLIENT_SECRET','MOUSER_API_KEY' |
  ForEach-Object {
    "$_=" + $(if (Test-Path "Env:$_") { 'configured' } else { 'missing' })
  }
```

`cmd.exe`:

```bat
if defined DIGIKEY_CLIENT_ID (echo DIGIKEY_CLIENT_ID=configured) else (echo DIGIKEY_CLIENT_ID=missing)
if defined DIGIKEY_CLIENT_SECRET (echo DIGIKEY_CLIENT_SECRET=configured) else (echo DIGIKEY_CLIENT_SECRET=missing)
if defined MOUSER_API_KEY (echo MOUSER_API_KEY=configured) else (echo MOUSER_API_KEY=missing)
```

bash/zsh:

```bash
for name in DIGIKEY_CLIENT_ID DIGIKEY_CLIENT_SECRET MOUSER_API_KEY; do
  if [ -n "${!name:-}" ]; then
    echo "$name=configured"
  else
    echo "$name=missing"
  fi
done
```

## Provider smoke tests

Create `./build` first. Each smoke uses EasyEDA as the separate CAD source and
tests one metadata provider.

### LCSC (anonymous)

```bash
python -m easyeda2kicad_digimou --manufacturer "Texas Instruments" --mpn OPA333AIDBVR --providers lcsc --cad-source easyeda --manifest-json ./build/smoke-lcsc.json --require-providers
python examples/check_provider_manifest.py ./build/smoke-lcsc.json --manufacturer "Texas Instruments" --mpn OPA333AIDBVR --provider lcsc --verification-status VERIFIED
```

### DigiKey (credentialed)

```bash
python -m easyeda2kicad_digimou --manufacturer "Texas Instruments" --mpn OPA333AIDBVR --providers digikey --cad-source easyeda --manifest-json ./build/smoke-digikey.json --require-providers
python examples/check_provider_manifest.py ./build/smoke-digikey.json --manufacturer "Texas Instruments" --mpn OPA333AIDBVR --provider digikey --verification-status VERIFIED
```

Success means exactly one DigiKey record with an exact manufacturer/full MPN,
a non-empty distributor part number, and no `provider_errors.digikey`.

### Mouser (credentialed)

```bash
python -m easyeda2kicad_digimou --manufacturer "Texas Instruments" --mpn "LM321MF/NOPB" --providers mouser --cad-source easyeda --manifest-json ./build/smoke-mouser.json --require-providers
python examples/check_provider_manifest.py ./build/smoke-mouser.json --manufacturer "Texas Instruments" --mpn "LM321MF/NOPB" --provider mouser --verification-status VERIFIED
```

Success means exactly one Mouser record with an exact manufacturer/full MPN,
a non-empty distributor part number, and no `provider_errors.mouser`.

### Credentialed provider live smoke (maintainers)

The ordinary test suite never opts in to provider traffic. With owner-owned
secrets configured in the current terminal:

```bash
python -m pytest tests/test_provider_live.py -m live_provider --run-live-provider -vv --tb=short
```

Check presence without printing values with `capabilities` or the commands
above. Each test makes one attempt per provider and asserts only exact identity,
distributor part number, sanitized URLs, and normalized output.

The manual GitHub Actions workflow uses the protected `provider-live`
environment, read-only repository permission, the actual default branch, a
single attempt, and requires a pass from both providers. Its protected secrets
are `DIGIKEY_CLIENT_ID`, `DIGIKEY_CLIENT_SECRET`, and `MOUSER_API_KEY`. Raw responses,
credentials, tokens, headers, prices, and stock are not evidence fields.
Issue #8 remains open until both a DigiKey pass and a Mouser pass are confirmed
in that workflow.

The three-provider example below is strict: it returns nonzero if any requested
record is absent.

```bash
python -m easyeda2kicad_digimou \
  --manufacturer "Texas Instruments" \
  --mpn OPA333AIDBVR \
  --providers lcsc,digikey,mouser \
  --cad-source easyeda \
  --full \
  --output ./libs/all_providers \
  --manifest-json ./build/all-providers.json \
  --require-providers
python examples/check_provider_manifest.py \
  ./build/all-providers.json \
  --manufacturer "Texas Instruments" \
  --mpn OPA333AIDBVR \
  --provider lcsc \
  --provider digikey \
  --provider mouser \
  --verification-status VERIFIED
```

Manifest proof is provider-specific:

| Check | Required proof |
| --- | --- |
| Exact identity | `identity.manufacturer` and full `identity.mpn` match |
| Provider success | One matching `distributor_records` entry |
| Provider failure | Corresponding key in `provider_errors`; no fake record |
| CAD | `cad.source`, `cad.verification_status`, and artifact paths |
| Overall status | `VERIFIED`, `PARTIAL`, or `CAD_NOT_FOUND`; do not infer provider completeness from exit `0` alone |

Common provider diagnostics:

| Code/status | Meaning |
| --- | --- |
| `GUEST_LOOKUP_UNSUPPORTED` / `AUTH_MISSING` | Required user credential is unavailable; this is not product `NOT_FOUND` |
| `AUTH_FAILED` / HTTP 401 or 403 | Credential rejected, app not enabled, or access forbidden |
| `RATE_LIMITED` / HTTP 429 | Provider rate limit reached; retry later |
| `NOT_FOUND` | Official provider returned no exact part |
| `MPN_MISMATCH`, `MANUFACTURER_MISMATCH`, `MANUFACTURER_UNVERIFIED` | Returned identity did not pass fail-closed validation |

## CAD handoff and package import

### Discover a product-specific DigiKey CAD handoff

```bash
python -m easyeda2kicad_digimou \
  --manufacturer "Analog Devices Inc." \
  --mpn AD5314BRM \
  --providers digikey \
  --cad-source digikey \
  --manifest-json ./build/AD5314BRM-handoff.json
```

The CLI revalidates exact identity and classifies every relevant safe URL from
the Product Information V4 `Media` operation. If the API has no CAD links, it
may make one credential-free, cookie-free GET of the exact canonical DigiKey
model page. Only links whose visible context binds the full MPN to an explicit
symbol, footprint, or 3D artifact are accepted. It does not bypass login,
CAPTCHA, agreements, guest limits, or rate limits.

`cad_discovery.available_sources` keeps manufacturer-provided files, Ultra
Librarian, SnapMagic, SamacSys, TraceParts, and unknown linked providers
separate. `missing_artifacts` records unavailable symbol/footprint/3D types.
Known provider rules are data-driven; a manufacturer link requires either a
manufacturer-provided label or a manufacturer/domain identity match. Unknown
hosts remain truthful manual handoffs and are never silently claimed as the
manufacturer.

A valid manual handoff returns `CAD_MANUAL_DOWNLOAD_REQUIRED`; missing
credentials return `CAD_AUTH_REQUIRED`; unsupported-only, unsafe, or ambiguous
handoffs return `CAD_DOWNLOAD_UNAVAILABLE`. Open the official URL yourself,
review the applicable terms, verify manufacturer/full MPN, and download only
the offered artifacts.

Same Sky `MJ-2523-SMT-TR` was verified live on 2026-07-30: DigiKey exposed a
manufacturer footprint and 3D model but no symbol, and the source was not
misidentified as Ultra Librarian. The earlier AD5314BRM Ultra Librarian path
remains validated with a real package in KiCad CLI 7/9/10 and KiCad 10 GUI.
Guest availability and download limits can change.

### Discover the Mouser CAD handoff

```bash
python -m easyeda2kicad_digimou \
  --manufacturer "Texas Instruments" \
  --mpn LM358DR \
  --providers mouser \
  --cad-source mouser \
  --manifest-json ./build/LM358DR-mouser-handoff.json
```

The CLI uses only Search API V2 and returns the exact sanitized Mouser Product
Detail URL. It never fetches or scrapes that page and does not infer whether
the current ECAD source is the manufacturer, SnapMagic, SamacSys, or another
provider. At this stage, `distributor` is `mouser`, while `delivery_partner`
and `model_creator` remain unset until separate package or evidence validation.
Explicit `--cad-source mouser` never falls back to EasyEDA.

Open the Product Detail page yourself, review the ECAD source it currently
offers, and import only a supported native KiCad package whose source and
format can be validated. As checked on 2026-07-30, the public LM358DR page
identified Texas Instruments as the manufacturer and listed a SnapMagic
symbol/footprint under Models. That page observation is not inferred from the
API handoff or recorded as SamacSys provenance. A real package, KiCad CLI
project import, and final KiCad GUI check are still required.

### Import a locally downloaded CAD package

Ultra Librarian example:

```bash
python -m easyeda2kicad_digimou \
  --manufacturer "Analog Devices Inc." \
  --mpn AD5314BRM \
  --cad-source digikey \
  --cad-package ./downloads/official-ultralibrarian-kicad.zip \
  --cad-package-format ultralibrarian-kicad \
  --cad-package-evidence ./downloads/AD5314BRM.evidence.json \
  --full \
  --output ./libs/provider_parts \
  --manifest-json ./build/AD5314BRM-import.json
```

Mouser-linked example, when the package is actually from SamacSys:

```text
--cad-source mouser
--cad-package ./downloads/official-samacsys-kicad.zip
--cad-package-format samacsys-kicad
--cad-package-evidence ./downloads/LM358DR.evidence.json
```

Manufacturer-provided footprint plus STEP/WRL packages use:

```text
--cad-source digikey
--cad-package ./downloads/official-manufacturer-kicad.zip
--cad-package-format manufacturer-kicad
--cad-package-evidence ./downloads/exact-part.evidence.json
```

The hash-bound evidence must preserve the exact DigiKey product/model URLs,
the actual manufacturer source URLs, delivery partner, model creator, and full
manufacturer/MPN identity. A verified footprint plus 3D package without a
symbol is installed as `CAD_PARTIAL` with `SYMBOL_UNAVAILABLE`; the importer
does not invent or substitute a symbol.

CLI input alone is insufficient proof of identity. The package or reviewed
hash-bound evidence must prove exact Manufacturer and full MPN. Mismatch,
ambiguous symbol/footprint selection, missing 3D, malformed KiCad, pin/pad
mismatch, nested archives, path traversal, symlinks, case collisions, more
than 4096 entries, unsafe compression ratio, or size limits fail closed before
output replacement.

The CLI stages and validates native `.kicad_sym`, `.pretty`, and `.3dshapes`
content before atomic installation. Provider packages, cookies, sessions, and
private responses must not be committed.

### Deterministic automatic CAD source selection

`auto` uses verified EasyEDA first, then a validated DigiKey-linked package,
then validated Mouser-linked packages:

```bash
python -m easyeda2kicad_digimou \
  --manufacturer "Example Manufacturer" \
  --mpn "EXACT-MPN-INCLUDING-SUFFIX" \
  --cad-source auto \
  --cad-candidate digikey=./downloads/ultralibrarian-kicad.zip \
  --cad-candidate mouser=./downloads/mouser-linked-kicad.zip \
  --full \
  --output ./libs/provider_parts \
  --manifest-json ./build/auto-selection.json
```

A landing URL alone is not selectable CAD. Every package must pass identity,
KiCad, pin/pad, and 3D validation. Material differences produce
`CAD_SOURCE_CONFLICT` and no installation. The selected source and package
SHA-256 are stored atomically in `<output>.cad-source-lock.json`; reruns must
match that lock and can rebuild from the same local package with `--offline`.

EasyEDA wins only when it can safely export every requested artifact. With
`--cad-source auto`, a missing or invalid requested symbol or footprint, a
pin/pad mismatch, or a missing requested 3D model continues to DigiKey and then
Mouser CAD discovery even when they were not selected as metadata providers. A
provider is preferred only when one product-specific handoff advertises every
missing artifact kind; artifact kinds from separate packages are never
combined. A validated local `--cad-candidate` can then be selected and imported
automatically; an interactive login, agreement, or package request remains a
typed manual handoff and is never bypassed or scraped.

## Registering libraries in one KiCad project

Project modification is explicit opt-in. Keep `--output` inside a disposable or
selected project and pass `--register-project-libraries`:

```bash
python -m easyeda2kicad_digimou \
  --full \
  --lcsc_id C21190 \
  --output ./myproject/libs/my_lib \
  --project ./myproject/board.kicad_pro \
  --register-project-libraries
```

PowerShell:

```powershell
python -m easyeda2kicad_digimou `
  --full `
  --lcsc_id C21190 `
  --output C:\work\myproject\libs\my_lib `
  --project C:\work\myproject\board.kicad_pro `
  --register-project-libraries
```

After successful CAD validation, the CLI updates only project-local
`sym-lib-table` and `fp-lib-table` with:

```text
${KIPRJMOD}/libs/my_lib.kicad_sym
${KIPRJMOD}/libs/my_lib.pretty
```

It does not edit the `.kicad_pro` file. Writes are atomic and detect concurrent changes.
They preserve unknown fields/order, reject nickname/URI collisions, and roll back
if the two-table update fails. An identical rerun is a no-op.

Preview without network, CAD output, or table writes:

```bash
python -m easyeda2kicad_digimou \
  --full \
  --lcsc_id C21190 \
  --output ./myproject/libs/my_lib \
  --project ./myproject \
  --register-project-libraries \
  --dry-run
```

`--project-relative` alone only writes portable 3D links; it never registers
libraries.

## JLCPCB/LCSC resolution in the same command

Every online exact-`--mpn` acquisition checks the public JLCPCB/LCSC catalogue
in the same invocation, regardless of `--providers` or `--cad-source`. No
`--pcba-target` flag or second command is required.

| Status | Meaning |
| --- | --- |
| `JLCPCB_PART_FOUND` | Exact identity proved a canonical `C...` ID; stock may still be zero |
| `MANUAL_GLOBAL_SOURCING_REQUIRED` | No canonical exact ID; use JLCPCB Parts Manager > Global Sourcing |
| `JLCPCB_LOOKUP_FAILED` | Provider/network failure |
| `JLCPCB_IDENTITY_AMBIGUOUS` | More than one exact candidate |
| `JLCPCB_IDENTITY_CONFLICT` | Identity evidence conflicts |

JSON stores the result under `jlcpcb`; CSV has permanent `JLCPCB Part #`,
`LCSC Part #`, match status, checked time, stock, cache state, manual action,
and Global Sourcing candidates. Part-number cells contain a proven canonical
ID or an empty string, never a status sentinel. The KiCad symbol retains only
the existing native `LCSC Part` field.

## Verify the result in KiCad

Generated files are an input to engineering review, not proof that the part is
electrically/mechanically correct.

1. Open the project in KiCad and use the Symbol Chooser. Confirm the expected
   symbol appears under the registered nickname.
2. Place the symbol. Compare every pin number, name, type, and hidden power pin
   with the manufacturer datasheet.
3. Open the footprint in the Footprint Editor. Confirm pad count/numbers,
   pin-to-pad mapping, pitch, body size, orientation/pin 1, courtyard, mask,
   paste, and through-hole drill where applicable.
4. Open the 3D Viewer. Confirm a STEP/WRL model exists, is not mirrored,
   rotated, offset, or scaled incorrectly, and matches the courtyard and pin 1.
5. Inspect the footprint's model path. Project-local output should use
   `${KIPRJMOD}/...`; a machine-global absolute path is not portable.
6. Open the JSON Manifest and confirm `cad.source`, `distributor`,
   `delivery_partner`, `model_creator`, package/artifact hashes, and exact
   Manufacturer/MPN.

For DigiKey, the real AD5314BRM package passed this symbol/pin,
footprint/pad/courtyard, and 3D model/alignment checklist in KiCad 10 on
2026-07-29. The corresponding real Mouser-linked proof remains outstanding
and must not be inferred from fixtures.

## Machine JSON for automation

Use the additive `acquire` subcommand for one stable result:

```bash
python -m easyeda2kicad_digimou acquire \
  --manufacturer "Texas Instruments" \
  --mpn OPA333AIDBVR \
  --providers lcsc,digikey \
  --cad-source easyeda \
  --full \
  --output ./libs/parts \
  --machine-json
```

stdout is exactly one schema-v1 UTF-8 JSON document. Progress is stderr-only,
including on Windows CP932 consoles. Artifact paths use
`path_base=project|output|cwd` plus relative paths; secrets and machine-global
paths are excluded.

Requirements are explicit:

- `--require-cad`
- `--require-provider digikey` (repeatable)
- `--require-jlcpcb-resolution`
- `--require-project-registration`

| Exit | Meaning |
| --- | --- |
| `0` | Success or optional warning |
| `2` | Invalid request |
| `3` | Required manual action |
| `4` | Exact part not found |
| `5` | Identity conflict/ambiguity |
| `6` | Provider/network failure |
| `7` | CAD acquisition/verification failure |
| `8` | Project registration failure |
| `70` | Unexpected internal failure |

Use `--json-events` instead for versioned JSON Lines with `started`,
`provider`, `cad`, `validation`, `project`, and final `completed` events.

Read-only discovery:

```bash
python -m easyeda2kicad_digimou capabilities --machine-json
python -m easyeda2kicad_digimou inspect-project ./board.kicad_pro --machine-json
python -m easyeda2kicad_digimou plan-acquire --manufacturer "Texas Instruments" --mpn OPA333AIDBVR --providers lcsc,digikey --offline --machine-json
python -m easyeda2kicad_digimou verify-artifacts ./result.json --output-root ./libs --machine-json
```

See [MACHINE_JSON.md](docs/MACHINE_JSON.md) for the result/event/headless
schemas, compatibility rules, and independent artifact verifier.

## Troubleshooting

| Symptom/code | Action |
| --- | --- |
| `PARTIAL` with exit `0` | Inspect `provider_errors`; add `--require-providers` if omissions are not acceptable |
| `GUEST_LOOKUP_UNSUPPORTED` / `AUTH_MISSING` | Run `capabilities`; configure your own API credential in the current process |
| `AUTH_FAILED`, 401, or 403 | Verify the credential, app subscription/environment, and provider approval; never paste tokens into logs |
| `RATE_LIMITED` / 429 | Stop retrying and wait for the provider window |
| `NOT_FOUND` | Confirm exact manufacturer and the complete ordering-code MPN |
| `MPN_MISMATCH` / manufacturer conflict | Do not shorten suffixes or override evidence; correct the request/package |
| `CAD_MANUAL_DOWNLOAD_REQUIRED` | Follow the sanitized official handoff, review the agreement, then use `--cad-package` |
| `CAD_IDENTITY_UNPROVEN` | Supply a self-attesting package or reviewed hash-bound evidence |
| `CAD_SOURCE_CONFLICT` | Review both validated packages; automatic selection intentionally stopped |
| `PROJECT_LIBRARY_*_CONFLICT` | Choose a new nickname/output or correct the existing project table |
| `OFFLINE_CACHE_MISS` | Re-run online once where caching is permitted; Mouser is live-only under current terms |
| Garbled human console text on Windows | Machine JSON is always UTF-8; redirect it as bytes or use a UTF-8 terminal |

`--offline` forbids all network access. `--refresh-metadata` bypasses metadata
cache and cannot be combined with `--offline`. `--debug` writes verbose human
diagnostics to stderr and still passes through secret redaction.

## Legacy and advanced usage

Legacy commands remain valid:

```bash
python -m easyeda2kicad_digimou --full --lcsc_id C21190
python -m easyeda2kicad_digimou --symbol --lcsc_id C21190
python -m easyeda2kicad_digimou --footprint --lcsc_id C21190
python -m easyeda2kicad_digimou --3d --lcsc_id C21190
python -m easyeda2kicad_digimou --full --lcsc_id C21190 C25804 C14663
python -m easyeda2kicad_digimou --svg --lcsc_id C21190 --output ./libs/my_lib
```

Default output is under the user's `Documents/Kicad/easyeda2kicad` directory.
An explicit `--output ./libs/my_lib` creates:

- `my_lib.kicad_sym`;
- `my_lib.pretty/`;
- `my_lib.3dshapes/` with STEP/WRL models.

Useful advanced flags:

- `--overwrite` replaces an existing matching library item;
- `--custom-field "Key:Value"` adds non-reserved symbol properties;
- `--datasheet-link manufacturer|lcsc|digikey|mouser` selects an exact
  datasheet source;
- `--manifest-csv PATH`, `--no-price`, and `--no-stock` control BOM output;
- `--show-conflicts` prints deterministic safe diagnostics;
- `HTTPS_PROXY` configures an HTTPS proxy;
- `--use-cache` enables the legacy EasyEDA resource cache.

Architecture and reference documentation:

- [Provider contract, exact matching, caching, and diagnostics](docs/PROVIDER_CONTRACT.md)
- [Architecture and security boundaries](docs/architecture.md)
- [Machine JSON contract](docs/MACHINE_JSON.md)
- [Current implementation/evidence state](docs/CURRENT_STATE.md)
- [Decision log](docs/DECISIONS.md)
- [Footprint command reference](docs/CMD_FOOTPRINT.md)
- [Symbol command reference](docs/CMD_SYMBOL.md)
- [3D command reference](docs/CMD_3D_MODEL.md)
- [Release notes](docs/releases/v1.1.0b3.md)

## License and warranty

This project is licensed under GNU AGPL-3.0; see [LICENSE](LICENSE) and
[NOTICE](NOTICE).

Converted symbols, footprints, and 3D models are not guaranteed correct.
Always compare them with the manufacturer datasheet and mechanical drawing
before fabrication or assembly.
