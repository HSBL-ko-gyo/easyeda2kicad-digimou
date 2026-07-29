# v1.1.0b3 initial release-candidate audit

Oracle CLI: `0.16.1`
Session: `digimou-b3-final-audit`
Engine: browser with `--browser-manual-login`
Requested/resolved model: `Thinking 5.5` / `Thinking 5.5`
Model verification: `yes`
Input: 10 current files, 50.32k input tokens
Result: `CANARY PASS / RELEASE BLOCKED`

The following answer is preserved verbatim.

---

CANARY PASS

# INITIAL RC Audit — easyeda2kicad +DigiMou v1.1.0b3

## Input verification

All ten individual files were present and readable. The input includes the
AGENTS policy canary, current README and release notes, workflow and checker
implementation, both changed runtime files, version identity, and focused
runtime tests. No bundle or prior repository state was used.

The canary prohibits Pro-tier Oracle use for RC audits; this audit did not
invoke one.

`README.md`, the release notes, and `_version.py` consistently identify
`1.1.0b3` / `v1.1.0b3`. The distribution, command, and package remain distinct
as `easyeda2kicad-digimou`, `easyeda2kicad-digimou`, and
`easyeda2kicad_digimou`.

The six attached Python files syntax-compile, and `1.1.0b3` is a valid PEP 440
prerelease. The supplied full-suite, Ruff, mypy, build, Twine, wheel-content,
secret-scan, and isolated-install results were treated as local release
evidence rather than rerun from these detached files.

## RELEASE BLOCKER

### RB-B3-1 — Existing service handoff can bypass the new artifact-aware fallback

**Affected files**

* `easyeda2kicad_digimou/__main__.py`
* `easyeda2kicad_digimou/metadata/service.py`
* `tests/test_cad_auto_handoff.py`

When EasyEDA supplies no `cad_data`, `resolve_metadata()` performs its older
automatic handoff first, using only the selected metadata providers and without
receiving the requested artifact kinds. It then stores that result in
`result.cad_discovery`. The CLI's newer expanded fallback to DigiKey and Mouser
runs only when `result.cad_discovery is None`.

Consequences include:

* `--providers digikey --cad-source auto` can stop at a DigiKey authentication
  or incomplete-artifact result without trying Mouser.
* A handoff selected before CLI artifact verification is not checked against
  the actual `--symbol`, `--footprint`, `--3d`, or `--full` request.
* The release claim that missing EasyEDA artifacts continue through DigiKey
  and then Mouser even when not metadata providers is not consistently true.

**Smallest compatible correction**

For CLI `--cad-source auto`, call
`resolve_metadata(..., discover_auto_handoff=False)` and perform exactly one
artifact-aware handoff after `_verify_metadata_cad()` and 3D inspection. Keep
direct service behavior unchanged if external callers depend on it.

Add a regression where EasyEDA is entirely unavailable, only DigiKey is
selected for metadata, DigiKey returns an authentication gap, and Mouser must
still be attempted with the complete requested artifact set.

### RB-B3-2 — Artifact filtering can accept split packages and return irrelevant handoffs

**Affected files**

* `easyeda2kicad_digimou/metadata/service.py`
* `tests/test_cad_auto_handoff.py`

The selector flattens `artifact_kinds` from every candidate under one
distributor into a union. Separate packages—one containing a symbol and another
a footprint—can therefore appear to satisfy a request that no single
selectable package satisfies. If no provider satisfies the required kinds, the
code nevertheless returns the first attempt, which may be a manual handoff
advertising none of the missing artifacts.

The returned `available_sources` and `missing_artifacts` are also not narrowed
to the EasyEDA artifacts being replaced. The existing footprint test verifies
only the successful second-provider case; it does not cover a no-match result.

**Smallest compatible correction**

Require one `CadSourceAvailability` entry to contain every required artifact
kind. Filter returned availability entries and artifact lists to the requested
missing kinds. When no candidate qualifies, return a non-actionable
`CAD_DOWNLOAD_UNAVAILABLE`/authentication result rather than the first
irrelevant `CAD_MANUAL_DOWNLOAD_REQUIRED` result.

Add regressions for:

* neither provider advertising the missing kind;
* required kinds split across separate source entries;
* irrelevant provider artifacts being absent from the final fallback result.

