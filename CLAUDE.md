# CLAUDE.md — maintaining the `claude-skills` marketplace

This repo **is** a Claude plugin marketplace. It ships two kinds of things to other
people, and it carries its own maintenance tooling for you.

- **Distributed (what users install):** four app-builder plugins listed in
  `.claude-plugin/marketplace.json` — `rails-stack` (the rails-8 + hotwire skills),
  `rails-flow`, `qa-flow`, `pipeline` — plus the `dist/*.skill` packages for claude.ai
  upload.
- **NOT distributed (maintainer tooling, this file's subject):** the flow under
  **`.claude/`** — commands, agents, and a status hook that live only in this repo. They
  are **not** part of the marketplace, so `/plugin marketplace add fmanimashaun/claude-skills`
  never installs them. Anyone who *clones this repo* gets them automatically; that is the
  point. (This replaced an earlier idea of a separate maintainer marketplace repo.)

If you are here to **build a Rails app**, you want the four plugins, not this file.

## The maintenance flow (the `.claude/` commands)

Downstream projects using the toolchain file issues here (via rails-flow's
`/rails-flow:report`, the reporter). You turn those issues into shipped, verified fixes:

- **`/maintainer-setup-intake`** — scaffold `.github/ISSUE_TEMPLATE/*` + the label taxonomy
  (already done for this repo; re-runnable, idempotent).
- **`/maintainer-triage [issue|label]`** — classify open issues by component × type ×
  priority, label, dedupe, and post a ranked queue. (agent: `issue-triager`)
- **`/maintainer-work [issue]`** — take ONE issue end-to-end: confirm → **verify against
  source-of-truth** → fix → PR (`Closes #n`) → version bump + CHANGELOG → release.
- **`/maintainer-audit [component]`** — proactively review a skill/plugin against
  source-of-truth + the open-issue signal; file findings as issues (don't fix in place).

Agents backing them (in `.claude/agents/`): `issue-triager`, `doctrine-verifier`,
`skill-doctor`, `plugin-doctor`, `release-manager`. A SessionStart hook
(`.claude/hooks/scripts/maintainer-status.sh`, wired in `.claude/settings.json`) surfaces
the open-issue count each session — read-only, fails open if `gh` is absent.

## The non-negotiable gate

Skills are **doctrine other people's agents follow verbatim** — a wrong "fix" ships
confident misinformation. So: **no skill claim is edited until the `doctrine-verifier`
agent confirms it against an authoritative source** (official docs for the version in
scope, the gem/framework changelog, the `docs/audits/` protocol). "It sounds right" is
never enough. A CONFIRMED verdict authorizes the edit; REFUTED closes the issue with the
citation; **INCONCLUSIVE leaves doctrine unchanged.** Record the citation + version
boundary in the CHANGELOG entry.

## Git flow (strict)

- **`dev`** is the default/integration branch. Branch `fix/*` or `feature/*` **off `dev`**.
- PR **into `dev`** with `Closes #n` (dev is default, so the merge auto-closes the issue).
- Release = PR **`dev → main`** (a merge commit). **Do not commit to `main` directly.**
- Never `git add -A` blindly — stage only files you authored; run `git status` first.

## Releases are automated — do NOT run `gh release` by hand

`.github/workflows/release.yml` fires on every push to `main`:

1. reads `metadata.version` from `.claude-plugin/marketplace.json` → tag `vX.Y.Z`;
2. if that tag doesn't exist, builds `dist/*.skill` with `scripts/package_core.py`,
   verifies committed `dist/` matches (drift guard), extracts notes from the CHANGELOG
   `(release vX.Y.Z)` block, and publishes the release with the two `.skill` assets;
3. if the tag already exists (version wasn't bumped), it is a **no-op**.

So to ship: land the fix on `dev`, **bump `metadata.version`**, then merge `dev → main`.
The workflow does the rest.

## Versioning discipline

- Components version **independently**. Bump only what changed:
  - skill content → the **rails-stack** `version` in `marketplace.json`;
  - a plugin's code → that plugin's `plugins/<name>/.claude-plugin/plugin.json`;
  - always bump the top-level `metadata.version` — it is the release tag label. Patch for
    fixes, minor for new capabilities.
- **Every bump gets a CHANGELOG entry** under the component's section (newest first).
- **One `### … (release vX.Y.Z)` block per actual promotion.** The workflow publishes
  only the block whose heading matches the shipped tag. If a single `dev → main`
  promotion consolidates several bumps, put ALL their notes under the one release block
  for the tag that ships — never leave `(release vX.Y.Z)` headings for versions that never
  get tagged, or their notes vanish from the published release. (This bit us: v1.6.6
  shipped three fixes but first published one block's worth of notes.)

## Packaging (skills)

`scripts/package_core.py` is the ONE canonical `.skill` builder — **ZIP_STORED**
(uncompressed) + pinned `create_system`, so output is byte-identical on any OS/Python/zlib.
Never zip skills any other way. After any `skills/**` edit: `python3 scripts/package_core.py`
then confirm `git status` shows only the intended `dist/` change. The CI drift guard fails
a release if committed `dist/` isn't a clean build.

## The feedback loop

`/rails-flow:report` (in the rails-flow plugin, shipped to users) → files structured,
deduped, version-pinned issues **here** → you `/maintainer-triage` and `/maintainer-work`
them → `dev → main` auto-releases. Every issue in this tracker arrived this way.

## Platform

The `.claude/` hook and the plugins' hooks are **bash + `python3`**, and the flow drives
**`gh`** (authenticated: `gh auth status`). On Windows, run Claude Code in **WSL or Git
Bash** with `python3` and `gh` on PATH. Hooks fail open when a dependency is missing.
