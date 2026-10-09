# Context budget — what gets injected, and how often you pay for it

The decision record behind `scripts/check_hook_output_budget.py` and the shape of
`hooks/scripts/session-start.sh`. Filed as [#1085](https://github.com/fmanimashaun/claude-skills/issues/1085).

Every other cost in this toolchain is measured and gated. This one was not measured at all:

```
grep -rn --include='*.md' -iE '/compact|compact the context|context window' plugins/ skills/
  -> one hit, about RubyLLM's model registry
```

## The fact that changes the arithmetic

**A `SessionStart` hook does not run once per session. It runs again after every compaction.**

That inverts the intuition. A hook feels like a fixed startup cost, so 4 KB reads as cheap. But a
compaction exists to reclaim a context window that ran out — and the hook fires into the fresh
window, spending part of what was just reclaimed, before any work happens. The longer the session,
the more times you pay, and the payments land at the worst possible moments.

Measured on this repository the first time anyone looked:

| hook | bytes per fire |
|---|---|
| `plugins/rails-flow/hooks/scripts/session-start.sh` | **4451** |
| `.claude/hooks/scripts/maintainer-status.sh` | 100 |
| `plugins/qa-flow/hooks/scripts/qa-status.sh` | 0 |
| `plugins/pipeline/hooks/scripts/pipeline-status.sh` | 0 |

One hook was 98% of the cost. Of its 4451 bytes, **3805 were `docs/brain/MEMORY.md` printed
verbatim**, and **42% of that block was `[slug](path)` markdown** — link scaffolding no model acts
on, repeated once per lesson, re-injected at every compaction.

## The rule

**Apply the harness-doctrine test to every line a hook prints: if a model ignores this line, what
happens?**

- A lesson — *"the Bash tool runs zsh; an unquoted `$var` is one word"* — changes what the model
  does. It earns its bytes.
- The path that lesson lives at does not. Nobody opens it from the banner; it is one `grep` away
  when it is wanted.
- A count plus a pointer beats a list. *"17 lessons; `/rails-flow:brain` for the rest"* preserves
  discoverability at a fixed cost, where the list grows without bound.

Stripping the scaffolding took `session-start.sh` from 4451 to about 2000 bytes with **no
actionable content removed** — the lesson text is printed in full. That is the shape to aim for:
cut the packaging, never the substance.

## Gate it as a ratchet, never a threshold

`scripts/check_hook_output_budget.py` records what each hook costs today and fails on growth.

A fixed byte limit is the wrong instrument here, for the reason this repository has hit before: set
above today's size it is inert and never fires; set below it, it is red on day one and gets
switched off. A ratchet starts honest, and the only way past it is `--update` in a commit somebody
reviews.

**It measures against a fixture project, never this repository.** Hooks print the branch, the last
commit subject, an issue count — all of which move. A baseline taken from the live tree would drift
on unrelated commits, and a gate that goes red on its own is one people learn to ignore. The
fixture pins every input, and the selftest asserts both that two runs agree *and* that a bigger
fixture measures bigger — determinism alone cannot show the fixture is what is being read, because
the live tree is stable within a run too.

## The load we do not emit is still the user's

The ratchet above governs the bytes **our** hooks print. A user's session pays for everything that
loads, and on the repository where this was measured (2026-09-22) ours was the smallest part of it:

| loaded into every session | ~tokens | whose |
|---|---|---|
| the `remember` plugin's SessionStart output | ~5,700 | a third-party plugin |
| `CLAUDE.md` | ~4,500 | the project |
| Claude Code auto-memory (`MEMORY.md` index) | ~3,800 | the harness |
| `AGENTS.md` | ~1,900 | the project |
| `rails-flow` `session-start.sh` | ~520 | us |

Three of those rows are **memory systems** — auto-memory, `remember`, and our `docs/brain` — and none
knows about the others. We cannot ratchet another plugin's output (it is not ours to run, and a number
we cannot reproduce is not one a ratchet can hold). What we can do is make the choice explicit:
`/rails-flow:setup-flow` §4a records which memory systems a project loads, and the `memory-systems`
check in `project_gates` holds the committed settings to it. **It adds nothing to any session** — it
runs on demand and in CI — so the check that guards the budget does not spend it.

