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
   offer `/rails-flow:handoff`, then tell the user to `/clear` (owner decision, 2026-10-07: `/clear`, not `/compact`, because once the handoff is written a compaction only carries a summary of what the handoff already holds). A session with an elected role is told instead that it resets itself, and is not asked to type anything (see *A session resets itself*). It adds nothing again until the fill
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
  `prompt.submit`; the lane band uses `session.start` and `ui.render` on `AbovePrompt`; `session-reset.mjs` uses `session.start` with the matcher `isInteractive`, `tool.call` for `Bash` and for `Write|Edit`, and `turn.complete`.
  A module may not pass `$` to a function imported from another of its files; this mod imports only pure helpers
  and shared plain data from `budget-guard.mjs` and `session-reset.mjs`, never `$`.
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
| Context window (`context-nudge.mjs`) | at 70%: one line asks for `/rails-flow:handoff`; at 75% the session compacts itself (see *A session resets itself*) | — |
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

## A session resets itself: clear when the job is done, compact mid-job (#1687, #1723, #1724)

**What is true today.** `/clear` and `/compact` are commands a person types, and the owner does not want to be the
one typing them for every session. Claude Code 2.1.292's mods API (the newest declaration on this machine; 2.1.295
is the version in scope and its declaration has not been read) has `$.command.run`, which "runs a slash command as
if the person typed `/command args` ... queued and run once the session is idle", and `$.session.compact`.
So `hooks/session-reset.mjs` and the mid-job part of `hooks/context-nudge.mjs` do it, on the owner's rule of 2026-10-09.

| Situation | What happens | Never |
|---|---|---|
| **Job done** (implementation session): every PR it opened is MERGED into `dev` (read live with `gh pr view <n> --json state,baseRefName`), a handoff was written this session, and `git worktree remove` has removed every worktree it added | `$.command.run({ command: "clear" })`, then ONE prompt: "Read <handoff> first, then wait for the coordinator's message" | no clear while any PR is unmerged or unreadable, any worktree is live, a background Bash job was started this job, or under `claude -p` |
| **Mid-job at a limit** (implementation session): the context fill reaches `RAILS_FLOW_COMPACT_PCT` (default 75, a starting value, nothing measured it) or a 5-hour or weekly window reaches its warn level | `$.session.compact({ instructions })` keeping the handoff, worktrees, branches, PRs and next step | touches no worktree; never clears; waits until the nudge or the usage line has reached the model, so the handoff was asked for first |
| **Coordinator** | compacts at the same fill or usage level, keeping `RAILS_FLOW_COORDINATOR_HANDOFF` (default `~/projects/claude-skills-wt/_logs/COORDINATOR-HANDOFF.md`), the queue and the open PRs; no precondition, its handoff lives in a file | never clears |
| **No role** (election failed, `claude -p`) | one context line says so | no clear, no compact |

