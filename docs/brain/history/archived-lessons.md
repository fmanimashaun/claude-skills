# Archived brain lessons

Lessons moved out of `docs/brain/MEMORY.md` by the prose-rule audit of 2026-10-18 (#2146): each is one-off history, superseded, or settled in code, so it no longer loads into sessions. The index lines are relocated verbatim, not summarised; each memo moved to `docs/brain/history/memos/` beside this file.

- [feedback-settle-token-disputes-by-usage](memos/feedback/settle-token-disputes-by-usage.md) — When two sources declare a design token differently, count the call sites and measure contrast — the declarations cannot settle it.
  - archived because: one-off history
- [feedback-record-the-choice-to-make-a-situational-rule-checkable](memos/feedback/record-the-choice-to-make-a-situational-rule-checkable.md) — A situational rule can only gate everyone or nobody until the project records its choice; then the check gets a real not-applicable.
  - archived because: settled: project_gates records not-applicable choices
- [feedback-ratchet-a-baseline-dont-set-a-threshold](memos/feedback/ratchet-a-baseline-dont-set-a-threshold.md) — A fixed threshold is inert below the repo and red above it; gate the regression against a recorded baseline instead.
  - archived because: settled: coverage ratchets gate exists (rails-flow coverage ratchets)
- [feedback-downstream-runs-beat-code-review](memos/feedback/downstream-runs-beat-code-review.md) — Defects worth fixing come from RUNNING things, not reading them — four repos read produced zero fixes; the fifth paid off only because its linter was run against our own corpus.
  - archived because: one-off history
- [feedback-a-rule-without-a-trigger-changes-nothing](memos/feedback/a-rule-without-a-trigger-changes-nothing.md) — Prose rules I wrote myself stopped none of my failures; every rule with a hook stopped me instantly.
  - archived because: meta-lesson, realised by every hook
- [feedback-refusing-to-guess-is-a-contribution](memos/feedback/refusing-to-guess-is-a-contribution.md) — Naming the fact you did not measure, instead of filling it with a plausible estimate, is what makes someone else go and measure it.
  - archived because: one-off history
- [feedback-run-the-canvas-to-port-it](memos/feedback/run-the-canvas-to-port-it.md) — Port a Claude Design canvas by executing its own JS (screen/modal builders) in Node and committing the dump as the app's data, instead of transcribing it twice.
  - archived because: Retask canvas porting detail; superseded design-is-source
- [feedback-the-database-launders-an-encoding](memos/feedback/the-database-launders-an-encoding.md) — A value written in the wrong encoding comes back from Postgres as UTF-8, so a round-trip assertion cannot test encoding handling.
  - archived because: Retask-specific test trivia
