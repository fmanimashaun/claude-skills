---
description: Set up the independent QA workspace — detects the codebase's testing signals and PROPOSES a stack (qa/qa.config.yml) you confirm/override, then scaffolds only the chosen tools, seed personas, and case catalogue. Stack-agnostic, free by default.
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

## 1. Inspect & detect the stack

Read CLAUDE.md (stack, auth, roles, tenancy), routes, the OpenAPI spec location, and
`docs/` for personas/acceptance criteria. Then **detect the codebase's testing signals** so
you can propose a stack (evidence → proposal), rather than asking cold:

- **Existing test tooling wins** — never propose switching a framework the repo already uses:
  - `cypress` in `package.json` (esp. with `@badeball/cypress-cucumber-preprocessor` or any
    `*.feature`) → `web_e2e: cypress-cucumber`.
  - `@playwright/test` in deps → `web_e2e: playwright`.
  - Python project (`requirements.txt`/`pyproject.toml`) with `selenium` and/or
    `pytest-bdd`/`behave` → `web_e2e: selenium-pytest-bdd`.
  - any `*.feature` / cucumber anywhere → keep it **BDD/Gherkin**.
- **Greenfield (no e2e tooling yet)** — propose from the app: JS/TS web → `playwright`
  (modern, resilient, free); Python-centric → `selenium-pytest-bdd`.
- **Mobile** — React Native / Flutter / Capacitor, or `ios/`+`android/` / Swift → `mobile: appium`; else `none`.
- **API** — an OpenAPI/Swagger spec or rswag present → `api: schemathesis`; else `none`.
- **Reporting** — existing Allure config → `allure`; else `markdown-csv` (free default).
- **Case mgmt** — existing Testmo config/creds → offer `case_management: testmo`; else `in-repo`.
- `functional_agent` → `playwright-mcp` (free) unless a self-hosted Autonoma is detected.

## 2. Propose the stack, then confirm — `qa/qa.config.yml` (qa-flow forces NO stack)

If `qa/qa.config.yml` already exists, use it. Otherwise **present the recommended config
from step 1's detection** — one short rationale per non-default line (e.g. "`web_e2e:
cypress-cucumber` — found cypress + `*.feature` in the repo"; "`mobile: appium` — detected
`android/` + `ios/`"; "`api: schemathesis` — OpenAPI at `docs/openapi.yml`") — and let the
engineer **confirm or override any line** before you write it. You *propose*; the engineer
*decides*. If detection is inconclusive for a tier, propose the free default and say so. This
file is the override point every qa-flow agent reads. Schema (free defaults shown):

```yaml
base_url: env:QA_BASE_URL
app:                                 # how /qa-flow:smoke boots the app (stack-agnostic; Rails defaults)
  start:        bin/dev              # boot command (e.g. `bin/rails server -p 3000`)
  port:         3000
  health:       /up                  # 200-when-ready route (Rails 8 default health endpoint)
  routes:       [/, /up]             # key routes the smoke gate hits (5xx = fail)
  boot_timeout: 60                   # seconds to wait for health before failing
