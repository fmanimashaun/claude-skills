---
description: Scaffold the independent QA workspace — Playwright, k6, seed personas, config, and tool checklist — separate from the developer test suite
---

# /qa-flow:setup-qa

Scaffold `qa/` as a self-contained QA workspace, independent of `spec/`. Never
overwrite existing files.

## Re-run safety & repair (idempotent by construction)

Safe to re-run on an existing qa/ workspace, as many times as needed:
- **Generated config** (playwright.config.ts, package.json, k6 skeletons): qa-flow
  owns these; on re-run, refresh only qa-flow-managed content, delimited by
  `// qa-flow:begin X` / `// qa-flow:end X` (or the file-type's comment syntax). Content
  outside the markers (a user's custom Playwright projects, added scripts) is left
  byte-for-byte untouched.
- **Seed data** (qa/seed.rb): additive — ensure the required personas exist idempotently
  (find_or_create), never wipe user-added seeds.
- **Repair**: if a managed file is DEFECTIVE against ground truth — baseURL not reading
  QA_BASE_URL, a project referencing a browser not installed, seed personas whose roles
  don't match the app's actual roles from CLAUDE.md — diagnose it, explain why, and
  propose the fix as a diff; wait for approval. Never repair a deliberate customization
  (added browsers, custom fixtures, extra thresholds) into the default.
- Stage only files setup-qa authored; never `git add -A`; `git status` after.

## 1. Inspect

Read CLAUDE.md (stack, auth, roles, tenancy), routes, the OpenAPI spec location, and
`docs/` for personas/acceptance criteria.

## 2. Scaffold `qa/`

- `qa/package.json` — Playwright, @axe-core/playwright, @playwright/test
- `qa/playwright.config.ts` — projects (setup + chromium/firefox/webkit), baseURL
  from `QA_BASE_URL`, retries=1, trace/screenshot on failure
- `qa/e2e/` — `auth.setup.ts` (log the personas in, save storageState), `fixtures/`,
  a starter `@smoke` spec covering core flows
- `qa/perf/` — a k6 smoke script + a load-profile skeleton
- `qa/seed.rb` — idempotent QA personas (one per role: admin/member/etc, plus a
  second-tenant user for isolation tests) loadable into the QA/staging env
- `qa/plans/`, `qa/reports/` — with `.gitkeep`
- **Test-case catalogue + agentic functional testing — free, repo-local:**
  - `qa/test-cases.csv` — the authored/maintained case catalogue (header
    `Test ID,Title,Area,Type,Priority,Status,Source,Notes`, plus one example row).
    **`/qa-flow:cases`** (the `case-author` agent) authors and maintains it from the
    PRD/app-surface/defects — stable IDs, idempotent; no online case manager (a Testmo
    export can seed it, but the file is the source of truth). Excel-openable.
  - `qa/manual-tests/` + `qa/manual-tests/screenshots/` (`.gitkeep`) — where
    **`/qa-flow:functional`** (the `functional-tester` agent, via Playwright MCP) writes its
    Markdown report + CSV summary + screenshots.
- `qa/README.md` — how to boot the target, set env vars, run each tier

## 3. Env & GitHub

Document required env: `QA_BASE_URL`, `QA_SPEC_URL` (optional), persona token vars.
Add `.github/PULL_REQUEST_TEMPLATE.md` (the PR Documentation Contract) if absent so
human PRs carry what qa-lead needs. Ensure `qa/reports/*` and `node_modules` are
gitignored; commit configs, specs, seed, and the stamp path is NOT gitignored
(the gate reads it from the repo).

## 4. Tool checklist (report, don't auto-install)

Node + `npx playwright install` (browsers) · `pipx install schemathesis` · `k6`
(brew/choco/apt) · Docker (for the ZAP image) · **Playwright MCP** for agentic functional
testing (`claude mcp add playwright -- npx @playwright/mcp@latest`, then restart — free).
State which are present vs missing.

## 5. Report

Files created, personas seeded, tools to install, and the entry points: `/qa-flow:cases`
to author/maintain the case catalogue, `/qa-flow:functional` for agentic functional testing
from it, `/qa-flow:verify` after feature merges, `/qa-flow:certify` before release.
