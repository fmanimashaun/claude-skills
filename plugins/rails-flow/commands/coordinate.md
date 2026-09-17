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

`sessions.json` is the session list as you already have it, plus what each session announced under
§2 of the skill:

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
  is done. Telling them it is ready is the whole of this command's authority.
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
operator's choice — on a Claude Code session, `/loop` or a scheduled wake-up — but nothing here
depends on that choice, so a machine with no scheduler loses nothing.

## Then send messages

The script reports; **you** decide and say it. Prefer the harness's direct channel over a shared
file, name the command you are quoting, and address the session by the name the session list gives.
