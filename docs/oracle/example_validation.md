# Manifest example validation

## Validation metadata

- Result: **PASS**
- Executed: 2026-07-22 22:56:04 JST (UTC+09:00)
- Command: `.venv\\Scripts\\python.exe -m pytest -q tests\\test_documented_examples.py`
- Result: `4 passed in 0.07s`
- Inputs:
  - `docs/examples/OPA333AIDBVR.manifest.json`
  - `docs/examples/LM321MF-NOPB.manifest.json`
  - `docs/examples/CAD_NOT_FOUND.mock.manifest.json`

## Checked invariants

The checked-in test parses each UTF-8 JSON document through the current
`MergedPart` model and asserts a lossless `from_dict()` / `to_dict()` round
trip. It also verifies:

- every distributor record has the same conservative normalized exact MPN as
  the merged identity;
- `provider_diagnostics` is present in all three schema instances;
- populated raw-response cache keys are lowercase 64-character SHA-256 values;
- product and datasheet links are public HTTP(S), contain no userinfo, and have
  no recognized credential-bearing query parameter;
- generated CAD paths are relative, contain no parent traversal, and are not
  Windows drive-absolute;
- the KiCad property projection excludes stock, price, MOQ, currency, retrieval
  time, provider errors, and provider diagnostics;
- the mocked CAD-not-found example derives manufacturer authority explicitly
  from `--manufacturer`, not from an unverified distributor alias; and
- root and CAD states in that mock are both `CAD_NOT_FOUND`.

No manifest value is printed by the test or copied to this audit record.

## Results

| Example | Model round trip | Exact MPN | URLs/cache key | Portable paths | Provider diagnostics | KiCad volatile exclusion | CAD semantics |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `OPA333AIDBVR.manifest.json` | PASS | PASS | PASS | PASS | PASS | PASS | `VERIFIED` |
| `LM321MF-NOPB.manifest.json` | PASS | PASS | PASS | PASS | PASS | PASS | `VERIFIED` |
| `CAD_NOT_FOUND.mock.manifest.json` | PASS | PASS | PASS | PASS | PASS | PASS | `CAD_NOT_FOUND` |

The two verified examples were produced by real public LCSC catalogue and
EasyEDA CAD calls. Their current records are LCSC-only because DigiKey/Mouser
credentials were not present. The mock is explicitly identified by both its
filename and its documented invocation; it contains no EasyEDA component ID,
symbol, footprint, 3D model, or generated CAD path.

## Conclusion

**PASS.** The three examples conform to the current model, preserve exact
identity and CAD-status semantics, use portable paths, and keep volatile sales
or diagnostic information outside the KiCad symbol-property projection.
