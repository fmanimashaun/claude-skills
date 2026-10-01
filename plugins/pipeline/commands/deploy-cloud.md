---
description: One-command autonomous cloud deploy — read the prepared .kamal/deploy.env briefing sheet, route every value to its Rails-native home, wire Kamal, and deploy with self-verification
argument-hint: "[optional: destination, e.g. production | staging]"
disable-model-invocation: true
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

0. **Resolve the destination once** (#1465). A destination is one decision with several
   consequences, and naming only one of them (the secrets file) half-applies it:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/kamal_destination.py" plan $ARGUMENTS
   ```

   Use its `env_file`, `overlay`, `setup` and `deploy` values everywhere below. With a
   destination, Kamal reads `config/deploy.<dest>.yml` over `config/deploy.yml` and
   `.kamal/secrets-common` then `.kamal/secrets.<dest>`, and **never `.kamal/secrets`**; without
   `-d` it reads none of the destination's files. Exit `2` (not a destination name) is a stop.

1. **Route** each `.kamal/deploy.env` key to its destination:
   - `CRED__*` → Rails encrypted credentials for the environment the app will RUN in: the
     `RAILS_ENV` Kamal resolves for every role (top-level `env`, then the role's, then host tags), from
     `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/kamal_destination.py" rails-env $ARGUMENTS`
     (never the destination's name, never an assumed `production`; exit `2` is a stop, including
     when the roles do not agree). Non-interactive `ActiveSupport::EncryptedConfiguration` write to
     its `write_content` / `write_key` pair + read-back verify; generate `secret_key_base` if blank.
     A NEW `write_content` hides the shared `config/credentials.yml.enc` from Rails, so seed it from
     the `content` file first (kamal-configurator shows how) or its keys vanish.
   - `KAMAL_REGISTRY_PASSWORD` / `RAILS_MASTER_KEY` / `POSTGRES_PASSWORD` → the plan's
     `env_file` (`.kamal/secrets`, or `.kamal/secrets.<dest>`), referenced by NAME in
     deploy.yml. `RAILS_MASTER_KEY` is the contents of `rails-env`'s `write_key`, the key of the
     pair just written; not its `key`, which is what the app reads today and differs on a fresh app.
   - `REGISTRY_USER` / `IMAGE` / `WEB_HOST` / `APP_HOST` → `config/deploy.yml`
     (generate via `kamal init` if absent, else patch, never clobber). With a destination,
     the hosts and anything else that differs go in the plan's `overlay`,
     `config/deploy.<dest>.yml`: Kamal refuses `-d` without it.
   - `RAILS_ENV` and non-secret toggles → deploy.yml `env.clear` (the overlay's `env.clear`
     when the destination's value differs). A `RAILS_ENV` other than `production` needs the app
     to have `config/environments/<env>.rb` (Rails loads it only if present, so a missing one boots
     silently without those settings) and a `database.yml` entry for it (without one, only the
     `primary` database falls back to `DATABASE_URL`; Rails 8.1.4 railties `engine.rb` L564–568,
     activerecord `database_configurations.rb` L214–216, L304–308). Missing either → STOP, name it.
2. **Safety pass (BLOCKING)**: `.kamal/deploy.env`, `.kamal/secrets*`, `*.key` gitignored AND
   dockerignored; `scan_committed_secrets.py` exits 0 (no secret value in any file git would
   commit, including an untracked deploy.yml; `git diff` cannot prove this, #1341);
   credentials round-trip verified.
3. **Confirm & deploy**: show the resolved plan — host, domain, image, destination,
   the NAMES routed to each bucket (never values), and the monitoring advisory — get explicit approval, then
   the plan's `setup` (first time) or `deploy` command, which carries `-d <dest>` when there is a
   destination (with `RAILS_FLOW_ALLOW_DEPLOY=1`).

## Monitoring advisory (never blocks, #1366)

Before the plan in step 3, check whether production will record anything about its own speed:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/apm_advisory.py" Gemfile.lock
```

It always exits `0`. Silence means a monitoring gem is present; one `apm advisory:` line
means none is, and goes into the plan verbatim. It is a reminder, not a precondition —
never refuse or delay the deploy on it, and never install a gem from here: the install
steps live in the `rails-8` skill's `references/observability.md` §7.

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
