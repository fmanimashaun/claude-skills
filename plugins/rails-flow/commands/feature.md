---
description: Orchestrated feature development — plan, spec-first implementation, quality gates, PR, tool-gated merge
argument-hint: <feature description>
---

# /rails-flow:feature — $ARGUMENTS

Build the requested feature end-to-end using the orchestrated flow below. You are the
orchestrator: delegate to the rails-flow subagents, keep your own context lean, and never
skip a gate. Hooks enforce the guardrails mechanically — do not fight them.

## Phase 0 — Context

1. Read `CLAUDE.md` and `GUARDRAILS.md`. If either is missing, tell the user and offer
   `/rails-flow:setup-flow` before proceeding.
2. Determine the base branch: `dev` if it exists, else the repository default. All work
   branches from and PRs into the base. Feature PRs never target `main` when `dev` exists.
3. Confirm a clean starting state (`git status`); stash/park anything unrelated.

## Phase 1 — Plan (delegated exploration)

Delegate codebase exploration to a subagent so raw file contents stay out of your context:
which models/controllers/views/jobs the feature touches, existing patterns to reuse, and
schema impact. Then produce a short plan:

- Units of work, ordered — each unit is one spec + its implementation
- Migrations needed (these go to `migration-writer`)
- Risks / invariants in play (tenancy scoping, authorization, module gates)

### Acceptance criteria — write them BEFORE any code

Every unit gets criteria, recorded in `docs/acceptance/<branch-slug>.md` — the slug is the
branch name after `feature/`, with any remaining `/` flattened to `-` (so `feature/team/foo`
→ `docs/acceptance/team-foo.md`). One `##` section per unit:

```md
## Invoice totals
- **AC-1** Given an invoice with two line items, when the user opens the invoice page, then
  the footer shows the summed amount formatted as currency
- **AC-2** Given an invoice with no line items, when POST /invoices runs, then the response is
  422 and the modal re-renders with "must have at least one line item" [error]
```

The shape is fixed: **Given** `<state>`, **when** `<action>`, **then** `<observable>`. Each
criterion carries a stable id (`AC-1`, `AC-2`, …) — the id is what the proving spec cites, and
what makes "the spec proves the criteria" checkable rather than a claim.

**Every criterion must name an action and an observable.** If it names neither, it will be
rubber-stamped:

| Bad | Why | Good |
|---|---|---|
| "handles invalid input" | no action, no observable | "Given a blank email, when the user submits the form, then the field shows 'can't be blank' and no user is created" |
| "login works" | asserts nothing | "Given a wrong password, when the user submits the sign-in form, then the page shows 'wrong email or password' and does NOT redirect to the dashboard" |
| "errors handled gracefully" | unfalsifiable | "Given an invoice with no line items, when POST /invoices runs, then the response is 422 and the modal re-renders with 'must have at least one line item'" |

**At least one error-path criterion per unit** — tag it `[error]` or state a failure case.
Happy-path-only criteria are rejected: most real defects live on the error path, and every
security finding this flow has produced downstream was an error or edge path.

Validate before implementing, and again once specs exist:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check_criteria.py" "docs/acceptance/<slug>.md"
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check_criteria.py" "docs/acceptance/<slug>.md" --specs spec
```

Exit `0` clean · `1` findings · `2` unusable (no file, or no criteria in it). On findings,
rewrite the criterion — never soften the check. The Stop gate runs this too, so a branch whose
criteria do not hold cannot finish.

*Why this precedes code:* a criterion written afterwards asserts what the code happens to do
rather than what was required, which is unfalsifiable — the same defect class as a gate that
cannot fail, moved from the gate to the goal. If you cannot evaluate it, you cannot iterate on
it unattended. The checker proves each criterion is *traceable* to a spec; it cannot prove the
spec truly asserts the observable, so that judgement stays yours.

Post the plan **and the criteria** to the user, then proceed — the gates below are the control
points, not a plan-approval pause. If the plan reveals genuine ambiguity about intent, ask
first: criteria are the place ambiguity surfaces cheapest.

For a feature whose shape the owner has to live with — a new billing model, a state machine, a
tenancy change — offer `/rails-flow:explain plan` before Phase 2. It restates the plan in plain
language for a non-specialist, so a wrong *premise* is caught for the price of a paragraph
instead of a build cycle. It writes nothing; it is a go/no-go, not a document.

## Phase 2 — Branch

```bash
git checkout <base> && git pull
git checkout -b feature/<kebab-slug>
```

## Phase 3 — Spec-first implementation loop (per unit)

1. **Write the failing spec first, and cite the criterion it proves.** Put the id in the
   example's description — `it "AC-2 rejects an invoice with no line items" do` — so the
   mapping from criterion to proof is mechanical, not remembered. The spec must prove the NEW
   behavior (wrong-role rejection for new filters, concern behavior, state transitions), not
   merely execute the code. Run it; confirm it fails for the right reason.
   A criterion no spec cites is an unproven criterion, and the Stop gate says so.
2. Implement — delegate substantial units to `rails-developer`; schema changes to
   `migration-writer` (round-trip proven). Small edits you may do directly.
3. Run the unit's specs to green, then `git add <specific files>` and commit with an
   imperative message. One unit per commit.

## Phase 4 — Quality gates (all mandatory)

Run in order; loop fixes back through Phase 3 until every gate passes:

1. `code-reviewer` on the branch diff → must end `VERDICT: CLEAN`
2. `test-runner` → FULL suite, 0 failures
3. `security-auditor` → only if auth, authorization, APIs, or data handling changed
4. `design-auditor` → only if views/partials/Stimulus changed

## Phase 5 — PR

```bash
git push -u origin feature/<slug>
gh pr create --base <base> --title "feat: <summary>" --body "<the PR Documentation Contract — see below>"
```

## Phase 6 — Merge gate (non-skippable)

- If the code-review-graph CLI is present with a built graph
  (`command -v code-review-graph && [ -d .code-review-graph ]`): run its `review-pr`
  skill with the PR number (installed per-project by `code-review-graph install`;
  since v2.x it is a plain skill — no plugin namespace). Supplement with
  `code-review-graph impact` on the changed files for blast-radius evidence.
- Otherwise: delegate to `pr-reviewer` with the PR number.
- A self-written review comment is the OUTPUT of a review, not the review. BLOCKED →
  fix on the same branch, push, re-run the gate. Repeat until CLEAN.
- On CLEAN: if the base is `dev`, merge (`gh pr merge --squash`), then post a summary
  comment citing the gate's findings. If the base is the default branch (no `dev`), stop
  after CLEAN and hand the merge decision to the user — and offer them a PR babysitter:
  `/loop "Check PR #<n>: if CI failed, read the log, fix on the branch, push; address
  new review comments; if merged, say MERGED" --interval 10m --expires 8h`.

- **Close-out rule**: a PR is finished only when every review thread is resolved —
  each actionable comment fixed on this branch (push, reply with the commit) or folded
  into a tracked repo issue and linked back. Sweep with `/rails-flow:pr-comments <n>`
  after the gate and after any human review lands. Do not start the next unit, phase,
  or task while the current PR has unresolved feedback.

## Phase 7 — Close the loop

Run `doc-updater` for the session's changes. Report to the user: plan → commits → gate
results → PR link → docs touched. If anything was deferred, say so explicitly.

If this feature changed how the product *behaves* for its owner — not merely how it is built —
run `/rails-flow:explain <area>` so `docs/GUIDE.md` moves with the code. `doc-updater` reports
when an area has gone stale but deliberately does not rewrite the explanation itself.
