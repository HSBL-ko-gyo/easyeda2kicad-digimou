# Legacy compatibility verification

Date: 2026-07-22

Upstream baseline: `fff10a38619963d7cb1c57d779655a9ea4572e95`

## Direct baseline/current output comparison

The unmodified baseline was exported with `git archive` and executed separately
from the working tree. Both versions received the same parsed C2040 EasyEDA CAD
payload through an injected API object and used the same output prefix with
`--symbol`, `--footprint`, and `--svg`. Using the same prefix matters because
the legacy footprint embeds its 3D-model path.

| Artifact | SHA-256 in both runs | Equal |
| --- | --- | --- |
| KiCad symbol | `e6cdf3845b6b6553a42e8e211ef59818a4f952ea762b8a484a69402204875653` | yes |
| KiCad footprint | `8995a8935ec3b9ded281b9358a7f93005b9e9652b7f87fe601ad22481699324e` | yes |
| Footprint SVG | `3213faef89fb5aeb7c6e50c50ff4c3d4fe4bb848c56c84bd8a0b23ecc01b6f4d` | yes |
| Symbol SVG | `73b585692a33089a2ddea6eab9edcb4d40f97611762e0eb81b30c162bee10a02` | yes |

No network response, temporary path, API key, or credential is recorded in this
document.

## Checked-in offline golden

`tests/test_legacy_offline_golden.py` runs the legacy-only invocation with the
real C2040 CAD fixture, a temporary `.easyeda_cache`, and a network opener that
immediately fails if called:

```text
--lcsc_id C2040 --symbol --footprint --project-relative --use-cache
```

It asserts exit code 0, exactly one version-banner line on stdout, empty stderr,
no network call, canonical byte equality for symbol/footprint, exact SHA-256,
and absence of a 3D output directory because `--3d` was not requested.

| Checked-in golden | Canonical SHA-256 |
| --- | --- |
| `tests/fixtures/legacy/golden/legacy_c2040.kicad_sym` | `56548f0c154ccee100f0c00d8b85b76ed2fc0126913aa960c38f517f86cbb934` |
| `tests/fixtures/legacy/golden/LQFN-56_L7.0-W7.0-P0.4-EP.kicad_mod` | `f611dd6b66453dd3a9d8d821f7025698c7e050791c44263c3484b2be71509847` |

The focused test most recently reported `1 passed in 0.20s` before the final
full-suite run. It is collected and passes in every current Python matrix run.

## Full regression matrix

| Tree/runtime | Result |
| --- | --- |
| Unmodified baseline, Python 3.9.25 | `177 passed, 69 skipped` |
| Unmodified baseline, Python 3.14.3 | `177 passed, 69 skipped` |
| RC2 pre-RC3 tree, Python 3.9.25 | `666 passed, 71 skipped` |
| RC2 pre-RC3 tree, Python 3.12.13 | `666 passed, 71 skipped` |
| RC2 pre-RC3 tree, Python 3.14.3 | `666 passed, 71 skipped` |

The current RC3 matrix is recorded separately in
`docs/oracle/rc3_reaudit1_quality.md`; the rows above remain historical
compatibility evidence and are not a claim about the current tree.

The 69 inherited skips occur because this checkout does not contain upstream's
optional `tests/reference_outputs/` tree. That missing directory is distinct
from the new checked-in `tests/fixtures/legacy/golden/` evidence above. The two
additional current skips are live DigiKey and Mouser smoke tests whose
credentials were absent.

## Platform boundary

All runtime executions above were on Windows. The current tree is grammar/type
checked with Python 3.9 and unit-tests POSIX and Windows path behavior, including
in-project, out-of-tree, and cross-drive cases. A native Linux runtime E2E was
not available and remains an explicit Release Candidate risk rather than an
unverified compatibility claim.