## The live window: a mod that shows the fill and nudges once (#1547)

Everything above bounds what we *inject*. Nothing watched how full the window actually was, so a long
session kept paying for context it no longer needed. `hooks/context-nudge.mjs` does two things, and only
these:

1. **Shows the fill.** After each turn, `session.measure` hands the mod `context.percent`; it pins
   `context NN%` under the prompt with `$.ui.status`, one line per plugin, which Claude Code renders as
   `⚠ rails-flow: context NN%` (the docs' own style for a routine value, not a severity). Neither source says
   how that line relates to a configured `statusLine`, so nothing here claims it leaves one alone. **In the VS
   Code extension's chat panel a mod's hooks run but what it draws does not appear**, so the line is probably
   not visible there (an inference: the docs table does not name `$.ui.status`); the nudge does not depend on
   drawing.
2. **Nudges once per climb.** When the person submits a prompt and the fill is at or past the threshold, it
   adds ONE context line only Claude reads (about 230 characters, asserted at most 400): finish the step,
   offer `/rails-flow:handoff`, then tell the user to `/clear` (owner decision, 2026-10-07: `/clear`, not `/compact`, because once the handoff is written a compaction only carries a summary of what the handoff already holds). It adds nothing again until the fill
   has fallen below the threshold or lost its reading (a `/clear` or a compaction). It is added only to a
   prompt from a person at an interactive surface: `composer`, `bridge` or no origin. The other fourteen of
   the engine's sixteen origin kinds are refused on purpose, `sdk` included, because `claude -p` has nobody to
   run `/clear`.

**What is verified, and where.** Verdicts are on #1547 (four `doctrine-verifier` passes) and the cited
excerpts are committed at `docs/evidence/audits/2026-10-02-mods-api-2.1.287.md`, with the declaration's
checksum, so no citation depends on a temporary path. That file was taken from 2.1.287 and has not been
re-checked against 2.1.288, which the CLI has since moved to; `claude plugin validate` and `claude plugin test`
pass on 2.1.288.
- `percent` is `tokens` over `window` as a whole percentage, "the status line's `used_percentage`", where
  `tokens` is uncached, cache-written and cache-read input together; both are absent until the first response
  of a live window and after a compaction. **The source is the engine's own type declaration for 2.1.287**
  (`claude-code.d.ts`, written by Claude Code and shipped with its plugin-authoring skill). The website docs
  list the field and do not define it, so a later release can change the formula without the docs saying so.
- `session.measure` fires after each turn and when the fill moved. A prompt hook can add context "only Claude
  reads". Mods need Claude Code 2.1.287 or later. A plugin manifest drops `statusLine`, which is why this is a
  mod and not a status line script.
- Two hooks on the same event with no matcher fail to load, so `hooks/register.js` (the one module
  `hooks.json` names) must register each event and matcher once. This mod uses `session.measure` and
  `prompt.submit`; the lane band uses `session.start`, `turn.complete` and `ui.render` on `AbovePrompt`.
  A module may not pass `$` to a function imported from another of its files, and this mod imports nothing.
- "No usage field reaches a hook" stayed INCONCLUSIVE, so the claim here is only that the docs document none.

**What CI checks, and what it cannot.**
- *CI runs* `plugins/rails-flow/scripts/check_mods.py` (doctor gate "mod unit tests"): `tests/*.unit.mjs` drive
  the mod's hooks under plain Node with a hand-built host, and `register.unit.mjs` checks that `register.js`
  registers each event and matcher once. The mutation guards `context_nudge`, `mods_register` and
  `hooks_json_modules` run in the mutation coverage sweep, so these checks are known to be able to fail.
- *CI cannot run* `claude plugin validate` or `claude plugin test`, which need the `claude` CLI; the gate
  runners do not have it (`check_hook_commands.py` says the same). They check that the engine accepts the
  module and calls these hooks with these event shapes, and they run on a maintainer's machine: 8 tests in
  `tests/context-nudge.test.ts`. Nothing in CI would notice the engine changing an event's shape.
- The unit test's fake host is written from the types, so it can agree with the mod and disagree with the engine.
  That gap is the reason the local run stays in the review checklist.

**What is not known.**
- **The threshold is a starting value.** Default 70, whole percent, overridden by
  `RAILS_FLOW_CONTEXT_NUDGE_PCT` (1 to 99). Nothing has measured where a handoff stops being cheap; do not
  read 70 as a finding.
- The mod's own variables reset on a hot reload, so a reload can repeat the nudge once. Development only.
- One clause of the prompt hook, the explicit `percent === null`, is redundant because `null < 70` is already
  true in JavaScript. Removing it changes nothing, so no test can catch it, and it is left out of the guard.

## Three limits, one automation: context, the 5-hour session, the week (#1676, #1677)

The context nudge watches one window. The account's 5-hour session limit and weekly limit were invisible to the
agent: on 2026-10-07 the owner had to say "we are still at 96% of weekly limit", after four Workflow broadcasts
had spent about 680k tokens each. Each started 11 agents, each paying about 62k tokens of startup context
(the workflow's own report divided by 11), only to call `SendMessage`. The point of this section is that the
agent knows where all three limits stand and acts in time: it writes things down while there is still
budget, and the work carries on after a reset.

| Limit | At the warn level | At the hard level |
|---|---|---|
| Context window (`context-nudge.mjs`) | at 70%: one line asks for `/rails-flow:handoff`, then `/clear` | — |
| 5-hour session window | at 80%: update the handoff, commit and push, no fan-out | at 90%: finish the step, save everything, stop; **resume by itself just after the reset** |
| 7-day window | at 80%: the same | at 90%: the same, and new `Workflow` and `Agent` calls are refused |
| Any usage | a `Workflow` whose script has agents only relay `SendMessage` is refused | — |

- **The status line** reads `context 30% · week 42% · 5h 12%`. Each usage line names the window's reset time,
  in UTC, and rides on a prompt once per level reached. It resets when usage falls back below warn.
- **The resume.** At the 5-hour hard level, the mod sets one timer (`$.clock.after`) for two minutes after the
  window's `resetsAt`. When it fires, it submits one prompt (`$.prompt.submit`), which runs once the session is
  idle, telling Claude to read the handoff and continue. Timers live in the session: a hot reload or the end of
  the session cancels them, so a closed session does not resume. `RAILS_FLOW_AUTO_RESUME=0` turns it off. The
  weekly window gets no resume, because it does not reset within a session.
- **Thresholds and override:** `RAILS_FLOW_BUDGET_WARN_PCT` (default 80) and `RAILS_FLOW_BUDGET_BLOCK_PCT`
  (default 90), whole percents from 1 to 100. `RAILS_FLOW_BUDGET_ALLOW=1` lifts the weekly fan-out refusal, but
  not the relay refusal.
- **The relay refusal** needs the script: a `Workflow` started by `name` or `scriptPath` carries none, so it
  is not checked. A script whose agents do real work and also report by message opts out with the line
  `// budget-guard: not a relay`.

**Where the figures come from, and when there are none.** They are `$.session.usage()` and
`session.measure`'s `rateLimits`, each window a `{ kind, percentUsed, resetsAt }` (`resetsAt` is ISO 8601 here;
the status line's own JSON uses epoch seconds). They appear only on a claude.ai Pro or Max subscription, or
behind a gateway spend limit, and only after the session's first response. Behind a gateway alone, the window
is `spend_limit`, so the 5-hour and weekly rules do not apply there. With no reading, nothing is refused and
nothing is announced. A guard that throws is skipped and the call runs (the engine's rule), so the usage
refusal fails open; the relay refusal makes no async call before it decides. Mods need Claude Code 2.1.287 or
later; this was developed against 2.1.292. The declarations and their checksum are in
`docs/evidence/audits/2026-10-07-mods-tool-call-ratelimits-2.1.292.md`.

## What this does not cover

Whether the content is *worth* its bytes is a review question, not a gate. The check answers only
**"did it grow without anyone deciding to let it"**.

Agent output is a separate budget with a separate failure mode — an agent's answer lands in the
parent conversation and stays there for the rest of the session, so a verbose agent is a permanent
tax rather than a one-off. That is [#1086](https://github.com/fmanimashaun/claude-skills/issues/1086).
