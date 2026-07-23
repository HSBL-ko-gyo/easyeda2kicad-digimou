# New RC local quality evidence

Generated: 2026-07-23 (Asia/Tokyo)

## Scope and starting point

The user opened a new Release Candidate cycle without reopening RC2. Before any
new source edit:

- RC2 `release_candidate.diff` still had SHA-256
  `cf4527f61101258a14cfff487f987a86111da87e453f06760eadb156066a421b`;
- all ten source/test hashes in `rc2_current_source_canary.md` matched; and
- no RC2 answer, diff, canary, or re-audit count was changed.

The new source changes are limited to RB-RC2-1, SF-RC2-1, their regression
tests, and the cache-schema invalidation required to prevent an old false exact
success.

## Focused acceptance probe

Command scope: the three Provider tests, metadata service, and CLI path tests,
selected for the new exact-candidate and manifest-collision cases.

Result:

```text
22 passed, 192 deselected
```

The selected cases cover:

- indeterminate raw MPN plus a valid exact candidate;
- exact raw MPN whose complete record cannot be parsed;
- a provably different raw MPN with malformed unrelated fields;
- all candidates indeterminate;
- live-shaped and direct raw-response replay behavior for all three Providers;
- Mouser zero count with missing or null `Parts`;
- incomplete exact failures not being written to raw/normalized cache;
- offline miss and refresh failure consistency;
- manifest same/ancestor, direct and multi-level ancestors;
- relative `..` normalization and pure Windows case-insensitive semantics;
- allowed manifest children and adjacent path prefixes; and
- collision exit before metadata resolution or any output path is created.

The complete related-file run then reported:

```text
252 passed
```

## Full quality matrix

| Gate | Result |
| --- | --- |
| Python 3.9.25 full pytest | `687 passed, 71 skipped` |
| Python 3.12.13 full pytest | `687 passed, 71 skipped` |
| Python 3.14.3 full pytest | `687 passed, 71 skipped` |
| Ruff format check | PASS, `59 files already formatted` |
| Ruff security lint | PASS |
| Python 3.9 strict mypy | PASS, 59 source files |
| `git diff --check` | PASS; only existing LF/CRLF notices |

The pass count increased by 21 from RC2. The skip count did not increase:

- 69 inherited skips still reflect the absent upstream
  `tests/reference_outputs/` bundle; and
- two live Provider tests still skip because DigiKey/Mouser credentials are
  absent.

No credentialed DigiKey/Mouser live call or native Linux process E2E was added;
those remain the same ACCEPTABLE RISK items as RC2.

## Cache compatibility

`CACHE_SCHEMA_VERSION` is 3. The canonical request and key therefore differ from
schema v2. A schema-v2 pair is rejected online and is explicit corruption
offline if presented under a current key. New indeterminate or
exact-but-unparseable responses raise before `MetadataCache.write`, so they
cannot become a normalized success. Offline never calls the Provider after such
a failed online attempt, and refresh propagates the same typed Provider failure
without publishing a replacement pair.

## Post-test mutation boundary

After the matrix above, only documentation and new Oracle evidence files are
being created. Product source and tests must continue to match the new source
canary through the Oracle audit.
