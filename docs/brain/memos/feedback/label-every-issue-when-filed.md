---
name: feedback-label-every-issue-when-filed
description: gh issue create skips the templates that label issues; I filed ~25 claude-skills issues with only comp:*. Pass comp + type + prio every time.
type: feedback
---

On 2026-09-25 the owner said "issues are not being tagged properly" (then: "on retask"). Measured:
12 of Retask's 14 open issues had no labels, and from claude-skills #1249 on, most issues I filed
carried only `comp:*` — no `type:*`, no `prio:*`, two with nothing at all.

**Why:** issue templates (`labels: ["bug"]`) apply labels only through the GitHub web form. Every
agent files with `gh issue create`, which bypasses them, so nothing is labelled unless the command says so.

**How to apply:** in claude-skills, every `gh issue create` carries one `comp:*`, one `type:*` and one
`prio:*` (`.rails-flow/issue-labels.json` declares it; #1311's guard-bash refuses otherwise once
shipped). In a consumer, read its label list and its `.rails-flow/issue-labels.json` first. Related:
[[a-rule-without-a-trigger-changes-nothing]] — the fix was a hook, not a reminder.

**Merged from `label-issues-when-filing` (Retask, same day), verbatim:**

2026-09-25: the owner said "you are not tagging your issues on GitHub" after I filed ~12 Retask issues (#824–#901) with `gh issue create` and no `--label`. Retask's taxonomy: bug / feature / enhancement / qa / documentation / accessibility, severity:s1–s4, rules-in-code, needs-decision, phase-*, status:part-built, and `post-launch` (created that day for designed-now, merge-after-go-live work).

**Why:** unlabelled issues are invisible to filtered views and triage; the owner reads the tracker by label.

**How to apply:** every `gh issue create` carries `--label` with a type label plus severity for defects, `post-launch` for deferred work. Before filing, `gh label list` if unsure. Same in claude-skills (comp:* / type:* labels). Related: [[ask-the-question-dont-report-it-waiting]].

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, label-every-issue-when-filed.md._
