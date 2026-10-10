---
description: Install the local git hooks: lifecycle nudges that spend no tokens, and the pre-push and pre-commit guards
---

# /pipeline:install-hooks

Two installers, run in this order and reported separately.

## 1. The guards (#1789) — they refuse

`pre-push` refuses a delete of `main`, `dev` or `staging`, and a push that is not a fast-forward of one (whatever the command was spelled like: `+main`, `--mirror`, an alias). `pre-commit` refuses a commit that stages a file that should never be committed (`.env`, keys, `node_modules/`, `tmp/` …), a file over 5 MiB, or more than 100 new files. Both fail closed, need only `bash` and `git`, and are tripwires under the server's branch protection, not a boundary: `--no-verify` skips them. The rules are stated at the top of each script in `${CLAUDE_PLUGIN_ROOT}/git-hooks/`.

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/install-git-guards.sh"
```

It needs no `pipeline.yml`. It writes each guard as a whole file where git runs hooks, and REFUSES (exit 1) a hook of that name that is tracked by git or is not ours, leaving it as it was: report that as not-installed, never as success. Limits are declared in the project's `GUARDRAILS.md` (`protected-branches:`, `max-staged-file-mb:`, `max-new-files-per-commit:`).

## 2. The nudges

Run the installer that writes local git hooks (nudge-only — they print a reminder and
leave a marker the SessionStart hook surfaces; they NEVER invoke Claude or spend
tokens):

```bash
bash "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/install-git-hooks.sh"
```

Requires `pipeline.yml` (run `/pipeline:setup-pipeline` first). Report what was
installed and confirm the no-token-spend behavior.

The hook goes where git runs hooks from — `git rev-parse --git-path hooks`, which honours
`core.hooksPath` and resolves a linked worktree to the common directory. If that post-merge hook
is **tracked** by git, the installer refuses and exits 1 rather than editing a shared, committed
hook; it prints the block for the user to add and commit themselves. Report that refusal as
not-installed, never as success. Mention the dormant GitHub Actions
adapter (`plugins/pipeline/pipeline.actions.yml.example`) for when cloud minutes exist.
