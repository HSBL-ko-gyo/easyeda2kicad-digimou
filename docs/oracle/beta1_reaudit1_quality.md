# Public-beta release-prep re-audit 1 quality evidence

Generated: 2026-07-23 (Asia/Tokyo)

The initial public-beta corrective audit reported CANARY PASS, no release
blocker, and RELEASE APPROVED. Release preparation then changed the package
version and public metadata and added release documentation/templates. This
record covers the revised tag candidate; no earlier approval is reused.

## Version and publication identity

- upstream/package version before preparation: `1.0.1`;
- selected PEP 440 version: `1.1.0b1`;
- annotated tag: `v1.1.0b1`;
- display name: `easyeda2kicad +DigiMou`;
- planned fork: `HSBL-ko-gyo/easyeda2kicad-digimou`;
- distribution/import/CLI name: unchanged `easyeda2kicad`;
- PyPI upload: prohibited and not performed.

Because `1.0.1` is an existing stable release, `1.0.1b1` would sort before it.
The additive metadata feature therefore uses the next minor beta.

## Final-tree quality matrix

| Gate | Result |
| --- | --- |
| Python 3.9.25 full pytest | `702 passed, 71 skipped`, exit 0 |
| Python 3.12.13 full pytest | `702 passed, 71 skipped`, exit 0 |
| Python 3.14.3 full pytest | `702 passed, 71 skipped`, exit 0 |
| Explicit legacy/metadata/Manifest release fixtures | `7 passed`, exit 0 |
| Ruff format check | PASS, `59 files already formatted` |
| Ruff lint | PASS |
| Python 3.9 strict mypy over package/tests/setup | PASS, 59 source files |
| `git diff --check` | PASS; only Git LF/CRLF working-tree notices |
| Version/import metadata | PASS, package and distribution `1.1.0b1` |
| CLI help | PASS; legacy and metadata options present |

The skip count is unchanged:

- 69 inherited skips from the absent optional upstream reference-output bundle;
- one DigiKey credentialed live test; and
- one Mouser credentialed live test.

## Clean build and installation

Build tooling was installed only in a temporary external venv. The project
dependency declarations were not changed. A temporary Git index produced clean
snapshot tree `6faae990b5e6793854f4fbc448bfffea696d0285` for the build.

| Gate | Result |
| --- | --- |
| sdist build | PASS |
| wheel build | PASS |
| wheel members | PASS, 37 members, required LICENSE/NOTICE/modules present |
| sdist members | PASS, 52 members, required LICENSE/NOTICE/README/setup/modules present |
| Forbidden archive members | PASS, zero tests/cache/Oracle/venv/credential files |
| Wheel fresh-venv install | PASS |
| sdist fresh-venv install | PASS |
| Installed version/import | PASS for both |
| Installed console `--help` | PASS for both |
| Installed metadata offline startup | PASS, expected typed cache/offline exit 1 |

Release artifact SHA-256:

| Artifact | SHA-256 |
| --- | --- |
| `easyeda2kicad-1.1.0b1.tar.gz` | `f14db949c2d3c5b7bc4e262183b1f14a8eea19e5129ddb8e90839dea8c221e32` |
| `easyeda2kicad-1.1.0b1-py3-none-any.whl` | `13b52e840ebab29b2cf8bec1de5ebb0136d171a7634baa843cb02f4261fa2be7` |
| `RELEASE_NOTES.md` | `6d82b61b7c48907bc8b7426782be5e5959547f743494f98c415bbb9b42746993` |
| `CLI_HELP.txt` | `5116b3d38867f289448cc3b14780ad420c8635ea05e891f2272b886620a03a81` |
| `SHA256SUMS.txt` | `ea7bd83977324d81284e0fb6e2d2efbd10d872bbceb9561340f29aa57d38e042` |

The artifacts and temporary build/install venvs remain outside the repository.
The real Git index has zero staged files, and no build/archive/checksum output
appears in tracked or untracked worktree status.

## Accepted risks

- DigiKey live API E2E with real credentials was not run.
- Mouser live API E2E with real credentials was not run.
- Native Linux process-level E2E was not run.
- The optional inherited reference-output bundle remains absent (69 skips).

These are disclosed beta feedback targets, not new release failures.
