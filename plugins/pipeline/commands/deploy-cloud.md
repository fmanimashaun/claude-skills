---
description: One-command autonomous cloud deploy — read the prepared .kamal/deploy.env briefing sheet, route every value to its Rails-native home, wire Kamal, and deploy with self-verification
argument-hint: "[optional: destination, e.g. production | staging]"
---

# /pipeline:deploy-cloud — $ARGUMENTS

Read the prepared `.kamal/deploy.env` and do everything — no prompting for values. `.kamal/deploy.env` is the
agent's briefing sheet; the agent routes each value to where Rails convention puts it,
then deploys.

## Preconditions (hard)

1. `.kamal/deploy.env` exists with every key from `.kamal/deploy.env.example` filled (blank only where the
   template says "leave blank to generate"). Missing → STOP, list them, point at
   `.kamal/deploy.env.example`. Never prompt, never half-deploy.
2. `qa/CERTIFICATION` PASSes for the current dev sha (release gate). Override only via
   audited `RAILS_FLOW_ALLOW_DEPLOY=1` + explicit say-so.
3. A release image for this sha exists, or build it first (`/pipeline:release`).

## Run — delegate to kamal-configurator

1. **Route** each `.kamal/deploy.env` key to its destination:
   - `CRED__*` → Rails encrypted credentials (non-interactive
     `ActiveSupport::EncryptedConfiguration` write + read-back verify; generate
     `secret_key_base` if blank).
   - `KAMAL_REGISTRY_PASSWORD` / `RAILS_MASTER_KEY` / `POSTGRES_PASSWORD` →
     `.kamal/secrets` (destination-scoped if `$ARGUMENTS` names one), referenced by
     NAME in deploy.yml.
   - `REGISTRY_USER` / `IMAGE` / `WEB_HOST` / `APP_HOST` → `config/deploy.yml`
     (generate via `kamal init` if absent, else patch, never clobber).
   - `RAILS_ENV` and non-secret toggles → deploy.yml `env.clear`.
2. **Safety pass (BLOCKING)**: `.kamal/deploy.env`, `.kamal/secrets*`, `*.key` gitignored AND
   dockerignored; `git diff` proves no plaintext secret in a committed file;
   credentials round-trip verified.
3. **Confirm & deploy**: show the resolved plan — host, domain, image, destination,
   and the NAMES routed to each bucket (never values) — get explicit approval, then
   `kamal setup` (first time) or `kamal deploy` (with `RAILS_FLOW_ALLOW_DEPLOY=1`).

## Bound the run before it starts (#128)

This is the most autonomous command in the marketplace and its blast radius is a live
host, so *"self-troubleshoot and re-run"* below is bounded rather than open-ended.
Open a ledger first; the doctrine, the numbers and the four forbidden escapes are in
`${CLAUDE_PLUGIN_ROOT}/reference/stop-conditions.md`.

```bash
BREAKER="${CLAUDE_PLUGIN_ROOT}/scripts/breaker.py"
python3 "$BREAKER" start --stages configure,deploy,health
python3 "$BREAKER" check deploy
python3 "$BREAKER" record deploy --outcome fail --signature "kamal: unauthorized on ghcr.io push"
python3 "$BREAKER" report
```

Exit `0` proceed · `1` STOP · `2` unusable — never `|| true`, never `|| echo`. The
`out-of-order` refusal is the useful one here: `deploy` cannot be attempted until
`configure` (routing + the blocking safety pass) has passed, so a half-configured
deploy is refused by the ledger and not only by the prose above.

## Post-deploy

Report each destination written (names only), deploy result, live-URL `/up` check.
Self-troubleshoot failures against `.kamal/deploy.env` + `kamal app logs` and re-run idempotently
— **within the attempt cap**: `breaker.py check deploy` before each retry, and
`breaker.py record` after it with the exact failure signature. Three attempts, or two
identical signatures, ends it: write the diagnosis with `breaker.py stop` and hand back
rather than deploying again. A fourth attempt at an unchanged auth failure has never
been the one that works, and each one is a real push to a real registry.
Cloud reminders: DB/internal ports to loopback (Docker bypasses UFW); migrations via
`bin/docker-entrypoint` (`db:prepare`) or `kamal app exec`. Never print secret values.

Close with `breaker.py report` and relay its verdict verbatim — `complete`, `partial`
or `stopped`. A deploy reported as done when the `/up` check never passed is the
worst available outcome here: the next person believes production is serving.
