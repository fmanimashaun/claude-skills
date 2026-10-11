# Threat model: a project's own test preflight and an automatic Postgres restart (#1821)

_2026-10-12 · claude-skills · decision: **not built**. Docs read 2026-10-12; quotes verbatim._

#1821 is the follow-up to #1561 / #1566, which shipped the PreToolUse test-preflight hook
(`plugins/rails-flow/hooks/scripts/test-preflight.sh`, `plugins/rails-flow/scripts/test_preflight.py`) WITHOUT two features:

- **(a)** a project's own preflight script, `.claude/test-preflight`, run by the hook;
- **(b)** an automatic Postgres restart, from a command the environment or a user file supplies.

Its acceptance asks for this record first: *can a project's settings or a repository reach the hook's environment at all? If they
can, no design in this issue is safe and it should not be built.*

## The question, answered: yes

| claim | verdict | source |
|---|---|---|
| A committed `.claude/settings.json` (and `.claude/settings.local.json`) may set `env`, and it reaches hook processes | CONFIRMED | settings-reference#env: "Values here are plain text in the settings file and reach every subprocess Claude Code starts." hooks: "A hook process inherits the parent environment, apart from the `OTEL_*` exporter variables …" |
| It applies after the workspace is trusted, and **always** in `-p` / SDK runs, which never show the trust dialog | CONFIRMED | settings-reference#env: "From project and local settings: after you trust the workspace, or at startup in `-p` mode, which never shows the trust dialog". permissions#what-runs-before-you-trust-a-folder: the `env` block is "Used" when only a parent folder was trusted, and under `claude -p` or the SDK |
| Trust is one decision per repository root, not per tool call | CONFIRMED | permissions: "In a repository, Claude Code keys the trust on the git repository root, so the trust covers the whole repository …" |
| `PATH`, `PYTHONPATH`, `LD_PRELOAD`, `DYLD_*` are not protected from project `env` | not on the docs' list (the list says "They include", so not exhaustive) | settings-reference, "Variables Claude Code ignores in `env`": `HOME`, `TMPDIR`, `XDG_*`, `CLAUDE_CONFIG_DIR`, `CLAUDE_CODE_PROCESS_WRAPPER` and others; the four above are absent |
| A PreToolUse hook runs before the user is asked about the command | CONFIRMED | permissions: "PreToolUse hooks run before the permission prompt, for every tool except `EndConversation`." |

URLs: https://code.claude.com/docs/en/settings-reference#env, https://code.claude.com/docs/en/hooks,
https://code.claude.com/docs/en/permissions#what-runs-before-you-trust-a-folder.

### Verification

Each row above is a **doctrine-verifier** verdict against the official Claude Code docs, fetched 2026-10-12 (agent run in the
#1821 session; the verdicts and quotes are reproduced here so they survive the session):

| # | claim | verdict | official source |
|---|---|---|---|
| 1 | project `env` (`.claude/settings.json`, `.claude/settings.local.json`) reaches hook processes | CONFIRMED | https://code.claude.com/docs/en/settings-reference#env ; https://code.claude.com/docs/en/hooks ; file table at https://code.claude.com/docs/en/env-vars |
| 2 | applies after trust, and always under `-p` / the SDK; trust is per git repository root | CONFIRMED | https://code.claude.com/docs/en/settings-reference#env ; https://code.claude.com/docs/en/permissions#what-runs-before-you-trust-a-folder |
| 3 | `PATH`, `PYTHONPATH`, `LD_PRELOAD`, `DYLD_*` are not on the ignored-variables list | **INCONCLUSIVE** — absent from the list, but the list says "They include", so it is not stated to be exhaustive | https://code.claude.com/docs/en/settings-reference (section "Variables Claude Code ignores in `env`") |
| 4 | PreToolUse hooks run before the permission prompt | CONFIRMED | https://code.claude.com/docs/en/permissions |
| 5 | `CLAUDE_ENV_FILE` lets a project hook change later HOOKS' environment | REFUTED (it feeds later Bash/PowerShell tool commands only) | https://code.claude.com/docs/en/hooks |

The decision does not rest on row 3: rows 1, 2 and 4 alone mean a repository chooses the hook's environment before the user
approves the command, and the issue's acceptance rule turns on that question, not on which variables are listed. Row 3 only
says the docs give no assurance that the dangerous ones are filtered.

So a repository the user has trusted — or any repository, in a `claude -p` or SDK run — chooses environment variables for the
hook process before the user approves the command it fires on. Every hardening the abandoned design added (#1821 body: a pinned
SHA-256 in `~/.claude/rails-flow-preflight.json`, a private 0700 copy, refusing a pin file inside the project) sits downstream of
an interpreter, a `PATH` and a dynamic loader the repository can choose. The script cannot defend a decision the environment
made before its first line ran.

## Decision

**Neither feature is built.** This follows the acceptance rule the issue set before any code, not a new judgement:

- **(a) a project preflight run by the hook:** not built. A project that wants one runs it itself, before the suite (the shipped
  hook already only reports).
- **(b) an automatic Postgres restart:** not built. Restarting a service is a side effect on a command the user has not yet
  approved, and the command or its environment would be repository-reachable in both forms considered.

## What the shipped hook already does, and what remains (unchanged by this record)

The hook on `dev` runs no repository-supplied script. It is invoked as `/bin/bash -p` (no `BASH_ENV`, no imported functions),
sources `lib/trusted-env.sh` first (#1850: scrubs `PYTHON*`, `GIT_*`, `BASH_ENV`, rebuilds `PATH` from entries outside the
repository), takes `python3` only from an absolute `PATH` entry outside the project and runs it isolated (`-I`), and finds
`pg_isready`, `lsof` and `ps` the same way (`trusted_which`).

Remaining, and a harness question shared by every plugin hook, not something this script can close:

1. **An absolute `PATH` entry outside the repository that the repository's `env` names** (for example a directory under `/tmp`)
   is accepted by `trusted_which`. Exploiting it needs a writable location the repository can populate; under trust, project
   hooks can already run code, so this adds no new capability there. Not tested.
2. **`DYLD_*` / `LD_PRELOAD` set by project `env`** act on the `/bin/bash` that starts the hook (on macOS, SIP strips `DYLD_*`
   for protected binaries such as `/bin/bash`, but not for every interpreter). Not tested.
3. **`DATABASE_URL`** makes `pg_isready` connect to a host the repository names: a connection, not code execution.

## Classification (harness-doctrine §10)

The test-preflight hook is **advice**: an advisory PreToolUse hook that always exits 0, adds context, and blocks nothing. Against
whom it holds: inside a trusted workspace, and in `-p`/SDK runs, a repository's own settings choose its environment (§10 item 2,
"Say against whom"). Nothing in this decision makes it a guarantee, and nothing should be read as one.

## If this is ever retried

Start from the docs' model, not from the script: it is buildable only if Claude Code gives a plugin hook an environment the
project cannot set (for example, `PATH` and loader variables added to the ignored list, or a per-plugin environment the user
alone configures). Re-read the two pages above first; then the abandoned design in git history (`d740cd81`, `c6d90fc4` on
`feature/1561-test-run-preflight`) is the starting point, with a negative fixture per hole and a shell-adversary pass.
