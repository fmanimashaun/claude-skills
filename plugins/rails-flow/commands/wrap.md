---
description: The coordinator's handoff round, end to end — send it to every implementation session, wait out heavy runs instead of interrupting them, check every reply against git, then write the board rows and the coordinator handoff. Coordinator only.
---

# /rails-flow:wrap

Before a restart, an account switch or the end of a day, every session must leave its work where the next one can
find it: pushed, handed off, worktree removed. Run by hand, that round is eleven messages, eleven replies taken on
trust, and a board updated from memory. This command runs it, and checks each reply instead of believing it.

**Coordinator only.** An implementation session that runs it would ask its peers to stop for it. If you are not the
coordinator, stop here.

## 1. The roster comes from `ListAgents`, not from a roll call

Call `ListAgents`. It lists the sessions `SendMessage` can reach — your other local Claude Code sessions among them —
and a session appears only once it binds an inbox socket. Names are labels, not identities: when several sessions
share a name, the listing adds a short identifier to each row and uses it in the address. So key your record of who
holds what by **worktree path**, and copy the address exactly as the row prints it.

Write `sessions.json` under your own scratchpad, one entry per implementation session, marking any session that
holds a heavy run (a full suite, e2e, a mutation guard, a sweep, Docker) — your slot record knows which:

```json
[
  {"name": "claude-skills-coord", "role": "coordinator"},
  {"name": "claude-skills-54", "worktree": "/path/to/wt/f1781", "branch": "fix/issue-1781-head-moves"},
  {"name": "claude-skills-b2", "worktree": "/path/to/wt/f1755", "heavy_run": "full mutation guard, pid 4242"}
]
```

## 2. Plan the round

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/wrap_round.py" plan --sessions sessions.json
```

It prints the round message once, then one line per session: `send`, `skip` or `self`.

- **`skip`** — the session holds a heavy run. Never interrupt it: a run cut short is a run repeated, and its result
  is lost. Subscribe instead: `SendMessage` with `notify_when_idle: true` and no message, to that session. You get
  one notice when it next goes idle or exits, and it costs that session nothing. This works only from your main
  conversation and only for sessions on this machine; if no notice has arrived within 12 hours the subscription is dropped and you are told; both
  sessions need Claude Code v2.1.236 or later. When the notice arrives, send that session the round.
- **`self`** — you. The coordinator compacts; it does not clear.

## 3. Send the round

Send the printed message to every `send` session, in parallel, by `SendMessage`. A message from you carries no
authority of its own — the platform never counts one as consent and never lets one change configuration — so the
round works only where the owner's instructions give the coordinator that authority. Say so if a session refuses.

## 4. Verify every reply

Collect the replies into `replies.json` (the round asks for JSON), then:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/wrap_round.py" verify --sessions sessions.json --replies replies.json \
  --repo-root . --board-out board.json --handoff-out coordinator-handoff.md
```

| state | meaning |
|---|---|
| `READY` | the head is what `origin` holds for that branch (or, the branch merged and deleted, an ancestor of `--base`), and every worktree it said it removed is gone from `git worktree list` |
| `MISMATCH` | the reply is untrue somewhere: a short or placeholder SHA, a push that did not land, a worktree still listed |
| `MISSING` | no reply. **Silence is not READY.** |
| `SKIP` | holds a heavy run; send the round when the `notify_when_idle` notice arrives |
| `SELF` | the coordinator |

It exits 0 only when every session is `READY` (or is you); 1 on any finding **or any `SKIP`** — a session still
waiting on a heavy run has not had the round, so `verify && compact` must not compact yet; 3 if a read failed,
timed out or `git` is missing (nothing was verified — say so; do not report an empty result). It runs three reads,
each in one exact shape — `git ls-remote origin <ref>`, `git worktree list --porcelain`,
`git merge-base --is-ancestor <a> <b>` — and refuses any other command, any extra word, and any positional value
starting with `-`; it never sends, merges or removes. A branch name containing a glob character (`*`, `?`, `[`), a
backslash, whitespace or `..` is a finding: `git ls-remote` reads its pattern as a glob, so `*` would match every
branch.

Chase each `MISMATCH` and `MISSING` with the finding quoted. Re-run `verify` after their corrected replies.

## 5. Board and handoff

`board.json` holds one row per session (state, head, findings): write it to whatever board the project keeps.
`coordinator-handoff.md` names who still waits on a heavy run and who to chase. Put it where the next coordinator
reads first, then compact. Each `READY` session clears itself once its work is merged and its worktree removed.

## What this command does not do

- **It does not decide who holds a heavy run.** That is your slot record; the script trusts the `heavy_run` field.
- **It does not check a heavy run from outside.** `claude agents --json --all` reads session state from outside a
  session, but only background sessions carry a `state`; an interactive session's entry has none. Ask, or read your
  slot record.
- **It does not survive a restart by itself.** A self-paced `/loop` and a Monitor watch are not restored on resume;
  `CronCreate` tasks are, but recurring ones expire after 7 days. The handoff file is what carries the round across.
