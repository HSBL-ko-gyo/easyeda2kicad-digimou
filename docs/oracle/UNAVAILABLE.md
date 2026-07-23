# Oracle availability incident history

Recorded: 2026-07-22 (Asia/Tokyo)  
Oracle CLI: 0.16.0  
Current state: **resolved for Architecture Review and RC review transport**

## Initial failure

The first Architecture Review attempt could not use the preferred API engine
because `OPENAI_API_KEY` was not configured. The browser engine then reported
that its private Chrome profile had not yet been initialized and signed in. No
answer was produced. No credential, browser profile, cookie, token, or Oracle
session cache was copied into the repository or review prompt.

## Initialized-profile stalls

After the user initialized the Oracle-only Chrome profile, authentication
succeeded. Earlier foreground captures nevertheless stalled or exceeded the
capture timeout without a complete review. Under the user's revised policy,
these pre-RC failures were recorded and implementation continued; the review
remained a mandatory pre-RC task.

The later parent session `easyeda-architectu-full-review` successfully attached
the 40-file bundle and verified its requested standard model, but its response
again outlived the 40-minute capture. A follow-up in the same conversation,
`easyeda-architectu-review-followup`, recovered the complete answer. It is saved
as `docs/oracle/architecture_review.md` and dispositioned in
`docs/DECISIONS.md`.

## Resolution and active policy

This file is retained as an audit trail, not as a current availability blocker.
The Architecture Review is complete. The valid Release Candidate re-audit also
completed on 2026-07-23 and is saved in
`docs/oracle/release_candidate_audit.md`; that audit blocked release on a code
finding, not on Oracle availability. Both review types used:

- `--engine browser`
- `--browser-manual-login`
- the initialized Oracle-only profile outside this repository
- a verified non-Pro/standard model

For a future RC cycle, an Oracle outage before the RC boundary is recorded while
Codex continues ordinary implementation. Do not silently omit the review. If
Oracle remains unavailable at the RC boundary, stop there; otherwise save and
disposition the audit before reporting the RC. The present cycle stopped because
the second/final re-audit retained RB-RC2-1.
