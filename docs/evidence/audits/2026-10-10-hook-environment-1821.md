# Threat model for #1821: can a repository reach a plugin hook's environment?

Date: 2026-10-10. Verified by `doctrine-verifier` against the live Claude Code docs; the second pass read the three pages WHOLE
(settings-reference.md 421,359 characters, env-vars.md 169,048, settings.md 57,979, each read to its last line) because the first
pass had read only part of two of them. Version boundaries are quoted where the pages state them.

## The question #1821 puts first

> A written threat model that answers (a) first: can a project's settings or a repository reach the hook's environment at all? If
> they can, no design in this issue is safe and it should not be built.

(#1821 acceptance for a retry.) The two features are a project's own test preflight script run by a `PreToolUse` hook, and an
automatic Postgres restart run by the same hook.

## Findings

| # | Claim | Verdict | Quote and source |
|---|---|---|---|
| H1 | A project's checked-in `.claude/settings.json` sets environment variables for the session | CONFIRMED | settings-reference `env`: *"Set environment variables for every session and for the subprocesses Claude Code starts from it."* Values *"reach every subprocess Claude Code starts."* `.claude/settings.json` is the "Shared project" level, "Everyone in the project" (settings) |
| H2 | `PATH`, `PYTHONPATH`, `NODE_OPTIONS`, `LD_PRELOAD`, `LD_LIBRARY_PATH`, `DYLD_*`, `GIT_*` and `SHELL` are not on the documented ignore list for project settings | CONFIRMED-NOT-BLOCKED by the list as written | The whole-page grep found `PYTHONPATH`, `NODE_OPTIONS`, `LD_PRELOAD`, `LD_LIBRARY_PATH` and `DYLD_*` nowhere in the three pages; `PATH` only inside "binary outside `PATH`" and the listed Windows `PATHEXT`; `GIT_CONFIG_COUNT`/`KEY`/`VALUE` once, in the subprocess-scrub paragraph of env-vars.md (not the ignore list). The ignore list ("Variables Claude Code ignores in `env`", settings-reference line 2911) names storage locations (`CLAUDE_CONFIG_DIR`, `CLAUDE_CODE_TMPDIR`, `HOME`, `TMPDIR`, `TMP`, `TEMP`, `XDG_*`), Windows program-selection variables (`SystemRoot`, `ComSpec`, `ProgramData`, `LOCALAPPDATA`, `PATHEXT`, `PSModulePath`, the `ProgramFiles` family), session-content and OpenTelemetry exporter variables, startup variables (`CLAUDE_CODE_PROCESS_WRAPPER`, `CLAUDE_CODE_SYNC_SKILLS`, `CLAUDE_CODE_SYNC_PLUGINS`, `CLAUDE_CODE_PLUGIN_CACHE_DIR`, `CLAUDE_CODE_PLUGIN_SEED_DIR`), dialog timers, and `CLAUDE_CODE_DISABLE_ATTACHMENTS`. **Limit: it is introduced with *"They include:"*, so it is representative, not a closed enumeration. Absence from it is not a statement that a variable is allowed.** |
| H3 | Project `env` applies after trust, or immediately in `-p` mode | CONFIRMED | *"From project and local settings: after you trust the workspace, or at startup in `-p` mode, which never shows the trust dialog"* (settings-reference). The permissions page's table "What runs before you trust a folder" lists *"Hooks in settings files, the `env` block and helper commands such as `apiKeyHelper`"* as "Used" for both "You trusted only a parent folder" and "`claude -p` or the SDK, folder never trusted". **INCONCLUSIVE:** what the trust dialog does for variables outside a "safe" set (the pages say *"Variables Claude Code classifies as safe"* apply *"at startup from every settings file"* without enumerating the set) |
| H4 | A plugin hook inherits the session environment | CONFIRMED | hooks: *"Handlers run in the current directory with Claude Code's environment."*; *"A hook process inherits the parent environment"* (exceptions: `OTEL_*` exporter variables, Anthropic credentials in HIPAA sessions). plugins-reference: hook commands get `CLAUDE_PLUGIN_ROOT`, `CLAUDE_PLUGIN_DATA`, `CLAUDE_PROJECT_DIR`; *"The variables aren't present in the environment of commands Claude runs through the Bash tool, in the main session or in a subagent."* env-vars (line 555 area): a subprocess scrub applies to *"subprocesses it starts, such as Bash commands, hooks, and stdio MCP servers"*, and leaves `GIT_CONFIG_COUNT`, `GIT_CONFIG_KEY_<n>`, `GIT_CONFIG_VALUE_<n>` *"in place, whatever it holds"* |
| H5 | A `PreToolUse` hook runs before the permission prompt | CONFIRMED | hooks: *"PreToolUse hooks run before every tool call, whether or not it needs permission. PermissionRequest hooks run only when Claude Code is about to ask you for permission"* |

## Consequence

[Inferred from H1 to H5; the docs never state it as one sentence, and it was not tested empirically here (that is #1843).] A repository
that ships `.claude/settings.json` with an `env` block can place `PATH`, `PYTHONPATH`, `GIT_CONFIG_COUNT`/`GIT_CONFIG_KEY_0=core.fsmonitor`
or `GIT_EXTERNAL_DIFF` in the environment of a plugin hook, once the folder is trusted and immediately in `claude -p` and SDK runs. A
`PreToolUse` hook that runs `git`, `python3` or a script it finds by name then runs what the repository chose, before the user has
been asked about the command. **The answer to #1821's question (a) is yes, so by its own acceptance rule neither feature is built:**

- (a) a project's own preflight script (even pinned by hash): the interpreter and the wrapper are resolved from the inherited
  environment before any of the pinning code runs; the abandoned design's own "Not closable inside the script" list said so.
- (b) an automatic Postgres restart: the command it would run is chosen by an environment a project can influence.

#1821 is closed as not planned, citing this file. What this does NOT show: that any shipped hook is exploitable today. That is a
measurement, filed as #1843 (a scratch project whose `.claude/settings.json` sets `PATH` to a directory holding a fake `python3`; the same for
`GIT_CONFIG_COUNT`; interactive after trust, and `claude -p`).

## What the narrowed #1564 does about it (decision recorded on #1564)

The owner's standing rule: a `PreToolUse` hook never executes repository- or environment-controlled code. So the WIP commit is a
`Stop` hook only (after the turn), and even there it runs `git` by an absolute path found outside the project, with a scrubbed
environment (no `GIT_*`), `core.hooksPath` and `core.fsmonitor` disabled and `commit --no-verify`. The `PreToolUse[Bash]` WIP commit on
`git push`, `gh pr merge` and `gh pr ready` is dropped.
