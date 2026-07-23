# Public-beta corrective RC secret audit

Date: 2026-07-23 (Asia/Tokyo)

Artifacts:

- full candidate: 68 files, 750,327 bytes, SHA-256
  `5c848efe9e3dcbbb4dcc632f150cca0e7e824384230de250a18e644a907945d3`;
- RC3-to-current delta: 17 files, 64,625 bytes, SHA-256
  `04004f17a6a90cf0c308acb3d3a11696163bbe98c96cf9100dab000a7420c3d7`;
- candidate tree: `0c7b7f01e3389ef7efbecec40574619d292bdf78`;
- clean temporary-index apply/check and applied-tree equality: PASS.

The high-confidence scan found zero private-key headers, AWS access-key
identifiers, GitHub tokens, OpenAI-style API keys, Google API keys, Slack
tokens, or JWT-shaped bearer values in:

- the full candidate;
- the RC3-to-current delta; and
- the current non-diff source/test/document tree.

The full candidate retains only the previously reviewed sanitizer fixtures:
five URL-userinfo and nine credential-like query matches in
`tests/test_metadata_cache.py`, `tests/test_metadata_manifest_fields.py`, and
`tests/test_provider_base.py`. The RC3-to-current delta has zero matches in both
generic categories. All retained matches are fixed non-secret test inputs; no
value is reproduced here.

No Oracle profile, browser session/cache, authentication artifact, Provider
credential, token, credential-bearing URL, build cache, virtual environment, or
temporary field-audit output is included in the candidate.

Result: **PASS**.
