---
description: Check whether this project's installed claude-skills toolchain is behind what is published, and carry a durable marker across the restart an update requires. Pillar 1 of the autonomous flow driver — run it before any unattended work so the driver never builds on a stale toolchain.
---

# /rails-flow:toolchain-check

The **bootstrap gate**. Resolve what is installed, compare it against what is published, and
if an update is needed, record it durably so the restart does not lose the thread.

Three states, and the third is the one that matters:

| exit | meaning | what to do |
|---|---|---|
| **0** | up to date | proceed with work |
| **1** | updates available, or a plugin failed to reach target | update + restart, or escalate |
| **2** | **could not resolve one side at all** | stop — this is NOT "up to date" |

Exit 2 is never folded into 0. "I could not read the installed state" is not a pass, and a
gate that reports it as one is worse than no gate.

## Check

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/toolchain_version.py"
```

Reads the installed side from this machine and the published side over `gh`. To compare
against a local checkout instead of the network:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/toolchain_version.py" --published-from /path/to/claude-skills
```

### The detected stack's own tools (#2168, #2288)

Then install what THIS project's stack still needs. The flow is unattended, so it acts rather than printing advice:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/toolchain_install.py" --project . --session-id "$CLAUDE_CODE_SESSION_ID"
```

Each detected stack declares its plugins and CLIs in its descriptor's `toolchain` block. The script installs a missing plugin at
local scope, only from an allowlisted marketplace whose registered source it checks, and a missing CLI by the vendor's method,
after proving the package comes from the vendor's repository. It checks that the tokens (`VERCEL_TOKEN`, `SUPABASE_ACCESS_TOKEN`)
are present in `.rails-flow/toolchain.env`, which must be ignored and untracked by git, the file itself (not a symlink) and mode
0600. No install needs a token, so none is put in an argument or a log; they are there for the vendor commands you run.
The `claude plugin` commands run in the project (local scope names its `.claude/settings.local.json`), so that project's own
settings may apply to them: the guarantee holds inside a trusted workspace only (#1843).

- `INSTALLED plugin …`: it loads after a restart. Record the step, ask for the restart, and run
  `toolchain_install.py --confirm` after it.
- `BLOCKED …`: something an agent cannot do (a missing token, a refused install, a package from the wrong repository). With
  `--session-id`, each is filed as a coordination ask for the board. Move on to other work; do not wait.
- `PR NEEDED …`: a change to the project itself, such as a devDependency. Make it on its own branch and open a pull request,
  through the normal flow. It is never left as an uncommitted edit.
- A tool call that the harness denies for permission is not seen by the script. File it the same way:
  `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/lib/coordination.py" ask --session-id "$CLAUDE_CODE_SESSION_ID" --title "toolchain BLOCKED: <the denied command>"`.

Exit 0 nothing left to do, 1 a BLOCKED or PR NEEDED line, 2 could not judge (say so; nothing was installed). To see what is
missing without installing anything, run `stack_toolchain.py --project .`.

## Update, restart, resume

The gate spans a restart, which is the whole difficulty: the process that decides an update
is needed is not the process that can confirm it happened.

```bash
# 1. arm — writes docs/brain/.toolchain-update recording target versions + where to resume
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/toolchain_version.py" --arm "step-name"

# 2. update, then restart Claude Code

# 3. resume — confirm EVERY plugin reached target, then clear the marker
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/toolchain_version.py" --resume
```

`--resume` needs only the installed side, deliberately: a network failure must never strand
a marker that a restart is waiting on.

**The marker is not cleared unless every plugin reached target.** A plugin still behind is
exit 1 with the marker intact, so the next run retries rather than proceeding degraded. With
no marker present there is nothing to resume, which is a clean exit 0 — that is what makes a
second re-run after a good update a no-op.

Landing *ahead* of target is not a failure. Overshooting still satisfies "at least what we
armed for", and failing on it would make every marker go stale the moment a newer release
appeared mid-restart.

## Why this script is longer than "compare two numbers"

Five substrate facts, each found by reading the real files rather than by assuming. They are
recorded here because every one of them fails in the *silent* direction — reporting a stale
toolchain as current.

1. **`known_marketplaces.json` records no version.** It carries `source`, `installLocation`
   and `lastUpdated` only. The installed marketplace version lives one level down, in
   `<installLocation>/.claude-plugin/marketplace.json`.

2. **`installed_plugins.json` maps each plugin to a LIST of install records, not one.** Two
   versions coexist in the cache — the machine this was written on held rails-flow at both
   1.19.0 and 1.18.2, same scope, separable only by `lastUpdated`. Reading `[0]` or `[-1]`
   picks arbitrarily and can report the stale one as installed.

3. **Plugin entries in `marketplace.json` carry no `version`.** Every plugin, `rails-stack`
   included since #2182, is versioned in its own `plugins/<name>/.claude-plugin/plugin.json`.

4. **But an older published manifest still puts `rails-stack`'s version in `marketplace.json`.**
   Before #2182 `rails-stack` was a skills bundle with no plugin directory, versioned *only* there.
   A resolver comparing against such a release must read both sources, or it misses that
   version entirely — and misses it as "up to date".

5. **The drift is real.** While this was written the installed marketplace was 1.72.0
   against a published 1.73.0.

6. **Install records are per project.** A project-scoped record carries a `projectPath`, and
   several projects on one machine run different versions. Measured: rails-stack 1.63.0 for
   one project and 1.68.0 for another, installed later. The newest record machine-wide is
   therefore not this project's, and reading it reported the older project as current (#1407).
   The gate resolves only records that apply to `--project`; a record without a `projectPath`
   applies everywhere. Unverified: which of a user-scope and a project record
   Claude Code loads when both apply; the gate takes the newest, as before.

## Verifying the gate

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/toolchain_version.py" --selftest
```

28 assertions, paired: every check has a fixture that must report **and** one that must stay
silent. Five mutations were run against it — `newest_record` returning `records[0]`, dropping
the `plugin.json` fallback, folding exit 2 into 0, clearing the marker unconditionally, and
comparing versions lexically — and each was caught by the fixture named for it, not by an
unrelated one.
