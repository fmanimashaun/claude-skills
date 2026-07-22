---
description: Prepare cloud deployment — generate the .env.example briefing-sheet template (every value the deploy agent needs, annotated by destination) and README setup docs
---

# /pipeline:setup-cloud

Prepare (not execute) cloud deployment. Produces the CONTRACT the developer fills in
before firing `/pipeline:deploy-cloud`: a `.env` briefing sheet the agent reads to
configure everything autonomously. No deploy here.

## 1. Generate .env.example

Inspect the app (Gemfile, config, routes, `pipeline.yml`) to discover which app
secrets the running app actually needs, then write `.env.example` documenting every
value — grouped by WHERE THE AGENT WILL ROUTE IT, names/format only, no real values.
Use the canonical template in this plugin
(`${CLAUDE_PLUGIN_ROOT}/../templates/env.example`) as the base and add app-specific
runtime secrets discovered from the code. Commit `.env.example`; never commit `.env`.

## 2. Safety scaffolding

Ensure `.env`, `.kamal/secrets*`, and `*.key` are in `.gitignore` AND `.dockerignore`
(add if missing). Confirm `.env.example` carries no real values.

## 3. README "Cloud deployment" section

Document for anyone adopting this repo: copy `.env.example` → `.env`, fill every
value, ensure the target host has Docker + SSH, then run `/pipeline:deploy-cloud` —
the agent routes each value (app secrets → encrypted credentials, deploy secrets →
.kamal/secrets, facts → deploy.yml) and deploys. Note the ghcr PAT scope
(write:packages), the domain/SSL requirement, and that `.env`/keys are never
committed.

## 4. Report

`.env.example` written (variable count by destination bucket), ignore-file state,
README section added, next step: fill `.env`, then `/pipeline:deploy-cloud`.
