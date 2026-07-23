# Public-beta release-prep re-audit 1 secret audit

Date: 2026-07-23 (Asia/Tokyo)

Audited source artifacts:

- revised candidate: 74 files, 803,147 bytes, SHA-256
  `93f312f93119140709116d036597d9e4ca78f3e97879e2ef644b9784c5474bf4`;
- initial-to-revised release-prep delta: 12 files, 63,485 bytes, SHA-256
  `68187df63a7a093d536c4d48232b56fd2482a37366f4684f959cf946daf84f25`;
- revised audited source tree:
  `334715a99d5ee514338199e27e685db1a78de81e`;
- clean temporary-index candidate apply and applied-tree equality: PASS;
- built package inputs equal the revised candidate package inputs: PASS.

The high-confidence scan found zero private-key headers, AWS access-key
identifiers, GitHub tokens, OpenAI-style API keys, Google API keys, Slack
tokens, or JWT-shaped bearer values in the revised candidate, release-prep
delta, and release artifacts.

The revised full candidate retains five URL-userinfo matches in the already
reviewed fixed sanitizer test fixtures. The release-prep delta has zero
URL-userinfo matches. Neither match set is a real credential. No
credential-bearing query URL was found in either revised diff.

Extracted wheel and sdist trees plus the release asset directory were scanned
separately:

- high-confidence secret patterns: zero;
- URL userinfo: zero;
- credential-bearing query URLs: zero;
- API key, client secret, access token, Authorization header values: zero.

The sdist and wheel contain no tests, cache, Oracle artifact, browser profile,
session cache, virtual environment, credential file, build directory, or
temporary field-audit output. The issue form and security policy explicitly
forbid secrets and unsanitized cache uploads.

The real Git index has zero staged files. Build, install-smoke, cache, venv,
archive, and checksum outputs remain outside or ignored by the repository.

Result: **PASS**.
