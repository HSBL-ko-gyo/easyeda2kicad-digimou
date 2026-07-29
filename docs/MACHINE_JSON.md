# Machine JSON contract

`easyeda2kicad acquire --machine-json` is the versioned, non-interactive CLI
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
`easyeda2kicad/schemas/machine-result-v1.schema.json`.

## Example

```powershell
python -m easyeda2kicad acquire `
  --manufacturer "Texas Instruments" `
  --mpn OPA333AIDBVR `
  --providers lcsc,digikey `
  --cad-source easyeda `
  --full `
  --output .\libs\parts `
  --machine-json
```

```bash
python -m easyeda2kicad acquire \
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

## Current phase boundary

Phase A provides the one-document `acquire --machine-json` result. JSON Lines
events and the read-only `capabilities`, `inspect-project`, `plan-acquire`, and
`verify-artifacts` commands are Phase B and are not claimed here.
