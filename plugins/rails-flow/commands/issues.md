---
description: Triage the repo's open issues and work them through the matching pipeline — verify the issue's claims before editing, check that nothing it waits on is still open, group issues that are one change wearing several numbers, each PR closing what it fixed
argument-hint: "[issue number | label filter]"
---

<!-- topology: sequential
     merge: n/a — verify → branch → build → gates → PR is a pipeline; each step consumes the
            previous step's output, and claim-verifier runs before anything is edited. -->

# /rails-flow:issues — $ARGUMENTS

Turn the repository's issue tracker into the work queue. One coherent branch at a time, full
pipeline every time, nothing half-done.

**An issue body is a hypothesis, not a specification.** However confident it reads, every
externally-verifiable claim in it is checked before a line is written — a stated contract, a
version fact, "per the docs X" — because a plausible wrong claim implemented as written becomes a
confident wrong behaviour with a spec proving it. (The marketplace that ships this flow once took an
issue's four "ARIA APG" keybindings at its word; the spec had dropped them years earlier.)

## Phase 0 — Context

Read `CLAUDE.md` and `GUARDRAILS.md`. Determine the base branch (`dev` if it exists).
Confirm `gh` is authenticated (`gh auth status`).

## Phase 0 — Capture unfiled defects (if any)

This command works the **tracker**, so anything not in it is invisible. If defects surfaced live in
this session (the user reporting problems while reviewing the running app) and aren't filed yet,
**file them first** — one issue each, with repro + expected/actual, batched in a single pass — so
they enter the queue below instead of becoming ad-hoc hot-fixes. Then triage normally.

## Phase 0 — File from `findings.jsonl`, one issue per *defect*

If a review produced `docs/reviews/<date>/findings.jsonl`, file from **that**, not from the markdown
(#138). The distinction is the whole point:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/findings.py" dedupe docs/reviews/<date>/findings.jsonl
```

**File one issue per distinct `signature`, not per record.** A defect seen by three passes, or
appearing on 72 pages, is **one** issue that says "N instances across M locations" — not N issues.
This is measured, not hypothetical: a real crawl produced **773** occurrences of one a11y defect
whose distinct count was about **18**, and a developer told "773 defects" stops reading, while one
told "18, one of which is on every page" fixes the navbar.

Carry `signature` into the issue body. It is how the next review recognises the same defect instead
of filing it again.

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

## Grouping related issues on one branch

Group issues that are **one change wearing several numbers** — it covers more ground per branch,
and for two issues editing the same lines it is the only reviewable shape. Group when all hold:

1. **Same component** — one area label, so a revert stays surgical.
2. **One coherent mechanism** — same files or code path. Fixes that never touch each other gain
   nothing from sharing a branch and widen the blast radius of a revert.
3. **Same discipline** — all bugs (failing spec first) or all features; never a bug carried through
   on a feature's coat-tails.
4. **Still reviewable in one sitting.** No fixed cap.

Traceability is **never pooled**: the branch name carries the primary issue; the PR body carries
one `Closes #n` per issue; if the project keeps a CHANGELOG, one bullet per issue. Pool those and
nobody can say which fix answered which report.

## Phase 2 — Work loop (one coherent branch at a time)

For the issue — or group — at the head of the queue:

0. **Verify the issue's claims before anything is edited.** Extract them and hand the list to
   **claim-verifier**, which checks each by running or grepping, never by reasoning:

   ```bash
   gh issue view <n> --json body --jq .body > /tmp/issue-<n>.md
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/extract_claims.py" /tmp/issue-<n>.md
   ```

   A **refuted** claim is commented on the issue with the evidence and the issue is relabelled
   `needs-info`; it is not implemented as written. An **unverifiable** claim is a question back to
   the reporter, not a licence to guess. Read for omissions too: what the issue does *not* say the
   upstream requires.

0b. **Check that nothing it waits on is still open** — for every issue the branch will carry, in
   one call, so a grouped branch declares its whole set:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check_issue_ready.py" <n> [<m> …]
   ```

   It reads `depends-on: #n` / `blocks: #n` lines (or a ```` ```deps ```` fence) from issue bodies
   — strict syntax, so prose saying "depends on" and a Ruby `depends_on:` in a code sample are not
   edges — and exits non-zero with the reasons on stderr when a named issue waits on open work, is
   already closed, or is not in the tracker. "Take the head of the queue" was a claim nothing
   checked; this is the check. On a refusal: work the blocker first, or say in the PR body that you
   are going out of order and why. A READY that says "declares no edges" means the tracker names no
   blocker, not that none exists.

1. Comment on the issue that work is starting (visibility for humans).
2. Branch by type off the base: bugs → `fix/issue-<n>-<slug>`, features/chores →
   `feature/issue-<n>-<slug>` (a group takes the primary issue's number).
3. Apply the matching discipline:
   - **bug** → the /rails-flow:fix rules: reproduce with a FAILING spec first, then
     make it pass; one proven change per commit.
   - **feature** → the /rails-flow:feature golden path: plan (delegated exploration),
     spec-first units, migration-writer for schema.
   - **chore/docs** → lightweight, but the gates below still apply.
4. Gates (all mandatory): code-reviewer → `VERDICT: CLEAN`; test-runner → full suite,
   0 failures; security-auditor / design-auditor when their domains were touched.
5. PR with the closing keyword so merge closes the issue — **one `Closes #n` per issue** on a
   grouped branch, never one line for the group:
   ```bash
   gh pr create --base <base> --title "<type>: <summary> (#<n>)" \
     --body "Closes #<n>. <Summary / Changes / Proof (specs added)>"
   ```
   Then check what the body **claims**, not only what the diff does — the same
   `extract_claims.py` → claim-verifier pass as step 0, on your own PR body. A sentence about the
   change can be wrong while the diff is internally consistent.
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

Issues triaged (per class), claims refuted (with the evidence, and the issue relabelled), issues
refused as not ready (and what they wait on), issues completed with PR links, issues skipped as
needs-info with the questions asked, and what remains in the queue.
