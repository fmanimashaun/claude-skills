---
name: feedback-verify-counts-before-stating-them
description: Never report a count, total, or "nothing changed" claim without running the bounded command first — the maintainer has caught two wrong numbers.
type: feedback
---

Every number I state to this maintainer must come from a command that bounded its own input.
Two were wrong in one session, both caught by them, not me:

- **"30 open issues" when there were 42.** `gh issue list` defaults to `--limit 30`, and I had
  dropped the explicit limit. Always `--limit 200` (or `gh api search/issues -q .total_count`).
- **"this release changes the `.skill` assets"** — hashing them showed all four byte-identical.

**Why:** both were `unverified-negative` from the repo's own `code-review` skill, committed while
holding that rule in context. Writing a rule down demonstrably does not prevent violating it. The
first wrong count also turned out to be hiding a real defect — `issue-triager`'s dedupe read the
same truncated list — which became issue #211.

**How to apply:** before stating a count, total, "all X are Y", or "nothing changed", run the
command that proves it and paste the number from that output. Prefer hashing artifacts over
believing a build step. If a listing could paginate, bound it explicitly. See
[[name-where-a-decision-landed]] for the related habit on claims about decisions.

**AN AUDIT COMMENT IS A MEASUREMENT WITH A DATE, AND IT READS AS CURRENT.** 2026-09-17: I quoted an
audit on Retask #303 — *"still only canvas data (`screens.json`, `screens["account/root"]`), and MFA
is unbuilt (#328)"* — and posted it as the present state. It was written against `ee7c2b2` and the
control had since been built: `root_account.rb:24-27` reads `user.totp_enrolled?` and
`user.recovery_codes_remaining` live, `GET /admin/actions/:kind/new` routes, and
`live_actions.rb:346` calls `user.issue_recovery_codes!` and writes an audit entry. A QA session
contradicted it from a live browser.

The aggravating detail: **I had already caught that same audit being stale twice that morning** — I
closed #288 precisely because its "not met" criterion had since been met — and still quoted it
without re-measuring.

**How to apply:** treat a GitHub issue body, an audit comment, a PROGRESS-LOG line and a handoff the
same way as a status snapshot — each is true as of a commit that is named somewhere above it, and
none of them updates. Before repeating any "X is not built / not done / missing" from prose, grep for
X. The claim that something is ABSENT is the one worth re-running, because the repo only ever grows
toward making it false.

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, verify-counts-before-stating-them.md._