**How the clear is queued ahead of the next prompt.** The slow part, `gh pr view` for each PR, is done EARLY, as soon
as the job looks finished (worktree removed, handoff written), and cached against the job epoch. At `turn.complete`
the hook only reads the cache and, if it says all merged for the current epoch, calls `$.command.run({ command:
"clear" })` at once, with no `await` before it and without awaiting it ("rejects ... inside a hook the turn is waiting
on"; measured on 2.1.293 under `claude -p`, a call from `turn.complete` did not reject). The clear is therefore queued
before any later prompt, so a new assignment waits behind it and lands in the fresh context. If the turn ends before
the early check answers, the check fires the clear when it does. Any tool call voids the cached answer, and one made
after the clear was queued leaves the new job's tracking alone and skips the reset prompt. A compaction "rejects while a turn runs", so a rejected one is tried again at the next `session.measure`.
The mid-job compact does not commit or push anything (that is #1564's separate work); it requires only that the
handoff was asked for first, and the usage warning already tells the session to commit and push.

**The role is elected, machine-wide, at `session.start`** (owner rule, 2026-10-09). The first live session to
start becomes the coordinator; every later one is an implementation session. The claim is the directory
`~/.claude/rails-flow/coordinator` (the owner works across repositories, so it is not per repo), made with `mkdir`,
which is atomic: of two simultaneous starts exactly one makes it. It records the claimant's pid, session id, start
time and the process start time (`ps -o lstart`). A claim is live only while its pid exists AND that process start
time matches, so a pid recycled after a reboot is not the coordinator; a stale claim is replaced under a second
`mkdir` lock, and a taker that finds the lock held becomes an implementation session (fewer coordinators, never
more). The pid is `$PPID` of the shell `$.process.run` starts: measured under `claude -p` on 2.1.293, it is the
`claude` process itself. One context line tells the session its role, and an implementation session who the coordinator is.
- **Override and hand-over:** start a session with `RAILS_FLOW_ROLE=coordinator` to take the claim from a live
  coordinator, or `RAILS_FLOW_ROLE=implementation` to opt out of the election. The old coordinator keeps its role
  until it restarts; the effect of a stale belief is only that it compacts instead of clearing.
- **A `/clear` keeps the role.** The process goes on and "no `session.start` fires" for a clear, so the mod's variables,
  and the claim's pid, are unchanged. **A resume starts a new process** and elects again: a resumed coordinator
  re-takes its stale claim only if it starts before any other session does. Otherwise relaunch it with
  `RAILS_FLOW_ROLE=coordinator`. This is a limit, not a guarantee.
- **Not done:** the role is not written to the board's session record (`coordination.py`); that is a separate change.

**Hardening from the adversarial review of #1728.** (1) Any tool call after the turn ended, or while `gh` answers,
cancels the clear (a job epoch is compared before `$.command.run` and before the prompt). (2) A path, branch, session
id or URL is put into a prompt or the compact instructions only if it is plain (`[\w.\/~-]`, URLs
`https://github.com/...`); otherwise a generic phrase is used, so a newline in tool input cannot become an
instruction. (3) A handoff kept as a comment counts only with the comment URL `gh` printed, and the reset prompt says
to verify the author, because the repository is public. (4) A PR is the LAST full `github.com/.../pull/N` URL of
`gh pr create`'s output, and `gh pr view` is given that URL, never a bare number (the coordinator works in two
repositories). (5) Worktree commands are read as commands: `git` must be the command word (after `;`, `|`, `&&`,
`(`, `{`, `if`/`then`/`else`/`do`, `!`, `xargs`, an env prefix, or inside `bash -c`/`-lc`/`eval`), with `-C`/`-c`
skipped, a `#` comment dropped to the end of its line, and heredoc bodies dropped; a worktree path the shell builds
(`$VAR`, `$(...)`) or `xargs` reads is recorded as unknown, which no remove can match, so the clear never fires.
(6) Round 2: `turn.start` forgets the previous turn's end, so a merge answer arriving during the next turn cannot queue
a clear mid-turn; and EVERY tool call (Read, Grep, Task too) moves the epoch. (7) A background count is never
decremented: a task notification names no task id at `prompt.submit` (`origin` is only `{ kind }`), so a finished
subagent cannot be told from a finished `bin/ci`. A session that started a background Bash job therefore never
clears itself; it compacts or is cleared by hand. The claim file's threat model is the same user: it guards against
accident, not impersonation.

**What the job-done test cannot see.** "A job" is what the session did in Bash and `Write`/`Edit`: a worktree it added
and removed, a PR it opened with `gh pr create`, a file named `*handoff*` it wrote (or a `gh pr|issue comment`
mentioning a handoff). A session that opened no PR never clears itself, on purpose. A background job
(`run_in_background`) started during the job blocks the clear for good, because no event says when it ended.
State is in memory only: a reload forgets the job and the session does nothing until it has done one.

**Verified, and how.** The declaration excerpts and their sha256 are in
`docs/evidence/audits/2026-10-09-mods-command-run-clear-2.1.292.md`. The unit test
`tests/session-reset.unit.mjs` runs the real election script against a throwaway `HOME` (five rounds of simultaneous
starts, a stale takeover, a recycled pid, the override) and drives both modules with a fake host; the mutation
guards `session_reset` and `context_nudge_compact` prove those checks can fail. `claude plugin validate` and
`claude plugin test` pass on 2.1.293. **Not verified:** that `$.command.run({ command: "clear" })` really clears a live
interactive session and leaves the mod's variables intact (the declaration says so; no interactive session was driven),
that `session.start` with the `isInteractive` matcher fires beside lane-band's unmatched one, and anything on 2.1.295.

## What this does not cover

Whether the content is *worth* its bytes is a review question, not a gate. The check answers only
**"did it grow without anyone deciding to let it"**.

Agent output is a separate budget with a separate failure mode — an agent's answer lands in the
parent conversation and stays there for the rest of the session, so a verbose agent is a permanent
tax rather than a one-off. That is [#1086](https://github.com/fmanimashaun/claude-skills/issues/1086).
