# Secret audit

## Audit metadata

- Result: **PASS**
- Executed: 2026-07-22 23:01:58 JST (UTC+09:00)
- Git inventory: 109 tracked or untracked, non-ignored files
  (52 tracked, 57 untracked)
- Head: `fff10a38619963d7cb1c57d779655a9ea4572e95`
- Branch: `feature/multi-distributor-metadata`
- Additional scopes: full Git history, tracked working diff, fixtures/examples,
  ignored `.easyeda_cache/`, and the built sdist/wheel
- Excluded: virtual environments, ordinary build intermediates, `.git` object
  storage outside the history scan, and Oracle's browser profile/session cache
  outside this repository

No matched value, environment-variable value, authorization payload, browser
profile path, or Oracle session data was printed or copied into this report.

## Method

Read-only scans reported only pattern category, count, and file path. The
high-confidence categories were:

- PEM/OpenSSH private-key markers;
- AWS, GitHub, OpenAI, Slack, and Google key/token formats;
- JWT-shaped values;
- URLs containing userinfo;
- secret-bearing URL query values;
- direct assignments to the documented DigiKey/Mouser credential variables;
  and
- sensitive filenames such as `.env*`, credential/secret documents, and
  private-key containers.

A broader literal scan was reviewed manually for test-only placeholders and
formatted authorization templates. The scan covered the complete non-ignored
working-tree inventory so untracked candidate files were not omitted. `git
diff --binary` and `git log -p --all` were scanned in memory; matched values were
never emitted.

The ignored runtime cache was scanned separately (15 files). Archive members
were read in memory: 45 sdist members and 37 wheel members. The current
DigiKey/Mouser environment-variable state was checked as a boolean only; all
three required variables were unset.

## Results

No likely real credential, private key, token, credential-bearing URL,
hard-coded authorization value, sensitive filename, or Oracle profile/session
copy was found.

| Scope/category | Result |
| --- | --- |
| Working-tree high-confidence formats | 0 findings |
| Direct credential-environment assignments | 0 findings |
| Sensitive tracked/untracked filenames | 0 findings |
| Full Git history high-confidence formats | 0 findings |
| Tracked working diff high-confidence formats | 0 findings |
| `.easyeda_cache/` credential/high-confidence scan | 0 findings in 15 files |
| sdist archive | 0 findings in 45 members |
| wheel archive | 0 findings in 37 members |
| DigiKey/Mouser credential availability | all required variables unset |
| Immutable RC diff, SHA-256 `cf4527f6…a421b` | 0 high-confidence findings |
| Nine post-audit status/review documents, 2026-07-23 00:46 JST | 0 high-confidence findings |

Synthetic userinfo or secret-query values were found only in the following
tests, where assertions verify their removal:

- `tests/test_metadata_cache.py`
- `tests/test_metadata_manifest_fields.py`
- `tests/test_provider_base.py`

The broader credential-literal scan additionally selected the official-client
redaction/authentication tests in `tests/test_provider_digikey.py` and
`tests/test_provider_mouser.py`. It also selected
`easyeda2kicad/providers/digikey.py` because the authorization header uses a
`Bearer %s` formatting template; no token literal is embedded there. All of
these findings are deliberate fake values or placeholders.

## Defense-in-depth correction

The audit found that the general cache redactor handled exact camelCase names
but not every prefixed camelCase secret suffix. The implementation now removes
keys such as `oauthAccessToken`, `myClientSecret`, and `databasePassword` in
both structured data and URL queries while retaining non-secret names such as
`accessTokenExpiresAt` and `tokenizer`. The metadata cache/provider regression
set passed (`38 passed`), and the subsequent complete three-runtime matrix
passed. Decision D024 records the boundary.

`.gitignore` now excludes `.env.*` (except `.env.example`), common
credential/secret JSON or YAML filenames, PEM/key files, and PKCS#12 containers,
in addition to `.env`, virtual environments, caches, and build outputs.

## Conclusion

**PASS.** The candidate contains no detected real credential leakage. The only
generic matches are explicit redaction fixtures and a runtime formatting
template. The generated Release Candidate diff was scanned after creation with
zero high-confidence findings; its full SHA-256 is
`cf4527f61101258a14cfff487f987a86111da87e453f06760eadb156066a421b`.
After Oracle completed, the nine documentation-only status/disposition files
were scanned again across private-key, major service-token, JWT, URL-userinfo,
and secret-query patterns with zero findings. No Oracle profile, session cache,
cookie, or authentication material was copied into the repository.
