# Public-beta corrective RC quality evidence

Generated: 2026-07-23 (Asia/Tokyo)

This is a distinct RC after the preserved RC3 approval. The public-beta
field-table audit required runtime changes, so no earlier Oracle approval is
reused.

## Quality matrix

| Gate | Result |
| --- | --- |
| Focused field/manufacturer/overwrite regressions | `7 passed`, exit 0 |
| Python 3.9.25 full pytest | `702 passed, 71 skipped`, exit 0 |
| Python 3.12.13 full pytest | `702 passed, 71 skipped`, exit 0 |
| Python 3.14.3 full pytest | `702 passed, 71 skipped`, exit 0 |
| Ruff format check | PASS, `59 files already formatted` |
| Ruff lint | PASS |
| Python 3.9 strict mypy | PASS, 59 source files |
| `git diff --check` | PASS; only Git LF/CRLF working-tree notices |

The skip count is unchanged:

- 69 inherited skips from the absent optional upstream reference-output bundle;
- one DigiKey credentialed live test; and
- one Mouser credentialed live test.

## Real-output acceptance

Both OPA333AIDBVR/C30878 and LM321MF/NOPB/C131103 succeeded through:

- legacy `--lcsc_id` symbol/footprint generation;
- metadata `LCSC ID + MPN + Manufacturer + JSON/CSV Manifest` generation;
- exact Manufacturer verification using same-part LCSC evidence;
- complete symbol/footprint property inspection; and
- a second `--overwrite` run.

For both parts, legacy and metadata symbol/footprint bytes match when generated
with the same path context. Metadata adds zero property keys, no property is
duplicated, and all four metadata artifacts remain byte-identical after
`--overwrite`. `LM321MF/NOPB` retains one sanitized root symbol rather than
growing another entry. Full evidence is in `docs/FIELD_TABLE_AUDIT.md`.

## Compatibility and publication gate

- CLI spellings, Python import/package name, manifest schemas, cache schema, and
  dependencies are unchanged.
- LCSC-ID/MPN mismatch remains fatal.
- Provider/CAD responsibilities are unchanged.
- No commit, tag, push, fork, release, or PyPI action has occurred.
- Publication remains blocked until the new Oracle audit passes its canary and
  reports no release blocker.
