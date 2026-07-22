---
description: Proactively review a skill or plugin against source-of-truth and the open-issue signal, logging gaps as issues rather than fixing in place
argument-hint: "[component, e.g. rails-8 | hotwire | rails-flow | qa-flow | pipeline]"
---

# /skill-maintainer:audit — $ARGUMENTS

Not issue-driven: go looking for problems before users hit them. Audits produce
ISSUES (the queue), not direct edits — so every change still flows through the verified
`/skill-maintainer:work` loop.

## Scope

`$ARGUMENTS` names the component to audit; default to the one with the most open issues
or longest since last audited (check `docs/audits/`). Pull the open-issue signal for it
(`gh issue list --label comp:<x>`) — clustered reports point at systemic gaps.

## Method

- **Skills (rails-8 / hotwire)** → delegate to **doctrine-verifier** across the
  reference's key claims: spot-check against official docs for the targeted version,
  flag anything outdated, unversioned, or contradicted. Record findings in
  `docs/audits/<date>-<component>-audit.md` (the existing audit format): coverage
  matrix, verdict per claim, version-boundary gaps.
- **Plugins (rails-flow / qa-flow / pipeline)** → review agents/commands for
  consistency and hooks for portability + correctness (`bash -n`, the interpreter and
  `mktemp` assumptions, fail-closed vs fail-open per hook's role, idempotency of
  scaffolding). Note drift from the plugin's stated charter.

## Output

For each finding, open a labeled issue (`gh issue create` with the right `comp:*` /
`type:*` / `prio:*`) so it enters triage like any downstream report — do NOT fix in
place. Post a summary: what was audited, sources checked, issues filed (numbers), and
the audit-doc path. Confirmed-correct areas are recorded too, so the audit is evidence
the doctrine held, not just a bug list.
