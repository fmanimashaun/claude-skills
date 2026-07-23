---
description: Scaffold GitHub issue templates + a label taxonomy so downstream reports arrive triage-ready. Idempotent and safe on a customized .github/.
---

# /skill-maintainer:setup-intake

Set up structured issue intake for a skills/plugins marketplace repo. Reports that
arrive with a component, type, and reproduction are triageable in seconds; free-form
reports are not. Safe to re-run — like the other flows, it owns only what it authored.

## Precondition — marketplace repo only (hard)

MAINTAINERS-ONLY. Before creating ANY file, template, label, or branch, confirm this is a
skills/plugins marketplace repo: `.claude-plugin/marketplace.json` must exist at the repo
root (the same test the SessionStart hook uses). If it is absent, STOP — mutate nothing,
create no labels — and tell the user: "skill-maintainer is a maintainers-only plugin for a
claude-skills marketplace repo, not an app project. Nothing was changed. App builders want
rails-stack / rails-flow / qa-flow / pipeline." This guard exists because setup-intake
writes `.github/ISSUE_TEMPLATE/*` and creates GitHub labels — a marketplace taxonomy that
must never land in an app repo by accident.

## Idempotency contract

- setup-intake owns the files it creates under `.github/ISSUE_TEMPLATE/` and the labels
  it defines. On re-run it refreshes managed template files, but **never overwrites a
  template a maintainer hand-edited** without showing a diff and getting approval.
- Labels are created if absent and left alone if present (never deleted).
- Stage only files you authored; never `git add -A`; `git status` after.

## 1. Issue templates (`.github/ISSUE_TEMPLATE/*.yml`)

Create form templates that capture what triage and the doctrine-verifier need, each
pre-applying its `type:*` label:

- `incorrect-doctrine.yml` — component (dropdown: rails-8 / hotwire), the claim in the
  skill, why it's wrong, **source/citation** proving it, version in use. (`type:incorrect-doctrine`)
- `skill-gap.yml` — component, what's missing, the scenario that needed it. (`type:skill-gap`)
- `plugin-bug.yml` — plugin (rails-flow / qa-flow / pipeline), command/hook, expected
  vs actual, repro steps, OS + `bash`/`python3`/`gh` availability. (`type:bug`)
- `packaging.yml` — the `.skill`/build problem, `package_core.py` output, OS + zlib.
  (`comp:packaging`, `type:bug`)
- `feature.yml` — target component, the capability, the use case. (`type:feature`)
- `config.yml` — `blank_issues_enabled: false` and a contact link to Discussions for
  usage questions (keep the tracker for actionable reports).

Fill component/version dropdowns from the actual `marketplace.json` plugins and pinned
versions so options stay truthful.

## 2. Labels

Define and create the taxonomy (idempotently — `gh label create <n> --color <hex> --force`
or skip-if-exists):
- `comp:rails-8`, `comp:hotwire`, `comp:rails-flow`, `comp:qa-flow`, `comp:pipeline`,
  `comp:packaging`, `comp:marketplace`
- `type:incorrect-doctrine`, `type:skill-gap`, `type:bug`, `type:feature`, `type:chore`
- `prio:P1`, `prio:P2`, `prio:P3`
- `needs-info`, `duplicate`

Keep a `.github/labels.yml` as the source of truth (name → color → description) so the
set is reproducible and auditable.

## 3. Report

Templates created/updated, labels created vs already-present, and the next step:
downstream users now file structured reports; you run `/skill-maintainer:triage` to
queue them.
