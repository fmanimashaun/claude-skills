---
description: Cross-session coordination computed from the repository — who is idle with finished work, which announced paths collide, which conflicts are generated and which are the author's judgement. Reports and messages; it never merges, never writes, and stays silent on single-session work.
---

# /rails-flow:coordinate

Several sessions against one repository need somebody awake. `parallel-session-lane` says how to
behave; **nothing ran it**, so coordination fell to whichever session took it on, reactively. Every
failure that produced was a **polling gap** — the information existed, in git or in the session
list, and nobody looked.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/session_coordinator.py" --sessions sessions.json
```

`sessions.json` is the session list from **`ListAgents`** — it lists the sessions `SendMessage` can reach,
your other local Claude Code sessions among them, and a session appears only once it binds an inbox socket —
plus what each session announced under §2 of the skill. Do not rebuild that list by messaging every peer to ask
who is alive; read the listing. Names are labels: several sessions sharing one get a short identifier in each
row, so address a session exactly as its row prints it:

```json
[
  {"name": "claude-skills-6b", "state": "busy", "repo": "claude-skills",
   "paths": ["plugins/rails-flow/scripts/session_coordinator.py", "CHANGELOG.md"]},
  {"name": "claude-skills-da", "state": "idle", "repo": "claude-skills",
   "paths": ["skills/parallel-session-lane/SKILL.md", "CHANGELOG.md"]}
]
```

Add `--ledger docs/brain/DECISIONS.md` to query claimed numbers across every remote ref rather
than asking a peer — a hand-kept ledger said *"highest merged is D-073"* while the refs said
**D-079, all merged**, four numbers stale inside a day.

Write it under **your own** scratchpad path. One shared file that several sessions append to is the
collision this whole skill exists to prevent, reproduced in the coordination layer.

## What it reports

| finding | what it means |
|---|---|
| `parked` | a PR is green, older than the stall floor, and the session that announced its **branch** is idle — or nobody announced it, which is reported as an age reading, not a stall verdict |
| `collision` | two sessions announced the same file path |
| `collision-branch` | two sessions announced the same **branch** — one branch means one HEAD and one index |
| `conflict-generated` | a file changed on both sides that a generator owns — **regenerate**, do not resolve |
| `conflict-authored` | a file changed on both sides that a human owns — **its author's judgement** |
| `assign` | an issue whose paths a session has already announced, with the reason stated |
| `claims` | the highest claimed number across **every remote ref**, not from a ledger anyone maintains |
| `claims-absent` | the ledger matched nothing — stated, because an empty search and a wrong path look identical |
| `claims-unknown` | the query itself failed (a malformed `--claim-pattern` exits 128) — **nothing was checked**, which is not the same as finding nothing |
| `migration-order` | a migration numbered at or below `schema.rb`'s version: recorded as applied, never run |

Every line carries the command that produced it. That is not decoration: on the day this was
written, every correction between sessions that stuck came with its command, and every one that did
not was argued twice.

## What it will not do, and why that is enforced rather than promised

- **It cannot merge, push, comment or close.** Every subprocess goes through one allowlist of
  read-only `git` and `gh` invocations; `gh pr merge`, `git push` and fourteen others raise
  `WriteAttempted`. `--selftest` proves the refusal by attempting each one, rather than by reading
  the allowlist and agreeing with it.
- **It does not land another session's work.** The author lands their own, because they know when it
  is done — and with it they inherit the rebase-and-re-verify at the moment of the merge, because
  *the last session to measure is not the last session to change the base*. Telling them it is ready
  is the whole of this command's authority.
- **Measuring is a separate job from permitting, and this command does the first only.** It reports
  on the integration branch AFTER a merge rather than standing in front of one, and every finding it
  prints says **new at this merge** or **pre-existing**. That attribution is the point: three
  sessions in one day lost time blaming inherited failures on their own diffs, and a branch's own
  green run says nothing about the branch it lands on. Routing every merge through one session was
  tried on the same day and produced the opposite failure — eighteen merges through one queue, with
  two authors idle holding finished work.
- **It does not assign across a boundary a session has not been authorised into.** Sequencing work
  is this command's call; granting access never is. A relay from one session to another is not
  authorisation, and the one hand-off that ignored that was correctly refused.
- **It is silent on single-session work, and silent when there is nothing to say.** The lane hook
  under-detects for the same reason: an advisory that nags is an advisory that gets switched off.

## The false escalation is the failure mode to fear

Not a missed defect — **chasing a session whose work is proceeding normally.** A wrong age is
indistinguishable from a real stall in every respect except the number, and the number is exactly
what a human reading a board will not re-derive. One unit error — a local clock compared against the
forge's UTC — produced two false escalations inside five minutes, reporting a 13-minute-old PR as 70
and a 33-minute-old one as 90. Both had to be walked back by the sessions that had been chased.

So `age_minutes` **refuses a naive clock** instead of assuming one, and the selftest asserts the
12-minute PR produces no finding at all. A detector that only fires is not a detector.

## Cadence — a decision, not an assumption

The skill says **no tmux and no daemon**. That is about not *requiring* infrastructure, and this
requires none: one command, no state, no server. Re-running it on a timer is supported and is the
operator's choice, but nothing here depends on that choice, so a machine with no scheduler loses nothing.

## Wait with the native tools, not a hand-built poller (#1682)

On Claude Code, each kind of waiting has a tool. Use it rather than a loop of `sleep` and re-reads:

| waiting for | use | what to know |
|---|---|---|
| a local session to finish (a review, a long run) | `SendMessage` with `notify_when_idle: true` | one notice when it next goes idle or exits; main conversation only, sessions on this machine only; if no notice arrives within 12 hours the subscription is dropped and you are told; v2.1.236+ in both sessions |
| a state that flips (PR checks, a merge, the load average crossing a gate) | the **Monitor** tool, with a command that prints one line when the state changes | every watch has a deadline — 5 minutes by default, at most 30 — and ends with one notice, so re-arm it if still needed. Monitor is not available on Amazon Bedrock, Google Cloud's Agent Platform or Microsoft Foundry, nor when `DISABLE_TELEMETRY` or `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` is set (on Windows, only with Git Bash); there, re-check with dynamic `/loop` instead |
| a recurring pass (re-running this command) | dynamic `/loop`, which reschedules itself with `ScheduleWakeup` | it picks a delay between one minute and one hour; an iteration that neither reschedules nor stops gets one fallback wake-up about 20 minutes later |
| the next session to read the state after a restart | the handoff file | a self-paced `/loop` and a Monitor watch are not restored on resume; `CronCreate` tasks are, but recurring ones expire after 7 days |

**What stays ours, because nothing native does it:** heavy-run slots (nothing in Claude Code limits concurrent
suites), the durable record of who holds what (keyed by worktree path, since names are not identities), the
handoff, a board that knows queue order and gates, path and branch collision detection (this command), and
authority. A cross-session message can never approve anything or change configuration, so a coordinator's
assignment carries weight only where the owner's own instructions say it does.

## Then send messages

The script reports; **you** decide and say it. Prefer the harness's direct channel over a shared
file, name the command you are quoting, and address the session by the name the session list gives.
