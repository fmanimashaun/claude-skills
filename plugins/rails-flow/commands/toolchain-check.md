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

3. **Most plugin entries in `marketplace.json` carry no `version`.** Four of five have none.

4. **Because the two version sources are disjoint, not redundant.** `rails-stack` is a
   skills bundle with no plugin directory, so it is versioned *only* in `marketplace.json`;
   the four code plugins are versioned *only* in their own
   `plugins/<name>/.claude-plugin/plugin.json`. Read either source alone and you miss the
   other set entirely — and miss it as "up to date".

5. **The drift is real.** While this was written the installed marketplace was 1.72.0
   against a published 1.73.0.

## Verifying the gate

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/toolchain_version.py" --selftest
```

28 assertions, paired: every check has a fixture that must report **and** one that must stay
silent. Five mutations were run against it — `newest_record` returning `records[0]`, dropping
the `plugin.json` fallback, folding exit 2 into 0, clearing the marker unconditionally, and
comparing versions lexically — and each was caught by the fixture named for it, not by an
unrelated one.