### RB-B3-3 — A runtime path still invents SamacSys provenance for Mouser

**Affected files**

* `easyeda2kicad_digimou/metadata/service.py`
* `tests/test_cad_auto_handoff.py`

`_external_cad_not_acquired()` hardcodes Mouser's `delivery_partner` as
`samacsys` and labels the route “Mouser / SamacSys,” despite having no package
or page evidence.

This contradicts the corrected README contract that a Mouser Product Detail
URL alone proves neither delivery partner nor model creator.

The focused fixture also encodes and asserts SamacSys as the default Mouser
partner.

**Smallest compatible correction**

Set `delivery_partner=None` and use a neutral label such as “Mouser-linked
official handoff.” Populate a partner or creator only from separately validated
evidence. Update the fixture and add a regression asserting that evidence-free
Mouser failures contain neither `samacsys` nor another inferred partner.

### RB-B3-4 — Human CLI logging does not enforce credential redaction

**Affected files**

* `easyeda2kicad_digimou/__main__.py`
* `tests/test_cli_metadata_e2e.py`

Machine-mode logging uses `_MachineLogFormatter`, which applies
`redact_configured_secret_text()`. The ordinary human CLI installs a plain
`logging.Formatter`, and existing handlers are left untouched. Therefore the
human/debug sink does not guarantee redaction if any record contains a
configured credential.

The new credential test confirms the environment-variable name and setup URL,
but it does not place sentinel credential values in the environment and prove
they are absent from human logs.

**Smallest compatible correction**

Apply a credential-redacting handler filter or formatter to every human CLI
handler, including handlers that already exist. Add a test setting sentinel
values for all three credential variables, deliberately emitting those values
through a diagnostic/debug record, and asserting that stderr, stdout,
manifests, and captured logs contain none of them.

### RB-B3-5 — The README monitor publishes raw untrusted repository content

**Affected files**

* `tools/readme_consistency.py`
* `.github/workflows/readme-consistency.yml`
* focused monitor tests

The report includes raw commit subjects and raw production paths. Commit
subjects are unbounded; Git paths may contain control characters, newlines,
backticks, mentions, links, or secret-like text.

The workflow reads that report and posts it verbatim to a public issue without
escaping, redaction, or a size bound.

This permits noisy mentions, malformed Markdown, oversized issue bodies, and
republication of secret-bearing subjects or filenames, contrary to the release
note's public-issue safety rule.

**Smallest compatible correction**

Do not place raw subjects or paths in the public issue. Publish canonical
commit SHAs, counts, safe option names, and a bounded neutral summary. If raw
details are retained anywhere, strip control characters, neutralize
mentions/Markdown, apply configured-secret redaction, truncate each field, and
enforce a total issue-body limit. Add hostile-subject and hostile-filename
tests.

## SHOULD FIX

### SF-B3-1 — The monitor silently passes common undocumented production changes

**Affected files**

* `tools/readme_consistency.py`
* monitor tests
* `docs/releases/v1.1.0b3.md`

A generic documentation gap is detected only for newly added surface files or
commit subjects matching a narrow prefix list. A production change committed
as `fix:`, `security:`, `perf:`, `refactor:`, or another normal subject can
pass without README review. Additionally, any change to `README.md`, even an
unrelated typo, suppresses the generic gap.

That is weaker than the release-note claim that the monitor checks
production-feature changes.

**Smallest compatible correction**

Do not treat `README.md changed` as proof of coverage. Either make every
detected production-surface change require an explicit documentation-review
result, or narrow the public claim to the exact heuristic implemented. Expand
tests for `fix:` changes and unrelated README edits.

### SF-B3-2 — A tag named like the default branch passes the branch-scope test

**Affected file**

* `.github/workflows/readme-consistency.yml`

The workflow triggers on all pushes and checks only whether `github.ref_name`
equals the default branch. A tag with the same short name as the default branch
also satisfies that expression.

**Smallest compatible correction**

Require a branch ref explicitly, for example:

`github.ref_type == 'branch' && github.ref_name ==
github.event.repository.default_branch`

Keep `workflow_dispatch` as the explicit manual exception.

### SF-B3-3 — Focused tests do not cover the full release claim matrix

