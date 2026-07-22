---
description: One-command autonomous cloud deploy — read the prepared .env briefing sheet, route every value to its Rails-native home, wire Kamal, and deploy with self-verification
argument-hint: "[optional: destination, e.g. production | staging]"
---

# /pipeline:deploy-cloud — $ARGUMENTS

Read the prepared `.env` and do everything — no prompting for values. `.env` is the
agent's briefing sheet; the agent routes each value to where Rails convention puts it,
then deploys.

## Preconditions (hard)

1. `.env` exists with every key from `.env.example` filled (blank only where the
   template says "leave blank to generate"). Missing → STOP, list them, point at
   `.env.example`. Never prompt, never half-deploy.
2. `qa/CERTIFICATION` PASSes for the current dev sha (release gate). Override only via
   audited `RAILS_FLOW_ALLOW_DEPLOY=1` + explicit say-so.
3. A release image for this sha exists, or build it first (`/pipeline:release`).

## Run — delegate to kamal-configurator

1. **Route** each `.env` key to its destination:
   - `CRED__*` → Rails encrypted credentials (non-interactive
     `ActiveSupport::EncryptedConfiguration` write + read-back verify; generate
     `secret_key_base` if blank).
   - `KAMAL_REGISTRY_PASSWORD` / `RAILS_MASTER_KEY` / `POSTGRES_PASSWORD` →
     `.kamal/secrets` (destination-scoped if `$ARGUMENTS` names one), referenced by
     NAME in deploy.yml.
   - `REGISTRY_USER` / `IMAGE` / `WEB_HOST` / `APP_HOST` → `config/deploy.yml`
     (generate via `kamal init` if absent, else patch, never clobber).
   - `RAILS_ENV` and non-secret toggles → deploy.yml `env.clear`.
2. **Safety pass (BLOCKING)**: `.env`, `.kamal/secrets*`, `*.key` gitignored AND
   dockerignored; `git diff` proves no plaintext secret in a committed file;
   credentials round-trip verified.
3. **Confirm & deploy**: show the resolved plan — host, domain, image, destination,
   and the NAMES routed to each bucket (never values) — get explicit approval, then
   `kamal setup` (first time) or `kamal deploy` (with `RAILS_FLOW_ALLOW_DEPLOY=1`).

## Post-deploy

Report each destination written (names only), deploy result, live-URL `/up` check.
Self-troubleshoot failures against `.env` + `kamal app logs` and re-run idempotently.
Cloud reminders: DB/internal ports to loopback (Docker bypasses UFW); migrations via
`bin/docker-entrypoint` (`db:prepare`) or `kamal app exec`. Never print secret values.
