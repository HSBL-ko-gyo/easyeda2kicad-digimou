# v1.1.0b3 Oracle transport and model-budget incident

Recorded: 2026-07-30 (Asia/Tokyo)
Oracle CLI: `0.16.1`

## Summary

The valid b3 release-candidate audit used the browser engine,
`--browser-manual-login`, and explicitly selected the verified standard
`Thinking 5.5` model. Before that valid audit, the first-time login helper was
started from Oracle's diagnostic command without an explicit `--model`.
Oracle's default resolved that two-character `HI` setup prompt to
`gpt-5.5-pro`.

This violated the repository rule that Pro must never be requested or selected.
The helper was stopped as soon as its model was visible. `oracle status`
subsequently recorded the setup session `hi-2` as completed with two
characters. It received no source file, no release prompt, and produced no
release review. It is not counted as an audit or authorization to use Pro
again.

## Transport attempts

1. `digimou-b3-release-audit`: standard `gpt-5.5`; stopped because the private
   browser profile was not initialized.
2. `hi-2`: login-only prompt `HI`; the helper omitted `--model`, defaulted to
   Pro, and was terminated after detection. No source or audit prompt was sent.
3. `digimou-b3-rc-audit`: standard `gpt-5.5`; login had not yet completed, so
   the session timed out before receiving source.
4. `digimou-b3-standard-audit`: standard model verified; the Windows upload
   path delivered zero files, so Oracle returned `ORACLE INPUT UNAVAILABLE`.
5. `digimou-b3-inline-audit`: standard model verified; a multiline Windows
   prompt was truncated and inline files were omitted, so Oracle again returned
   `ORACLE INPUT UNAVAILABLE`.
6. `digimou-b3-final-audit`: a single-line prompt plus ten individual short
   `-f` arguments delivered all 10 files. Requested and resolved model were
   `Thinking 5.5`, verification was `yes`, and the valid audit returned
   `CANARY PASS / RELEASE BLOCKED`.
7. The first two final re-audit 2 uploads timed out before the send button
   became clickable, first at 45 seconds and then at 120 seconds. Neither
   produced an audit prompt or answer.
8. `digimou-b3-final-reaudit-two-3` delivered seven reduced individual files
   with standard `gpt-5.5`. Oracle CLI evidence reported `Thinking 5.5`
   verified, but the response identified the active model as GPT-5.6 Thinking
   and returned `ORACLE INPUT UNAVAILABLE`. No finding or verdict was adopted.
9. `digimou-b3-final-reaudit-two-4` explicitly selected available non-Pro
   standard `gpt-5.6`. Oracle picker evidence reported requested/resolved
   `GPT-5.6 Sol`, verified `yes`; the response identified the active tier as
   GPT-5.6 Thinking, non-Pro, passed the model and attachment canaries, and
   completed the valid final audit.

The statement in the valid Oracle answer that “this audit did not invoke” Pro
is accurate for that audit conversation only. It must not be read as erasing
the separate login-helper incident above.