web_e2e:          playwright        # playwright | cypress-cucumber | selenium-pytest-bdd | none
mobile:           none              # appium | none
functional_agent: playwright-mcp    # playwright-mcp | autonoma-selfhosted | none
api:              schemathesis       # schemathesis | none
perf:             k6                 # k6 | none
security:         zap                # zap | none
a11y:             axe                # axe | none
reporting:        markdown-csv       # markdown-csv | allure | both
case_management:  in-repo            # in-repo (free CSV) | testmo (paid, opt-in)
```

Everything defaults **free**. A team overrides any line — e.g. `web_e2e: cypress-cucumber`,
`mobile: appium`, or `case_management: testmo`. Re-running setup-qa reconciles scaffolding to
the current config. **Paid/optional backends are opt-in and need credentials, never
committed.**

## 3. Provision the chosen tools

- `functional_agent: playwright-mcp` → enable the MCP: `claude mcp add playwright -- npx
  @playwright/mcp@latest` (then restart). `autonoma-selfhosted` → point at the self-hosted
  instance. `none` → skip.
- `case_management: testmo` (paid, opt-in) → confirm `TESTMO_URL` + `TESTMO_TOKEN` are set in
  the environment (gitignored, never committed); `case-author` then mirrors the CSV to Testmo
  via its REST API. Absent creds → stay `in-repo` and report how to enable. (Testmo is not an
  MCP — REST/CLI only.)

## 4. Scaffold `qa/` — only what the config enables

Always: `qa/qa.config.yml`, `qa/seed.rb` (idempotent QA personas — one per role + a
second-tenant user), `qa/plans/`, `qa/reports/`, `qa/README.md`, and the **free stack-agnostic
core**:
- `qa/test-cases.csv` (header `Test ID,Title,Area,Type,Priority,Status,Source,Notes` + one
  example) — the catalogue `/qa-flow:cases` authors/maintains.
- `qa/manual-tests/` + `screenshots/` (`.gitkeep`) — where `/qa-flow:functional` writes its
  Markdown + CSV report.

Per `web_e2e` (scaffold ONE):
- **playwright** — `qa/package.json` (@playwright/test, @axe-core/playwright), `qa/playwright.config.ts`
  (setup + chromium/firefox/webkit, `baseURL` from `QA_BASE_URL`, retries=1, trace/screenshot on
  fail), `qa/e2e/` (`auth.setup.ts` → storageState, `fixtures/`, a `@smoke` spec).
- **cypress-cucumber** — `qa/package.json` (cypress, `@badeball/cypress-cucumber-preprocessor`,
  `@testing-library/cypress`), `qa/cypress.config.js`, `qa/e2e/features/*.feature` (+ `step_definitions/`),
  `cy.session()` auth, `@smoke`/`@regression` tags.
- **selenium-pytest-bdd** — `qa/requirements.txt` (selenium, pytest, pytest-bdd), `qa/e2e/features/*.feature`
  (+ `steps/`), `conftest.py` (WebDriverWait, driver fixture), Page Objects, pytest markers.
Per `mobile: appium` — `qa/mobile/` (Appium caps, accessibility-id locators, shared `.feature`s).
Per `perf/api/security/a11y` — k6 skeleton / Schemathesis config / ZAP notes / axe wiring, only if enabled.

Per `reporting: allure` (or `both`) — wire the free **Allure** reporter for the chosen
runner so every tier feeds one aggregated HTML report (`allure-results/` → `allure-report/`):
- **playwright** — add `allure-playwright` to `reporter` in `playwright.config.ts`
  (`resultsDir: qa/reports/allure-results`).
- **cypress-cucumber** — add `allure-cypress` (import in `cypress/support`, `allureCypress`
  in config), results to `qa/reports/allure-results`.
- **selenium-pytest-bdd** — `allure-pytest`; run with `--alluredir qa/reports/allure-results`.
- **appium** — the underlying runner's Allure adapter, same results dir.
- API/perf/a11y tiers write into the **same** `allure-results/` so the report is unified.
Report dir: `qa/reports/allure-results` (raw, gitignored) → `qa/reports/allure-report` (HTML,
gitignored). `both` = keep the Markdown/CSV summary too. Default `markdown-csv` skips all this.

## 5. Env & GitHub

Document required env: `QA_BASE_URL`, `QA_SPEC_URL` (optional), persona token vars.
Add `.github/PULL_REQUEST_TEMPLATE.md` (the PR Documentation Contract) if absent so
human PRs carry what qa-lead needs. Ensure `qa/reports/*` (including
`qa/reports/allure-results` and `qa/reports/allure-report`) and `node_modules` are
gitignored; commit configs, specs, seed, and the stamp path is NOT gitignored
(the gate reads it from the repo).

## 6. Tool checklist (report, don't auto-install)

List only the tools the chosen config needs, and which are present vs missing:
- **web_e2e**: playwright → Node + `npx playwright install`; cypress-cucumber → Node +
  `npm i -D cypress @badeball/cypress-cucumber-preprocessor @testing-library/cypress`;
  selenium-pytest-bdd → Python + `pip install selenium pytest pytest-bdd` + a WebDriver.
- **mobile: appium** → `npm i -g appium` + drivers (`appium driver install uiautomator2`/`xcuitest`).
- **functional_agent: playwright-mcp** → `claude mcp add playwright -- npx @playwright/mcp@latest` (free).
- **api/perf/security**: `pipx install schemathesis` · `k6` (brew/choco/apt) · Docker (ZAP image).
- **reporting: allure** (if selected) → `allure` CLI. **case_management: testmo** → `TESTMO_URL`/`TESTMO_TOKEN` set.
All free except an opt-in `testmo` license the team already holds.

## 7. Report

Files created, personas seeded, tools to install, and the entry points: `/qa-flow:cases`
to author/maintain the case catalogue, `/qa-flow:functional` for agentic functional testing
from it, `/qa-flow:verify` after feature merges, `/qa-flow:certify` before release.
