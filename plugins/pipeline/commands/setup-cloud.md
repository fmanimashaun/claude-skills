---
description: Prepare cloud deployment — generate the .kamal/deploy.env.example briefing-sheet template (every value the deploy agent needs, annotated by destination) and README setup docs
---

# /pipeline:setup-cloud

Prepare (not execute) cloud deployment. Produces the CONTRACT the developer fills in
before firing `/pipeline:deploy-cloud`: a `.kamal/deploy.env` briefing sheet the agent reads to
configure everything autonomously. No deploy here.

## Re-run safety & repair (idempotent by construction)

Safe to re-run. `.kamal/deploy.env.example` is regenerable documentation — on re-run, refresh it to
reflect the app's current secret surface (new CRED__ keys discovered from code) while
PRESERVING any user-added annotations, and never touch the developer's actual `.kamal/deploy.env`.
`config/deploy.yml` (when deploy-cloud generates it) uses `# kamal-config:begin/end`
markers so re-runs refresh only the generated block, leaving hand edits intact; a
DEFECTIVE deploy.yml (registry/image contradicting pipeline.yml, a secret VALUE that
leaked into the committed file) is diagnosed and fixed as an approved diff. Never
overwrite deliberate config. Stage only authored files; never `git add -A`.

## 1. Generate .kamal/deploy.env.example

Inspect the app (Gemfile, config, routes, `pipeline.yml`) to discover which app
secrets the running app actually needs, then write `.kamal/deploy.env.example` documenting every
value — grouped by WHERE THE AGENT WILL ROUTE IT, names/format only, no real values.
Use the canonical template in this plugin
(`${CLAUDE_PLUGIN_ROOT}/templates/deploy.env.example`) as the base and add app-specific
runtime secrets discovered from the code. Commit `.kamal/deploy.env.example`; never commit `.kamal/deploy.env`.

## 2. Safety scaffolding

Ensure `.kamal/deploy.env`, `.kamal/secrets*`, and `*.key` are in `.gitignore` AND `.dockerignore`

**And if a repo-root `.env` exists from a previous run, say so and stop.** Earlier versions put the
briefing there, which is the path `bin/dev`'s Procfile runner reads by default — so the sheet's
`RAILS_ENV=production` and `RAILS_MASTER_KEY` were injected into local development. The app booted in
production and died at credential decryption, naming the credentials and never the briefing; with a
valid key it pointed local development at the **production database** instead.

Do not delete it: it may hold real values, and it may also hold keys the app genuinely wants. Report
it, name the risk, and let the developer move what belongs in the briefing to
`.kamal/deploy.env` and decide about the rest.
(add if missing). Confirm `.kamal/deploy.env.example` carries no real values.

## 3. README "Cloud deployment" section

Document for anyone adopting this repo: copy `.kamal/deploy.env.example` → `.kamal/deploy.env`, fill every
value, ensure the target host has Docker + SSH, then run `/pipeline:deploy-cloud` —
the agent routes each value (app secrets → encrypted credentials, deploy secrets →
.kamal/secrets, facts → deploy.yml) and deploys. Note the ghcr PAT scope
(write:packages), the domain/SSL requirement, and that `.kamal/deploy.env`/keys are never
committed.

## 4. Report

`.kamal/deploy.env.example` written (variable count by destination bucket), ignore-file state,
README section added, next step: fill `.kamal/deploy.env`, then `/pipeline:deploy-cloud`.