**Affected files**

* `tests/test_cad_auto_handoff.py`
* `tests/test_cli_metadata_e2e.py`

The auto-handoff tests cover an unusable requested footprint, but not:

* a total EasyEDA CAD miss with only one external metadata provider selected;
* missing/invalid symbol;
* pin-pad mismatch;
* requested 3D absence;
* no provider advertising the missing kinds;
* artifact kinds split across separate packages;
* evidence-free Mouser provenance;
* secret sentinels in human logging.

The current CLI test also mocks `resolve_metadata()` after it has already
produced a result, so it cannot expose the service/CLI short-circuit in
RB-B3-1.

**Smallest compatible correction**

Parameterize the fallback test over `symbol`, `footprint`, `model_3d`, pin-pad
mismatch, and complete CAD absence, with provider selection varied
independently from CAD discovery.

## ACCEPTABLE RISK

### AR-B3-1 — Credentialed Mouser package/live gap

A real Mouser-linked package has not completed project registration, KiCad CLI,
and KiCad GUI validation. Complete Mouser CAD support remains explicitly
unclaimed.

### AR-B3-2 — Native Linux process E2E gap

Native Linux process E2E remains outside the supplied release evidence.

### AR-B3-3 — Inherited reference-output skips

The inherited upstream reference-output bundle remains outside the available
evidence and is preserved as a disclosed limitation.

## OPTIONAL

### OPT-B3-1 — Duplicate README heading

`README.md` contains “Machine JSON for automation” twice consecutively.

### OPT-B3-2 — Legacy banner uses the upstream script name

Normal human invocation prints `easyeda2kicad.py`, while `--version` correctly
prints the distinct +DigiMou identity. This is cosmetic but can confuse copied
logs.

### OPT-B3-3 — Pin GitHub Actions by immutable commit

`actions/checkout@v4` and `actions/github-script@v7` are tag-pinned rather than
commit-pinned.

## RESOLVED

### RES-B3-1 — Version, tag, distribution, package, and no-PyPI identity

`1.1.0b3` is consistent across the README, release notes, and runtime identity.
The GitHub prerelease/tag form is `v1.1.0b3`; the package and command remain
distinct from upstream, and PyPI publication is explicitly excluded.

### RES-B3-2 — Explicit CAD sources remain no-fallback

EasyEDA CAD is used only for `easyeda` and `auto`. Explicit DigiKey and Mouser
source branches perform their own handoff and do not silently call EasyEDA.

### RES-B3-3 — Login, agreements, requests, and downloads remain manual

The automatic path produces typed handoff/action results and does not treat a
landing page as an acquired package. The focused test asserts that `package`
remains `None`.

### RES-B3-4 — Credential guidance uses exact names and official URLs

The guidance names `DIGIKEY_CLIENT_ID`, `DIGIKEY_CLIENT_SECRET`, and
`MOUSER_API_KEY`, covers missing and rejected credentials, and uses fixed or
sanitized official setup URLs. It does not prompt for or print credential
values in the changed guidance path.

The human logging sink still requires RB-B3-4 before the no-secret-logging
contract is complete.

### RES-B3-5 — README Mouser wording and supported package formats

The README correctly separates distributor, delivery partner, and model
creator. A Product Detail URL is not represented as SamacSys evidence, while
separately validated Ultra Librarian, SamacSys, and manufacturer-native package
formats remain documented as supported.

### RES-B3-6 — Monitor permissions, exact-range deduplication, and shell safety

The workflow grants only `contents: read` and `issues: write`. Its marker
deduplicates reruns of the same base/head range. Shell values are passed as
quoted arguments, and the checker invokes a fixed `git` executable through
`subprocess.run()` without a shell.

### RES-B3-7 — Legacy surfaces remain present

The legacy `--lcsc_id`, symbol, footprint, 3D, full, SVG, output naming, hidden
abbreviation compatibility, and `${EASYEDA2KICAD}`-oriented default layout
remain in the attached CLI.

### RES-B3-8 — No new CLI option

Within the attached v1.1.0b3 delta, **no new product CLI option exists**. The
beta changes existing `--cad-source auto` behavior, diagnostics,
documentation, and monitoring.

RELEASE BLOCKED
