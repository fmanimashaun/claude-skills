---
description: Scaffold pipeline.yml and the local git-hook nudges; verify the Docker/Kamal release prerequisites
---

# /pipeline:setup-pipeline

Wire the lifecycle orchestration into this repo.

## 1. pipeline.yml

Write (never overwrite) `pipeline.yml`:

```yaml
registry: ghcr.io
image: ghcr.io/<owner>/<repo>        # inferred from git remote
mode: local                          # local (pull-and-run) | cloud (kamal deploy)
dev_branch: dev
main_branch: main
certify_target: local                # local prod-mode boot | staging URL
```

Infer `image` from the git remote. Confirm owner/repo with the user.

## 2. Docker / registry prerequisites (report, don't auto-run)

- Rails 8 Dockerfile present? (`rails app:update` generates it if upgrading)
- Docker installed and running locally?
- A GitHub PAT with `write:packages`, exported as `KAMAL_REGISTRY_PASSWORD`, and
  `REGISTRY_USER` set — needed to push to ghcr. State how to create it; never store
  it in the repo.
- `RAILS_MASTER_KEY` available for the local boot verify.

## 3. Local git-hook nudges (no token spend)

Install `/pipeline:install-hooks`: writes `.git/hooks/post-merge` that, when a
feature lands on `dev`, prints the nudge "QA verify pending — run /qa-flow:verify or
/pipeline" and touches `.git/pipeline-pending`. The pipeline SessionStart hook
surfaces that marker next time Claude Code opens. These NEVER invoke Claude headlessly
— they remember, you decide when to spend tokens. (GitHub Actions adapter is provided
dormant in `pipeline.actions.yml.example` for when cloud minutes are available;
copy to `.github/workflows/` to enable.)

## 4. Report

Files created, prerequisites present vs missing (with fix commands), and the entry
point: `/pipeline` to drive the lifecycle, `/pipeline:status` to see where you are.
