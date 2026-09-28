---
description: Comprehensive release certification before dev->main — full regression plus release-only layers (load, DAST, cross-browser, a first-boot operator walkthrough, a forged-request authorization sweep); writes the stamp that unlocks the deploy gate
argument-hint: "[optional focus note]"
---

<!-- topology: parallel
     merge: ANY S1/S2 open, or any layer failing its bar, outranks every other layer's PASS (see
            Phase 4). The same defect found by two layers is ONE defect, reported with both. -->

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
pages), `perf-tester` (load profile with soak, plus the client-side capture across the
primary pages — run that one on **chromium**, since CLS and render-blocking status exist
nowhere else), `security-scanner` (ZAP baseline; active scan only with explicit
approval), `exploratory-tester` (release charters).

## Phase 3b — Release-only layers: the first-boot walkthrough and the authorization sweep (#1428)

Both are MANDATORY: the stamp cannot be written without them, and the release gate re-checks them.
They exist because a release passed every other layer and still shipped a root admin who could not
create staff, two ways to sign in as root that skipped its second factor, and a role that could
demote root. The day-one journey was never walked, and authorization was tested by action, never
by target.

1. **First-boot operator walkthrough.** On an EMPTY database (seeds only; the production-like env;
   every demo, fixture and QA shortcut OFF), drive a real browser at a phone width (<= 480px) AND
   a desktop width (>= 1024px): the operator's first sign-in with the real password and second
   factor, creating each staff role, and each new person's first sign-in and first task. Record
   `qa/manual-tests/first-boot-<version>/pages.csv` with the columns
   `Step,Width,Actor,URL,Action,Expected,Actual,Status,Notes,Screenshot,Also,Issue,Env`, plus the
   screenshots it names. Status is `Pass`, `Fail`, `Blocked` or `Not walked`. **A Blocked or Not
   walked row needs its reason in Notes**, and a Fail row names its filed issue. Redact QR codes,
   typed keys and recovery codes in every screenshot: the check refuses them only where they leaked
   as TEXT (an `otpauth://` URI, a labelled base32 key, a line of recovery codes, in any text file
   or PNG text chunk). It cannot see pixels.
2. **Forged-request authorization sweep.** For every action that changes ANOTHER account's role,
   scope, status, credentials or privileges, send a forged request from each lower role against
   each higher target, the built-in root included, and assert the target is unchanged. A hidden
   button is not a guard. Record `qa/manual-tests/authz-<version>/sweep.csv` with the columns
   `action,location,actor_role,target_role,guard,verdict,evidence,issue`, where location is
   `file:line` and verdict is `GUARDED`, `HOLE` or `UI-ONLY`. **Any HOLE or UI-ONLY fails.** At least
   one row targets root (pass `--root-role` if the app calls it something else).

Check both before Phase 4. Each exits 1 on a failing layer, 2 when there is nothing to read:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/release_evidence.py" first-boot "qa/manual-tests/first-boot-<version>"
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/release_evidence.py" authz "qa/manual-tests/authz-<version>/sweep.csv"
```

A failing layer is a FAIL verdict like any open S1/S2. What the checks do NOT judge: whether the
database was really empty, which roles the app has, and whether the sweep lists every action. Those
belong to `qa-lead`'s plan and to review.

## Phase 4 — Certify or reject

`qa-reporter` consolidates. ANY S1/S2 open, any layer failing its bar, or either release-only
layer failing (Phase 3b) → verdict FAIL, no stamp; defects filed, dev is not release-ready. Only a clean sweep →
`qa-reporter` writes `qa/CERTIFICATION` (bound to the tested dev sha) and promotes
the cycle's proven features into the `@regression` corpus. Report which sha is
cleared for main and remind the user the release-gate hook now permits that promotion.
**Committing the stamp** (#1337): commit `qa/CERTIFICATION` to dev by its own PR, together with the
first-boot and authz evidence it names (#1428), and change nothing else before promoting. The gate
accepts a stamp whose sha is an ancestor of dev when the only paths changed since are
`qa/CERTIFICATION` and that evidence, so the stamp's own commit never invalidates it.
Any other change after the tested sha means re-certify.
