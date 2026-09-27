---
description: Re-read the Claude Code docs our doctrine quotes and review new CHANGELOG entries, filing each change as a verified issue
argument-hint: "[optional: a Claude Code version to review up to]"
---

# /maintainer-upstream — $ARGUMENTS

Claude Code ships most weeks, and our agents, hooks and doctrine quote its docs. This command
finds what changed since the last review and turns each change into an issue that goes through
the normal `/maintainer-work` loop. **It edits no doctrine itself.** (#1328)

## Precondition — marketplace repo only (hard)

MAINTAINERS-ONLY. Confirm `.claude-plugin/marketplace.json` exists at the repo root. If absent,
STOP and change nothing.

## 1. Run the check

```bash
python3 scripts/check_upstream_docs.py
```

Read the exit code as three verdicts:
- **0**: every registry quote is still on its page, and no CHANGELOG entry after the cursor names
  a surface we build on. Go to step 4.
- **1**: findings. Each `[quote-gone]` row names the page, the old quote and the files built on it.
  Each `[unreviewed]` row is one CHANGELOG entry.
- **2**: unusable (registry unreadable, or a page could not be fetched). That is **not** a pass. Fix
  the cause and re-run.

## 2. Triage each finding

For a `[quote-gone]` row, fetch `<url>.md` and find the current wording. It is one of three things:
- **Wording only, same meaning:** update the quote in the registry and in each `used_by` file. This
  still needs a doctrine-verifier verdict when a shipped file changes.
- **Behaviour changed:** file an issue (`type:incorrect-doctrine`, the `comp:*` of the `used_by`
  files) quoting the old and the new text. doctrine-verifier must return CONFIRMED before anyone
  edits.
- **Page moved:** point the registry row at the new page, and fix the citations.

For an `[unreviewed]` entry, read it against the files that use that surface (hooks →
`plugins/*/hooks/`, agents → `plugins/*/agents/` and `reference/model-tiers.md`, and so on):
- **No effect on us:** nothing to do.
- **Changes what we ship or say:** file one issue per change.
- **A new capability worth adopting:** file a `type:feature` issue. Adopting it is a design
  decision, not an upstream fact.

Every `gh issue create` carries a `comp:*`, a `type:*` and a `prio:*` label.

## 3. Add rows for anything newly relied on

When a triaged change means our doctrine now depends on a new sentence in the docs, add a row
to `docs/evidence/upstream/claude-code.json`: `id`, `url` (without `.md`), the verbatim `quote`,
and `used_by`. `--coverage` refuses a cited page with no row. It does not refuse an unregistered
quote on a page that already has a row, so add the row by hand.

## 4. Advance the cursor

Set `changelog_reviewed` to the newest version you reviewed and `reviewed_on` to today. Commit
that on its own branch off `dev` with the triage results named in the PR body. The cursor moves
only when a review actually happened.

## When it runs

`.github/workflows/upstream.yml` runs step 1 every Monday and opens or updates one
`upstream-drift` issue when it finds anything. Run this command when that issue appears, or
before a promotion that touches hooks, agents or plugin manifests.
