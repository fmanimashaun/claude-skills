---
description: Triage open issue reports for the skills marketplace — classify by component/type/priority, label, dedupe, and post a prioritized work queue
argument-hint: "[issue number | label filter]"
---

# /maintainer-triage — $ARGUMENTS

Turn the issue tracker into the maintenance work queue. Classify and label only —
fixing happens in `/maintainer-work`.

## Precondition — marketplace repo only (hard)

MAINTAINERS-ONLY. Confirm `.claude-plugin/marketplace.json` exists at the repo root before
doing anything. If absent, STOP and tell the user this plugin is for maintaining a
claude-skills marketplace repo, not an app project — change nothing. (Same test as the
SessionStart hook.)

## Phase 0 — Context

Confirm `gh` is authenticated (`gh auth status`). Read `CHANGELOG.md` (what each
component is and its current version) and `.github/labels.yml` if present (the label
taxonomy). If issue intake isn't set up yet, suggest `/maintainer-setup-intake`.

## Phase 1 — Pull the reports

```bash
gh issue list --state open --limit 100 --json number,title,labels,createdAt,body,author
```

If `$ARGUMENTS` is an issue number, triage only that one. If it's a label
(e.g. `comp:rails-8`, `type:incorrect-doctrine`), filter to it. Otherwise triage all
untriaged.

## Phase 2 — Delegate classification

For each issue, hand it to the **issue-triager** agent, which applies exactly one
`comp:*`, one `type:*`, and one `prio:*` label, and flags `needs-info` or `duplicate`.
Trust existing labels; infer and apply where missing. Never adjudicate correctness here
— a report of "wrong doctrine" is routed, not judged (that's the verifier's job in the
work loop).

## Phase 3 — Compute the order, don't reason it out

Priority alone does not give an order: a P1 sitting behind three unstarted issues is not
the next task. The dependency edges declared in issue bodies do, and they are computed,
not re-derived by hand each time (#133):

```bash
python3 scripts/issue_graph.py
```

**It exits non-zero when the graph is wrong** — a cycle, an edge to an issue that does not
exist, a typo'd key, a declaration outside its fence — and prints no queue at all in that
case. Those are filing errors: fix the issue bodies, then re-run. Do not hand-wave past
them and rank by priority instead, which is the habit the tool replaces.

Feed its four outputs into the table below:

- **Ready now** — the candidates. Everything else is noise until these are done.
- **Blocked by what** — never rank a blocked issue above its own blocker.
- **Critical path per epic** — the chain that actually determines when an epic finishes.
- **Priority vs graph** — `P1-but-blocked` and `low-priority-blocking-P1`. Re-label when
  the graph disagrees with the hand-assigned priority; the graph is the better evidence.

While triaging, add a `deps` block to any issue whose ordering you had to work out by
reading prose — that is the reasoning that would otherwise be redone next time. Format:
`docs/issue-dependency-graph.md`.

## Phase 4 — Post the queue

Report a single ranked table to the user: **ready-now first**, then P1,
`type:incorrect-doctrine` ahead of peers, oldest-first within a tier — with the skipped set
(needs-info / duplicate) and why, and blocked issues listed under what blocks them.

Quote the coverage line verbatim (`N/M open issues declare edges`). An ordering computed
from three declared edges out of forty open issues is worth having, but reporting it
without saying so implies knowledge the tracker does not contain.

Do not start fixing. End by naming the head of the queue and inviting
`/maintainer-work <n>`, which re-checks the pick against the graph
(`scripts/issue_graph.py --ready <n>`) before it branches — so a queue posted here is acted
on rather than read.
