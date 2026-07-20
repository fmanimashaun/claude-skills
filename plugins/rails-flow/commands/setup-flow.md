---
description: Scaffold the rails-flow conventions into this project — CLAUDE.md, GUARDRAILS.md, and the docs/brain memory system
---

# /rails-flow:setup-flow

Install the flow's project scaffolding. Never overwrite an existing file — if CLAUDE.md or
GUARDRAILS.md exists, propose a merged diff and let the user decide.

## 1. Inspect the project first

Fill the templates from reality, not assumptions: read the Gemfile (Rails version, DB
adapter, auth/authz gems, form builder, test stack, deployment), `config/application.rb`,
`db/schema.rb` header, directory shape (`app/services`? `spec/`? `mobile/`?), and existing
docs. Note every place the project deviates from the rails-8 skill's vanilla doctrine —
those become **Project Overrides**.

## 2. Create `CLAUDE.md` with this structure

```markdown
# CLAUDE.md — <project>

**Product**: <one line> · **Stack**: Rails <x>, <DB>, Hotwire, <CSS>, Solid Queue, Kamal 2
This file is the AI agent entry point. Read it before starting any task.

## App Identity
<table of framework, database, jobs, cache, websockets, storage, auth, authorization,
asset pipeline, CSS, deployment, test suite — filled from the Gemfile/config inspection>

## Common Commands
<dev server, console, migrate, targeted + full rspec, rubocop on changed files, brakeman,
bundler-audit, deploy — the project's real commands>

## Project Overrides (beats general doctrine)
<explicit list of deliberate deviations from the rails-8/hotwire skills, e.g.:
- Forms: simple_form mandatory — never raw form_with (styling lives in the initializer)
- Authorization: CanCanCan, hash conditions only
- Tenancy: all queries scoped through Current.<scope>; public ids in URLs, never DB ids
- N+1 detection: prosopite raises in test
Keep this section honest — an empty list is a valid answer.>

## Patterns
<the 3-6 patterns agents must copy: controller shape, service invocation + result object,
job shape (ids only, idempotent), key concerns — short code snippets from THIS codebase>

## Verification Commands
<grep one-liners that mechanically check the overrides, e.g. no raw form_with in views,
no unguarded .unscoped, no raw palette colors>

## When Working in This Repo
<numbered ALWAYS-rules distilled from the above>

## See Also
AGENTS routing → the rails-flow plugin agents · GUARDRAILS.md · docs/brain/MEMORY.md
```

## 3. Create `GUARDRAILS.md`

Sections: **Database migrations** (safe vs prohibited-without-approval, the migration
checklist with rollback proof, required patterns incl. money `decimal(15,2)`), **Git**
(branch model `main ← staging ← dev ← feature/*` adapted to this repo's real branches; no
force-push, no `git add -A`, no `--no-verify`, stage specific files, small logical commits),
**Secrets** (credentials only; never commit .env), **Deploys** (require explicit user
approval). Note at the top: *the rails-flow hooks enforce these mechanically; this document
is the human-readable law they implement.*

## 4. Seed the memory system

Create `docs/brain/MEMORY.md` (an index: one line per memo — link + 8-15 word summary) and
explain `/rails-flow:brain` to the user: lessons and decisions get institutionalized as
memos, not lost in chat history.

## 5. Report

List created files, the detected Project Overrides, and any ambiguity you need the user to
settle (e.g. base branch, form builder mandate yes/no).
