---
description: Convert project docs (PRDs, branding, architecture) into project-local skills and keep them synced as documentation evolves
argument-hint: "[optional: docs subpath or skill name to focus on]"
---

# /rails-flow:curate — $ARGUMENTS

Documentation that only humans read is capability the agents don't have. This command
closes that gap: `docs/` knowledge becomes project-local skills, continuously.

## Phase 0 — Context

Read `CLAUDE.md`. Ensure `.claude/skills/` exists. If `$ARGUMENTS` names a subpath or
skill, scope the run to it.

## Phase 1 — Inventory and diff

Delegate to `skill-curator`: inventory `docs/**` (excluding `docs/brain/` and
`docs/reviews/`), load `.claude/skills/.manifest.tsv` if present, and compute the
delta — new skill-worthy docs, drifted sources (hash mismatch), deleted sources with
orphaned skills.

## Phase 2 — Plan (user gate)

Present the curation plan: skills to create / update / retire, each with its source
docs and a one-line rationale, plus any project-local agent proposals. **Wait for
approval** — skills change agent behavior repo-wide; this is a human decision.

## Phase 3 — Apply

`skill-curator` executes the approved plan: distilled SKILL.md + references per
domain, both manifest files refreshed, specific files staged. Commit follows normal
flow rules (no `git add -A`).

## Phase 4 — Report

Skills created/updated/retired, manifest summary, and: if `.claude/skills/` is new
this session, remind the user to restart Claude Code so the directory is watched.

## Continuous mode

The SessionStart hook reports when curated sources drift from their skills — run this
command when it does, after PRD/branding updates, or fold a periodic line into
`loop.md`. As the project's documentation grows, so does its agents' expertise.
