---
description: Attack your own diff with the adversary agents before a human reviews it — shell-adversary and mutation-verifier in parallel, fix what blocks, re-run only those, stop when all are CLEAN or after 3 rounds
argument-hint: "[base ref, default origin/dev]"
---

# /gauntlet — $ARGUMENTS

Independent reviewers have blocked 14 PRs here on defects the author introduced
(`docs/evidence/reviews/blocked-catalogue.md`). Each block costs a full fix round. This runs the
checks they would have run, before they see it, so a review confirms rather than discovers.

It is advisory for the author and **never a substitute for the independent review**: an author's
own agents share the author's blind spots, and an author's green is not a review.

## What runs

| Agent | Runs when the diff touches | Returns |
|---|---|---|
| `shell-adversary` | a hook, a command parser, a push or redirect parser, a fallback | CLEAN or BLOCKED with the command that got through |
| `mutation-verifier` | `scripts/*.py`, `plugins/*/scripts/*.py`, a hook script | CLEAN or BLOCKED with the surviving mutation or the unguarded script |

If the diff touches neither, say so and stop: a gauntlet with nothing to attack is a pass nobody
earned, so report `nothing to attack`, not CLEAN.

## The loop

1. Work in the branch's own worktree and confirm the branch with `git branch --show-current`. The
   base is `$ARGUMENTS`, else `origin/dev`; `git fetch origin dev` first.
2. List the diff with `git diff --name-only <base>...HEAD` and pick the agents from the table.
3. **Launch the chosen agents in one message so they run in parallel.** Give each the base ref and
   nothing else; they read the diff themselves.
4. Collect the verdicts. Print one line per agent: its name, CLEAN or BLOCKED, and its finding count.
5. For every BLOCKED agent: fix each finding in the code, **add the regression fixture the finding
   implies**, and re-run only the agents that blocked. Stage what you authored by name, never
   `git add -A`.
6. Stop when every agent is CLEAN, or after **3 rounds**. After round 3, stop and report each
   remaining finding to the user. Do not loop a fourth time and do not call it done.

## Try the changed plugin in a real session

When the diff changes what a plugin's commands, agents or hooks do, the adversaries read the code; they do not run it in a session. Load the
branch's copy for one session, without installing it (flag and behaviour: <https://code.claude.com/docs/en/plugins/cli-reference#flags-that-load-a-plugin-for-one-session>):

```bash
claude --plugin-dir plugins/qa-flow --plugin-dir plugins/rails-flow
```

- A session-only copy takes precedence over an installed plugin of the same name for that session, so you exercise the diff, not what you installed.
  `claude --plugin-dir plugins/qa-flow plugin list` shows it as `qa-flow@inline` under "Session-only plugins".
- A folder of plugins loads each child holding a `.claude-plugin/plugin.json` (Claude Code 2.1.265 or later), so `--plugin-dir plugins` loads the four
  flow plugins and the `flow-suite` bundle. It does not load `rails-stack` (its source is the repository root).
- Never point it at the repository root: that would load this repo's `.claude/` maintainer tooling, which is not distributed (`evals/README.md`).
- Two plugins that depend on each other: load both; the local copy satisfies the dependency entry without installing it
  (<https://code.claude.com/docs/en/plugins/dependencies#test-a-plugin-and-its-dependency-locally>).

It is a manual step, so it is not in the table above and never makes a gauntlet CLEAN.

## Rules

- **An agent's `not run` is not CLEAN.** If it could not run an input or a guard, that is a finding
  you must resolve or hand to the user.
- **A finding you disagree with gets a written reason**, not a silent skip. Say which line, and what
  would change your mind.
- **A fix that adds a new parsing path re-runs `shell-adversary`**, even if it was CLEAN, because the
  fix is a new diff.
- Then do the rest of the checklist: the sweep, and your own read of the diff against
  `skills/code-review/SKILL.md`. The gauntlet does not replace either.
