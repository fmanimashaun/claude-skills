---
description: Write the work order for a unit of work — one self-contained file an executor can run from with no conversation history, carrying the goal, the criteria it is graded by, the scope, the stop conditions, and how to verify.
argument-hint: "[blank to infer from the branch | <slug>]"
---

# /rails-flow:handoff — $ARGUMENTS

Everything an executor needs today is spread across `CLAUDE.md`, `GUARDRAILS.md`, the phase plan,
`docs/brain/`, `docs/acceptance/<slug>.md` — and the conversation. That last one is the problem.
Context that lives in chat evaporates on a fresh session, on a resume after a crash, on a second
machine, and when the work is delegated to a subagent that never saw the discussion. What survives
is what was written down.

So: **one file per unit of work**, holding everything needed to execute it and nothing else.

## Where it lives, and why not `HANDOFF.md`

`docs/handoff/<slug>.md`, **committed**. The slug is the branch name after `feature/` or `fix/`
with any remaining `/` flattened to `-` — byte-identical to the rule
`/rails-flow:feature` uses for `docs/acceptance/<slug>.md`, so a unit of work is one slug with two
files: what "done" means, and how to get there.

[#127](https://github.com/fmanimashaun/claude-skills/issues/127) proposed a root `HANDOFF.md` and
left committed-vs-gitignored open. Both halves are decided here, against the issue:

- **Not a root file.** Work orders are per feature/fix and concurrent branches each have one. A
  single root file is overwritten by whichever branch touched it last and conflicts on every merge —
  the artefact whose whole purpose is surviving a context switch would be the one thing that cannot.
- **Committed, not gitignored.** The failure it exists to fix *is* the loss of context between
  sessions and machines. An artefact that a fresh clone does not have solves nothing, and it is
  reviewable in the PR that ships the work, alongside the criteria it cites.

## The shape (the headings are a contract)

`check_handoff.py` requires all nine `##` sections. Each is there because leaving it out is a
specific, observed failure — not for symmetry.

```markdown
# Work order — <slug>

## Base commit
`a1b2c3d` on `feature/invoice-totals` — the tree this order was written against.

## Goal
One paragraph: what is being built and the outcome that makes it worth doing. No implementation.

## Acceptance criteria
Graded by `docs/acceptance/<slug>.md` — AC-1, AC-2, AC-3. Cite the ids; do not restate them.

## Scope
### In
- `app/models/invoice.rb`
- `spec/models/invoice_spec.rb`
### Out
- `app/models/account.rb` — tenancy lives there; a change needs its own criteria
- anything under `db/migrate/` — no schema change in this unit

## Guardrails
`GUARDRAILS.md` in full. The ones this unit will actually brush against: every query
clinic-scoped, no `Model.find(params[:id])`, 422 on invalid and 303 on redirect after mutation.

## Stop conditions
- **Attempt cap: 3** per criterion. On the third failure, stop and write the diagnosis.
- **No progress: 2** consecutive runs with an identical failure signature is a stop, not a retry.
- **Blast radius: 10 files**, and never a file outside In above.
- **Forbidden — these end the run:** weakening or deleting a failing test to make it pass;
  reverting a task that was already passing to unblock this one; editing a file outside In;
  disabling a guardrail or a hook.
- **Budget:** stop at 2 hours or 300k tokens, whichever comes first, and report the remainder.
- On a stop: write the diagnosis, then continue with unrelated criteria. Never block the run on one
  stuck item, and never report a partial run as complete.

## Verify
1. `bundle exec rspec spec/models/invoice_spec.rb` — 0 failures.
2. `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check_criteria.py" docs/acceptance/<slug>.md --specs spec`
3. `bundle exec rspec` — full suite, 0 failures.

## Executor
Tier: judgement (`model: inherit`) — see the plugin's `reference/model-tiers.md`.

## On completion
Update `docs/brain/STATUS.md`; a decision taken on the way goes to `docs/brain/DECISIONS.md` as a
`D-nnn` with its trade-off; note the PR number here.
```

**Self-contained by construction** is the whole claim, so it is checked rather than asserted: the
checker rejects a work order that points at the conversation ("as we discussed", "the plan I
described above"), and rejects leftover `<placeholders>`, `TBD` and `TODO`. An executor cannot
resolve either, and will guess — which is the exact failure the file exists to prevent.

**The base commit is the section an executor reads first.** The other eight describe what to
do; this one says from *where*. A work order is committed, so it is durable by design — and durable
is when it bites: `/rails-flow:escalate` parks a question on an issue and resumes *"in a different
session after a restart"*, so an order can be picked up against a tree that has moved. Its `scope`
names files and its `verify` names commands, and neither is true of a branch three commits later.

The checker **resolves** it: a plausible hex string that is not a commit in this repository is
refused, because an executor will start from it. Drift is **reported, not refused** — *"written
against `a1b2c3d`, HEAD is 4 commits ahead"* — since work legitimately continues on a moved branch
and a gate refusing every stale order would be switched off.

**Link, never copy.** The criteria section cites `AC-n` ids; it must not carry
`Given … when … then …` lines of its own, and the checker enforces that. Two prose copies of one
criterion will disagree, and nothing says which grades the work. Same rule as `docs/GUIDE.md`
(`/rails-flow:explain`) and for the same reason.

## Stop conditions are doctrine, not decoration

The section above is the rails-flow half of
[#128](https://github.com/fmanimashaun/claude-skills/issues/128), and it belongs in the work order
because the work order is what an unattended executor reads. An agent that cannot make progress but
keeps trying does not idle — it digs: reverts its own fixes, loosens tests until they pass, widens
scope to route around a blocker. Every one of those looks like activity in a log, and two of them
look like success.

Defaults, all overridable per work order — but a work order must state a **number**, because "stop
when stuck" cannot be evaluated by the thing that is stuck:

| Condition | Default | Why that shape |
|---|---|---|
| Attempt cap | 3 per criterion | Bounded retries; the fourth attempt on an unchanged failure has never been the one that works. |
| No-progress | 2 identical failure signatures | Repetition *without a changing error* is the signal. A changing error is progress. |
| Blast radius | 10 files, never outside `### In` | Scope creep is how "fix the invoice total" becomes a tenancy refactor nobody reviewed. |
| Budget | stated per work order, remainder reported | An unattended run with no budget is discovered by its bill. |

Two rules carry more weight than the numbers:

- **Escalate and continue.** A stop writes the diagnosis — what was attempted, the exact failure
  signature, the suspected cause — and then moves to unrelated criteria. One stuck item must not
  end the run, and a stop is not a failure of the run.
- **The final report distinguishes complete / partial / stopped.** *Partial completion reported as
  success is the worst available outcome*: it spends the reviewer's trust and the reviewer's time,
  and it is how a green log ships a broken feature. List what was not attempted, by name.

**The forbidden escapes are not "discouraged".** They end the run:

| Escape | Why it ends the run rather than costing a warning |
|---|---|
| Weakening or deleting a failing test | Destroys the only external proof the work has. A cheap-tier executor is *only* safe while that proof is outside it. |
| Reverting a passing task to unblock this one | Trades work that was proven for work that is not. |
| Editing a file outside `### In` | The scope declaration is what makes the diff reviewable and the change revertible. |
| Disabling a guardrail or hook | The guardrails are the reason unattended work is allowed at all. |

`maxTurns` in an agent's frontmatter is *"Maximum number of agentic turns before the subagent
stops"* ([Claude Code docs](https://code.claude.com/docs/en/sub-agents), fetched 2026-07-31) — a
mechanical backstop for delegated work, and a per-agent one. It bounds turns, not attempts, so it
complements the attempt cap rather than replacing it: an agent can burn three attempts inside one
turn, or spend twenty turns making real progress on one.

## Run

**1. Resolve the slug.** `$ARGUMENTS` if given, else the current branch after `feature/`|`fix/`
with `/` flattened to `-`. Not on such a branch and no argument: say so and stop — a work order
with no slug has nothing to pair with.

**2. Read before writing.** `docs/acceptance/<slug>.md` (the criteria — they are the graded
contract, and the work order cites their ids), `CLAUDE.md`, `GUARDRAILS.md`, and the plan for this
unit. Do not invent criteria here: if the acceptance file is missing, write it first
(`/rails-flow:feature` Phase 1) — a work order that grades itself is not a work order.

**3. Write `docs/handoff/<slug>.md`.** Fill every section. Resolve every placeholder. Nothing may
depend on this conversation.

**4. Verify — this gate does not get skipped.**

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check_handoff.py" "docs/handoff/<slug>.md" \
  --criteria "docs/acceptance/<slug>.md"
```

Exit `0` clean · `1` findings · `2` unusable (no file, or not a work order at all). On findings, fix
the work order. Never soften the check: an under-specified work order does not fail loudly, it
produces confident work on the wrong thing.

What the checker cannot do: judge whether the goal is the *right* goal, whether the scope is *big
enough*, or whether the stop conditions are *wise*. It checks that each is present, numeric where a
number is the only falsifiable form, and free of dangling references. The judgement stays yours.

**5. Commit** `docs/handoff/<slug>.md` by name, in the same commit as the criteria where possible.
Never `git add -A`.

## Reconciling the agents with the tier doctrine

The same script checks the other half of #127 — that no agent's `model:` silently contradicts
`reference/model-tiers.md`:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check_handoff.py" \
  --agents "${CLAUDE_PLUGIN_ROOT}/agents" \
  --tiers "${CLAUDE_PLUGIN_ROOT}/reference/model-tiers.md"
```

Run it after touching any agent's frontmatter or the tier table. A project that has adopted the
doctrine for its **own** `.claude/agents/` points the same two flags at its own directory and its
own copy of the table.

## Report

The slug, the path written, which criteria ids it cites, the in/out scope counts, the stop-condition
numbers chosen where they differ from the defaults, and the `check_handoff.py` result. If the
acceptance file was missing and you wrote it first, say so — that ordering is the point, not an
aside.
