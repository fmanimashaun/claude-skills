---
description: Triage the repo's open issues and work them one at a time through the matching pipeline — bugs as fixes, features as features — each PR auto-closing its issue
argument-hint: "[issue number | label filter]"
---

# /rails-flow:issues — $ARGUMENTS

Turn the repository's issue tracker into the work queue. One issue at a time, full
pipeline every time, nothing half-done.

## Phase 0 — Context

Read `CLAUDE.md` and `GUARDRAILS.md`. Determine the base branch (`dev` if it exists).
Confirm `gh` is authenticated (`gh auth status`).

## Phase 1 — Triage

```bash
gh issue list --state open --limit 50 --json number,title,labels,createdAt,body
```

If `$ARGUMENTS` names an issue number, triage and work only that one. If it names a
label, filter to it. Otherwise triage everything:

- Classify each issue: **bug** · **feature** · **chore/docs** · **needs-info**.
  Trust existing labels; infer from title/body when unlabeled, and apply the label
  (`gh issue edit <n> --add-label <type>`).
- **needs-info**: the issue lacks enough detail to act (no reproduction, ambiguous
  intent). Comment with the specific questions, label it `needs-info`, and skip —
  never fabricate requirements.
- Order the workable queue: security/P1 first, then bugs, then features/chores,
  oldest first within a tier. Post the queue to the user before starting.

## Phase 2 — Work loop (strictly one issue at a time)

For the issue at the head of the queue:

1. Comment on the issue that work is starting (visibility for humans).
2. Branch by type off the base: bugs → `fix/issue-<n>-<slug>`, features/chores →
   `feature/issue-<n>-<slug>`.
3. Apply the matching discipline:
   - **bug** → the /rails-flow:fix rules: reproduce with a FAILING spec first, then
     make it pass; one proven change per commit.
   - **feature** → the /rails-flow:feature golden path: plan (delegated exploration),
     spec-first units, migration-writer for schema.
   - **chore/docs** → lightweight, but the gates below still apply.
4. Gates (all mandatory): code-reviewer → `VERDICT: CLEAN`; test-runner → full suite,
   0 failures; security-auditor / design-auditor when their domains were touched.
5. PR with the closing keyword so merge closes the issue:
   ```bash
   gh pr create --base <base> --title "<type>: <summary> (#<n>)" \
     --body "Closes #<n>. <Summary / Changes / Proof (specs added)>"
   ```
6. Merge gate: review-pr skill if the code-review-graph CLI + graph are present, else
   the pr-reviewer agent — repeat until CLEAN.
7. **Close-out**: run /rails-flow:pr-comments on the PR. Every review thread must be
   fixed on-branch or folded into a tracked issue before this issue counts as done.
8. Merge to `dev` on CLEAN (default-branch bases stop for the user). Verify the issue
   auto-closed (`gh issue view <n> --json state`); close manually with a comment if
   the keyword didn't trigger. doc-updater if behavior or architecture changed.
9. Only now take the next issue from the queue.

## Unattended operation

`/goal there are zero open workable issues (excluding needs-info) — work them with
/rails-flow:issues, one at a time`. The guardrails, stop gate, and merge review keep
the run inside the rails.

## Report

Issues triaged (per class), issues completed with PR links, issues skipped as
needs-info with the questions asked, and what remains in the queue.
