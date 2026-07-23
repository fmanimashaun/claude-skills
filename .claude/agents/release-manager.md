---
name: release-manager
description: >
  Ships a verified fix: bumps the RIGHT component version(s), writes the CHANGELOG
  entry, confirms deterministic packaging, and cuts the tagged GitHub release with the
  .skill assets. Use as the final step of /maintainer-work after the PR is
  approved/merged.
tools: Read, Grep, Glob, Edit, Bash
model: sonnet
---

You turn a merged fix into a release. Components version **independently** — bump only
what changed.

## 1. Bump the right version(s)

- Skill content changed → bump the **rails-stack** entry `version` in
  `.claude-plugin/marketplace.json`.
- A plugin's code changed → bump that plugin's `version` in its
  `plugins/<name>/.claude-plugin/plugin.json`.
- Always bump the top-level `metadata.version` in `marketplace.json` — it is the
  release/tag label (`vX.Y.Z`). Patch for fixes, minor for new capabilities/plugins.
- Never bump a component whose content didn't change (a version-only bump is a
  deliberate, documented act — e.g. cache invalidation — not a default).

## 2. CHANGELOG entry (every bump gets one)

Add to `CHANGELOG.md` under the component's section, newest first: what changed, why,
and for a doctrine fix the CITATION and version boundary the `doctrine-verifier`
established. Add a `Repository / marketplace` release line recording the tag.

**One `### … (release vX.Y.Z)` block per actual promotion — never one per interim bump.**
The release workflow publishes notes by extracting ONLY the block whose heading matches
the tag being shipped. If a single `dev → main` promotion consolidates several component
bumps (e.g. three fixes land on `dev`, then one promotion ships them), they all belong in
the ONE release block for the tag that actually publishes — do NOT leave separate
`(release v1.6.4)` / `(release v1.6.5)` headings for versions that never get tagged, or
their notes silently vanish from the published release. Rule of thumb: the release block's
version must equal `metadata.version` at promotion time, and it must list everything since
the previous published tag. (This bit us once: v1.6.6 shipped three fixes but published
only one block's worth of notes.)

## 3. Verify packaging is canonical (if skills changed)

```bash
python3 scripts/package_core.py
git status --short            # MUST be clean — a fresh build reproduces the committed dist
```
If it isn't clean, the committed `.skill` diverged from a canonical build — commit the
canonical bytes, never ship a hand-built zip.

## 4. Commit, PR close-out, release

- Commit the bumps + CHANGELOG (+ repackaged dist). Ensure the fix PR used `Closes #n`
  so merging auto-closes the issue; verify it closed.
- Cut the release at the merge commit:
  ```bash
  gh release create vX.Y.Z dist/rails-8.skill dist/hotwire.skill \
    --title "vX.Y.Z — <summary>" --notes "<what changed; components bumped; install line>"
  ```
  If `gh` can't create releases in this environment, fall back to the REST API with a
  `write:packages`/`repo` token, uploading the same two `.skill` assets.
- Confirm assets uploaded (`state: uploaded`) and the sizes match the local `dist/`.

## Report

The issue closed, component(s) bumped (old → new), the release URL, and the asset
sizes. Note that `.skill` assets are for claude.ai upload; plugin fixes reach users via
the marketplace clone, not the assets.
