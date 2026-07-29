# Machine JSON contract

`easyeda2kicad-digimou acquire --machine-json` is the versioned, non-interactive CLI
surface for scripts, CI, and AI/EDA tooling. The legacy root command remains
unchanged.

## Output boundary

- stdout contains exactly one UTF-8 JSON document followed by one newline.
- The version banner is omitted. Progress and human diagnostics use stderr.
- The writer emits UTF-8 bytes directly, so a Windows CP932 console does not
  change or truncate the JSON.
- Machine mode does not prompt, open a browser, or launch KiCad.
- Values cross a credential-stripping boundary before stdout. Raw provider
  responses, credentials, tokens, headers, secret-bearing URLs, and global
  machine paths are not result fields.

The checked-in and packaged schema is
`easyeda2kicad_digimou/schemas/machine-result-v1.schema.json`.

## Example

```powershell
python -m easyeda2kicad_digimou acquire `
  --manufacturer "Texas Instruments" `
  --mpn OPA333AIDBVR `
  --providers lcsc,digikey `
  --cad-source easyeda `
  --full `
  --output .\libs\parts `
  --machine-json
```

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

Provider omissions remain optional unless required. Repeat
`--require-provider` to require exact normalized records:

```text
--require-provider lcsc --require-provider digikey
```

Other requirement switches are:

- `--require-cad`
- `--require-jlcpcb-resolution`
- `--require-project-registration`

`--require-project-registration` must accompany
`--register-project-libraries` and the existing explicit `--project`,
`--output`, symbol, and footprint options. It does not opt in to project
modification by itself.

## Result fields

Every result contains:

- `schema_version`, `request_id`, `command`, `status`, and `exit_code`;
- exact `identity`;
- normalized per-provider status, record, and safe diagnostic;
- CAD source, distributor, delivery partner, model creator, retrieval mode,
  package hash, verification, and discovery status;
- JLCPCB/LCSC resolution;
- hashed artifacts;
- project-table changes;
- typed `warnings`, `errors`, and `actions_required`.

Artifact and project paths are never machine-global. Each artifact supplies a
relative `path` plus `path_base=project|output|cwd`. Project changes always use
`path_base=project`. `sha256` is the content hash of the installed artifact.

An optional missing provider can produce `SUCCEEDED_WITH_WARNINGS` and exit 0.
When the same capability is required, status and exit code reflect the typed
failure or manual action. `actions_required` can also accompany an optional
warning; callers decide whether optional actions matter.

## Exit codes

| Exit | Meaning |
| --- | --- |
| `0` | Success or optional warning |
| `2` | Invalid request |
| `3` | Required manual action |
| `4` | Exact part not found |
| `5` | Identity conflict or ambiguity |
| `6` | Provider, network, authentication, rate-limit, or required cache failure |
| `7` | CAD acquisition, export, or verification failure |
| `8` | Project registration failure |
| `70` | Unexpected internal failure |

The process exit code always equals the JSON `exit_code`.
When several required capabilities fail, every typed item remains in the
result. The single process code uses this deterministic precedence:
internal failure, identity, CAD, project registration, provider, not found,
then manual action (invalid input is rejected before acquisition).

## Versioning policy

Schema version `1` is closed and explicit: unknown top-level and nested fields
are rejected. Producers do not silently add fields or enum values within v1.
A change that alters required fields, field meaning, enum values, status/exit
mapping, path semantics, or value types requires a new schema version. Fixes
that only make sanitization stricter or correct a producer to match the
checked-in v1 schema do not change the version.

Consumers should select behavior from `schema_version`, `status`, `exit_code`,
and typed codes, not terminal prose. They should verify every returned artifact
hash before using it.

## JSON Lines events

Use `--json-events` instead of `--machine-json` to receive UTF-8 JSON Lines:

```bash
python -m easyeda2kicad_digimou acquire \
  --manufacturer "Texas Instruments" \
  --mpn OPA333AIDBVR \
  --providers lcsc,digikey \
  --offline \
  --json-events
```

Every event contains `event_schema_version=1`, the same 32-character request
ID, a sequence starting at 1, a fixed type, and a type-specific payload. Event
types are `started`, `provider`, `cad`, `validation`, `project`, and
`completed`. The last event always embeds the same machine-result v1 document
under `payload.result`, including provider failures, manual handoffs, invalid
requests, interruptions, and bounded internal failures.

`--machine-json` and `--json-events` are mutually exclusive. Validate each
event with `easyeda2kicad_digimou/schemas/machine-event-v1.schema.json`, then validate
the final `payload.result` with `machine-result-v1.schema.json`.

## Read-only discovery

Four JSON-only commands expose safe planning and inspection data:

- `capabilities` reports supported providers, CAD source handoff behavior, and
  authentication state as booleans only.
- `inspect-project --project PATH` parses project-local library tables and
  returns project-relative paths, hashes, and entries without changing them.
- `plan-acquire` accepts identity, provider, CAD, requirement, and optional
  project-registration inputs, then reports planned network/write stages
  without provider requests or filesystem writes.
- `verify-artifacts --result FILE` verifies the relative artifact paths and
  SHA-256 values in a machine-result document. Supply `--project-root`,
  `--output-root`, or `--cwd-root` for the corresponding `path_base`.

Their result schema is
`easyeda2kicad_digimou/schemas/headless-result-v1.schema.json`. Global paths, secret
values, raw responses, and credential variable names are not returned.
The commands always emit JSON, while also accepting `--machine-json` for an
explicit machine-mode spelling. `inspect-project PROJECT` and
`verify-artifacts RESULT` are positional aliases for `--project PROJECT` and
`--result RESULT`.

Example:

```bash
python -m easyeda2kicad_digimou capabilities
python -m easyeda2kicad_digimou inspect-project --project ./board.kicad_pro
python -m easyeda2kicad_digimou plan-acquire \
  --manufacturer "Texas Instruments" \
  --mpn OPA333AIDBVR \
  --providers lcsc,digikey \
  --offline
python -m easyeda2kicad_digimou verify-artifacts \
  --result ./result.json \
  --output-root ./libs
```

The independent standard-library example verifies the same hashes without
importing this package:

```bash
python examples/verify_machine_artifacts.py \
  result.json \
  --base output=./libs
```

Read-only commands never contact a provider, prompt, launch a browser/KiCad, or
write project/artifact files. `plan-acquire` can return proposed table changes,
but applying them still requires the separate acquisition command and its
explicit `--register-project-libraries` opt-in.
