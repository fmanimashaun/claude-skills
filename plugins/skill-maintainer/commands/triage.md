---
description: Triage open issue reports for the skills marketplace — classify by component/type/priority, label, dedupe, and post a prioritized work queue
argument-hint: "[issue number | label filter]"
---

# /skill-maintainer:triage — $ARGUMENTS

Turn the issue tracker into the maintenance work queue. Classify and label only —
fixing happens in `/skill-maintainer:work`.

## Phase 0 — Context

Confirm `gh` is authenticated (`gh auth status`). Read `CHANGELOG.md` (what each
component is and its current version) and `.github/labels.yml` if present (the label
taxonomy). If issue intake isn't set up yet, suggest `/skill-maintainer:setup-intake`.

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

## Phase 3 — Post the queue

Report a single ranked table to the user: P1 first, `type:incorrect-doctrine` ahead of
peers, oldest-first within a tier — with the skipped set (needs-info / duplicate) and
why. Do not start fixing. End by naming the head of the queue and inviting
`/skill-maintainer:work <n>`.
