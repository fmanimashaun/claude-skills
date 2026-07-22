---
description: Comprehensive release certification before dev->main — full regression plus release-only layers (load, DAST, cross-browser); writes the stamp that unlocks the deploy gate
argument-hint: "[optional focus note]"
---

# /qa-flow:certify

The final gate before main. Comprehensive whole-application validation that existing
features work together and the system is release-ready. Run against STAGING (the real
infra tier), never production.

## Phase 0 — Environment & readiness

Confirm dev is green and deployed to staging; set `QA_BASE_URL` to staging. Record the
exact dev sha under test (`git rev-parse origin/dev`) — the stamp binds to it. Read
CLAUDE.md, docs/, project skills, and `docs/brain/` (escaped-defect history).

## Phase 1 — Smoke gate

`e2e-tester` `@smoke` against staging. Fail → stop, staging build not certifiable.

## Phase 2 — Certification plan

`qa-lead` plans the full run: complete `@regression` corpus, full-spec API, a11y
sweep, k6 load+soak profile, ZAP baseline, fuller exploratory charters.

## Phase 3 — Full execution

Dispatch all layers: `e2e-tester` (full `@regression`, chromium+firefox+webkit),
`api-contract-tester` (full spec + authz matrix), `a11y-auditor` (all primary
pages), `perf-tester` (load profile with soak), `security-scanner` (ZAP baseline;
active scan only with explicit approval), `exploratory-tester` (release charters).

## Phase 4 — Certify or reject

`qa-reporter` consolidates. ANY S1/S2 open, or any layer failing its bar → verdict
FAIL, no stamp; defects filed, dev is not release-ready. Only a clean sweep →
`qa-reporter` writes `qa/CERTIFICATION` (bound to the tested dev sha) and promotes
the cycle's proven features into the `@regression` corpus. Report which sha is
cleared for main and remind the user the release-gate hook now permits that promotion.
