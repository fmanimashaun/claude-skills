---
description: Break a spec, a brief or an issue into dependency-ordered vertical slices — draft each with criteria and blocking edges, check the plan, show it for approval, then file one labelled issue per slice so /rails-flow:issues can work the frontier.
argument-hint: "[docs/product/specs/<slug>.md | docs/brain/BRIEF.md | an issue number]"
---

# /rails-flow:slice — $ARGUMENTS

`/rails-flow:brief` and `/rails-flow:spec` end at "the first slice", and nothing produced the
slices. `/rails-flow:feature` builds one, and `/rails-flow:issues` works issues that already exist.
This command fills the gap between them. It turns the spec into issues that can be worked in order,
each small enough to finish in one fresh session.

Adapted from mattpocock/skills `to-tickets`, on the owner's decision recorded on #1369.

## What a slice is

A slice is a **vertical** cut: complete through every layer it touches (migration, model, controller,
view, spec) and demoable on its own. "The models", then "the controllers" is a horizontal cut. None
of its pieces can be shown to anyone, and the integration defect surfaces last.

- **One fresh context each.** If a slice needs the conversation that planned it, it is too big.
  Split it until each one could go to a session that has read only its issue.
- **The thinnest end-to-end path first.** S1 is the tracer bullet: the smallest path through every
  layer, however bare. Later slices widen it.
- **The exception is a wide refactor.** A rename across the app cannot be vertical. Sequence it as
  **expand** (add the new alongside the old), then **migrate in batches** (one slice per batch), then
  **contract** (remove the old). Each step is still a slice with its own criteria.

`check_slices.py` checks the plan's structure. Whether each slice is truly vertical and small enough
is a judgement: yours when drafting, and the owner's at the approval step.

## Run

**1. Read the source.** The spec (`docs/product/specs/<slug>.md` from `/rails-flow:spec`), else
`docs/brain/BRIEF.md`. If `$ARGUMENTS` is an issue number, read it with `gh issue view <n> --comments`,
since the comments hold the corrections. That issue becomes the **parent** of every slice. Also read
the code the work touches, so the edges reflect what really depends on what.

**2. Write the plan** to `docs/product/slices/<slug>.md`, in this shape:

```markdown
# Slices: magic-link sign-in
Source: docs/product/specs/sign-in.md

## S1 — Sign in with an email link
Mock-up: no visible change
- **AC-1** Given a registered address, when the user submits the sign-in form, then an email with a one-time link is sent
- **AC-2** Given an unknown address, when the user submits the sign-in form, then the same confirmation shows and no email is sent [error]

## S2 — Remember the device for 30 days
depends-on: S1
Mock-up: docs/design/remember-device.png
- **AC-3** Given a signed-in user who ticked "remember me", when they return within 30 days, then they are signed in without a link
- **AC-4** Given a remembered device older than 30 days, when the user returns, then the sign-in form is shown [error]
```

- **`depends-on:`** names other slices (`S1`) or existing issues (`#93`), comma-separated, on one
  line. Omit the line for a slice that waits on nothing.
- **`Mock-up:`** is on every slice (#1376). A slice that changes a screen links its mock-up; every
  other slice says `no visible change`.
- **Criteria** are stubs in `check_criteria.py`'s shape: Given / when / then, with at least one
  `[error]` path per slice. They become the slice's `docs/product/acceptance/<slug>.md` when
  `/rails-flow:feature` picks it up.
- **No `###` headings inside a slice.** A heading starts a new criteria unit and detaches the
  criteria below it.

**3. Check it**, and fix every finding before showing anyone:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check_slices.py" docs/product/slices/sign-in.md
```

It refuses a cycle (no slice could go first), an edge to a slice that does not exist (a blocker
nobody closes), a slice with no criteria, a malformed `depends-on:` line, a missing Mock-up, and any
criterion `check_criteria.py` would refuse. Exit 0 prints the filing order.

**4. Show the breakdown and stop for approval.** Show one table: order, slice, what it depends on,
Mock-up, and the criteria count. Add one line per slice saying why it is vertical. Filing creates
public issues, so wait for an explicit yes. The owner may merge, split or reorder slices; edit the
plan and re-run step 3.

**5. File in order**, blockers first, so each blocker already has a number when a dependent needs it.
For each id printed by `--order`, render the body with the numbers filed so far, then create the
issue. Label it from `.rails-flow/issue-labels.json`, one label per declared group:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check_slices.py" docs/product/slices/sign-in.md --order
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check_slices.py" docs/product/slices/sign-in.md \
  --issue-body S2 --filed S1=101 > docs/product/slices/.issue-body.md
gh issue create --title "S2 — Remember the device for 30 days" \
  --body-file docs/product/slices/.issue-body.md \
  --label type:feature --label prio:P2 --blocked-by 101 --parent 100
```

The body's `depends-on: #101` line is the record `check_issue_ready.py` reads. `--blocked-by` and
`--parent` also set GitHub's native relationship. Drop `--parent` when there is no parent issue.
`check_slices.py` refuses to render a slice whose blocker is not filed yet.

If `gh help issue create` does not list `--blocked-by`, your `gh` predates the flags. Create the
issue without them and link it through the REST API instead. Both endpoints take the issue's `id`,
not its number:

```bash
blocker_id="$(gh api "repos/{owner}/{repo}/issues/101" --jq .id)"
gh api "repos/{owner}/{repo}/issues/102/dependencies/blocked_by" -F issue_id="$blocker_id"
child_id="$(gh api "repos/{owner}/{repo}/issues/102" --jq .id)"
gh api "repos/{owner}/{repo}/issues/100/sub_issues" -F sub_issue_id="$child_id"
```

**6. Commit the plan** (`docs/product/slices/<slug>.md`) by name, with the filed number next to each
slice heading. Never `git add -A`. Delete `.issue-body.md`.

## What happens next

`/rails-flow:issues` works the **frontier**: any slice whose blockers are all closed.
`check_issue_ready.py --queue` computes it from the `depends-on:` lines, so nothing new reads the
graph. Each slice then goes through `/rails-flow:feature` on its own branch. The mock-up gate in
Phase 1 applies to every slice that links a mock-up.

## Report

The source read, the slice count, the filing order, each slice's issue number and its edges, which
native links were set (flags or REST), and the `check_slices.py` result.
