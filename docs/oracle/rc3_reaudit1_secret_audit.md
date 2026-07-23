# New RC re-audit 1 secret audit

Date: 2026-07-23 JST

Scope:

- `docs/oracle/rc3_reaudit1_release_candidate.diff`
- `docs/oracle/rc3_reaudit1_delta_from_initial.diff`
- current source, tests, non-diff documents, README, and setup metadata
- the planned re-audit 1 direct attachments

Candidate identities:

- full candidate: 63 files, 723,055 bytes, SHA-256
  `2c25cedc3f3720a3c9b54bc8563688b993d988e5ab75ba6791dc9c24dc23e6c5`
- initial-to-revised delta: 19 files, 37,269 bytes, SHA-256
  `695245d3ddde1a8607af0d17ac887170b7c8de0eb7b6861fa113201260a62b68`
- full and delta clean-index apply checks: PASS

## High-confidence scan

Both diffs and the current non-diff tree have zero occurrences of:

- private-key headers
- AWS access-key identifiers
- GitHub tokens
- OpenAI-style API keys
- Google API keys
- Slack tokens
- JWT-shaped bearer values

The revised delta has zero generic URL-userinfo or credential-like query
matches. The full candidate retains the same fixed sanitizer regression
fixtures as the initial audit:

| Pattern | Added-line matches | Files |
| --- | ---: | --- |
| URL user-info | 5 | `tests/test_metadata_cache.py`, `tests/test_metadata_manifest_fields.py`, `tests/test_provider_base.py` |
| credential-like query parameter | 11 | `tests/test_metadata_cache.py`, `tests/test_metadata_manifest_fields.py`, `tests/test_provider_base.py` |

Every generic match is a non-secret test value. No real credential, Oracle
session cache, browser profile, authentication artifact, or provider token is
included. Values are intentionally not reproduced here.

Result: **PASS**.
