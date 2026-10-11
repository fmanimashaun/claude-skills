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
| It applies after the workspace is trusted, and in `-p` / SDK runs, which never show the trust dialog, unless the user opts out (`--bare` and `--setting-sources user` are documented opt-outs) | CONFIRMED | settings-reference#env: "From project and local settings: after you trust the workspace, or at startup in `-p` mode, which never shows the trust dialog". permissions#what-runs-before-you-trust-a-folder: the `env` block is "Used" when only a parent folder was trusted, and under `claude -p` or the SDK |
| Trust is one decision per repository root, not per tool call | CONFIRMED | permissions: "In a repository, Claude Code keys the trust on the git repository root, so the trust covers the whole repository …" |
| `PATH`, `PYTHONPATH`, `LD_PRELOAD`, `DYLD_*` are not protected from project `env` | **INCONCLUSIVE** — absent from the list, but the list says "They include", so it is not stated to be exhaustive | settings-reference, "Variables Claude Code ignores in `env`": `HOME`, `TMPDIR`, `XDG_*`, `CLAUDE_CONFIG_DIR`, `CLAUDE_CODE_PROCESS_WRAPPER` and others; the four above are absent |
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
| 6 | `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1` strips variables from hook processes | CONFIRMED but narrow: it strips **credentials only** (by name or value shape) from every subprocess, keeps GitHub tokens, proxies and `GIT_CONFIG_*`, and leaves `PATH`/loader variables alone — so it does not address this record's residuals | https://code.claude.com/docs/en/hooks ("…when `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB` is set to `1`, the variables it strips") ; https://code.claude.com/docs/en/env-vars ("strip credentials from the environments of the subprocesses Claude Code starts, such as Bash commands, hooks, and stdio MCP servers") |

The decision does not rest on row 3: rows 1, 2 and 4 alone mean a repository chooses the hook's environment before the user
approves the command, and the issue's acceptance rule turns on that question, not on which variables are listed. Row 3 only
says the docs give no assurance that the dangerous ones are filtered.

So a repository the user has trusted — or any repository, in a `claude -p` or SDK run the user has not opted out of — chooses
environment variables for the hook process before the user approves the command it fires on.

**But that is not, by itself, a new exposure.** The same permissions table marks "Hooks in settings files" as "Used" in exactly the
same two situations as `env` (a parent folder trusted; `claude -p`/the SDK). A repository that wants its own preflight to run before
the prompt already has a documented, trust-gated way to do it: a PreToolUse hook in its own `.claude/settings.json`. So the reason
not to build (a) is not that the plugin would newly expose users to repository code; it is that **the plugin must not become a
second execution vector for repository code** — one home per concern, and the project's own settings file is that home, under
the trust decision the user already makes for it. A plugin feature that runs `.claude/test-preflight` duplicates that route with
weaker visibility (the user approves a plugin, not the script it would run) and adds the pinning machinery the abandoned design
needed to make it safe.

## Decision

**Neither feature is built.** This follows the acceptance rule the issue set before any code, not a new judgement:

- **(a) a project preflight run by the hook:** not built — the plugin will not be a second execution vector for repository code.
  A project that wants one declares its own PreToolUse hook in its settings file (trust-gated, the documented route), or runs it
  itself before the suite; the shipped hook only reports.
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
2. **Loader variables set by project `env`.** On macOS this is closed for the hook: SIP strips `DYLD_INSERT_LIBRARIES` for the
   protected `/bin/bash` that starts it (measured in the #1903 review), and `lib/trusted-env.sh` (line 86) unsets every `LD_*` and
   `DYLD_*` before any child runs. **Open on Linux:** `LD_PRELOAD` acts on `/bin/bash` itself, before the library's scrub runs.
3. **`DATABASE_URL`** makes `pg_isready` connect to a host the repository names: a connection, not code execution.

## Classification (harness-doctrine §10)

The test-preflight hook is **advice**: an advisory PreToolUse hook that always exits 0, adds context, and blocks nothing. Against
whom it holds: inside a trusted workspace, and in `-p`/SDK runs, a repository's own settings choose its environment (§10 item 2,
"Say against whom"). Nothing in this decision makes it a guarantee, and nothing should be read as one.

## If this is ever retried

(a) should not be retried as a plugin feature while a project's own settings file can declare the same hook: that is the home.
(b) and any residual above are retried from the harness, not the script: whether a plugin hook can be given an environment the
project cannot set. **`CLAUDE_CODE_SUBPROCESS_ENV_SCRUB` is not that mechanism:** when set to `1` it strips *credential-looking*
variables (matched by name or value shape) from every subprocess Claude Code starts — Bash, hooks, stdio MCP servers — and leaves
GitHub tokens, proxy settings and `GIT_CONFIG_*` in place (env-vars page). It does not touch `PATH`, `PYTHONPATH` or loader
variables, so it narrows credential exposure and leaves every residual above as it is. Re-read the two pages above first. The abandoned design survives as commits `d740cd81` and `c6d90fc4`
(reachable from `chore/arm-v1.156.0` and `chore/integrate-1893`; the original branch is gone), with a negative fixture per hole
and a shell-adversary pass if any of it is reused.
