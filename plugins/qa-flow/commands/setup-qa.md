---
description: Scaffold the independent QA workspace — Playwright, k6, seed personas, config, and tool checklist — separate from the developer test suite
---

# /qa-flow:setup-qa

Scaffold `qa/` as a self-contained QA workspace, independent of `spec/`. Never
overwrite existing files — propose merges.

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
- `qa/README.md` — how to boot the target, set env vars, run each tier

## 3. Env & GitHub

Document required env: `QA_BASE_URL`, `QA_SPEC_URL` (optional), persona token vars.
Add `.github/PULL_REQUEST_TEMPLATE.md` (the PR Documentation Contract) if absent so
human PRs carry what qa-lead needs. Ensure `qa/reports/*` and `node_modules` are
gitignored; commit configs, specs, seed, and the stamp path is NOT gitignored
(the gate reads it from the repo).

## 4. Tool checklist (report, don't auto-install)

Node + `npx playwright install` (browsers) · `pipx install schemathesis` · `k6`
(brew/choco/apt) · Docker (for the ZAP image). State which are present vs missing.

## 5. Report

Files created, personas seeded, tools to install, and the two entry points:
`/qa-flow:verify` after feature merges, `/qa-flow:certify` before release.
