---
description: Scaffold pipeline.yml and the local git-hook nudges; verify the Docker/Kamal release prerequisites
---

# /pipeline:setup-pipeline

Wire the lifecycle orchestration into this repo.

## 1. pipeline.yml

## Re-run safety & repair (idempotent by construction)

Safe to re-run. `pipeline.yml` is a small owned config: on re-run, reconcile keys —
add missing keys with sane defaults, leave user-set values untouched, and REPAIR only
demonstrably-wrong keys (an `image` that contradicts the git remote, a `mode` that
isn't `local`/`cloud`, a `dev_branch` that doesn't exist in the repo) by proposing the
corrected value as a diff for approval. Never overwrite a user's deliberate value.
Local git-hook nudges follow install-git-hooks' append-or-backup discipline (they never
clobber a co-existing post-merge). Stage only authored files; never `git add -A`.

Write (never overwrite) `pipeline.yml`:

```yaml
registry: ghcr.io
image: ghcr.io/<owner>/<repo>        # inferred from git remote
mode: local                          # local (pull-and-run) | cloud (kamal deploy)
dev_branch: dev
main_branch: main
certify_target: local                # local prod-mode boot | staging URL
# Optional, for the release image build (#1701). Left out, `/pipeline:release` runs a bare `docker build`:
# build_args: { APP_VERSION: "{{release_name}}" }   # one --build-arg per entry
# labels:     { service: <app> }                    # one --label per entry (Kamal reads `service`)
```

Write the two optional keys as COMMENTS, never live: a project that has not asked for them gets the
build it always had. When the Dockerfile has an `ARG` with no default (an app that reads its version
from `ARG APP_VERSION`), say so and offer the entry: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/release_build.py"
--image x --sha y --dry-run` names each such ARG as `UNFED ARG`, without building. On re-run, leave a
declared `build_args` or `labels` exactly as the user wrote it.

Infer `image` from the git remote. Confirm owner/repo with the user.

## 2. Docker / registry prerequisites (report, don't auto-run)

- Rails 8 Dockerfile present? (`rails app:update` generates it if upgrading)
- Docker installed and running locally?
- A GitHub PAT with `write:packages`, exported as `KAMAL_REGISTRY_PASSWORD`, and
  `REGISTRY_USER` set — needed to push to ghcr. State how to create it; never store
  it in the repo.
- `RAILS_MASTER_KEY` available for the local boot verify.

## 3. Local git-hook nudges (no token spend)

Install `/pipeline:install-hooks`: writes a `post-merge` hook under
`$(git rev-parse --git-dir)/hooks/` — i.e. `.git/hooks/post-merge` in a normal clone, but the
resolved git-dir in worktrees/submodules — that, when a feature lands on `dev`, prints the
nudge "QA verify pending — run /qa-flow:verify or /pipeline" and touches
`$(git rev-parse --git-dir)/pipeline-pending` (`.git/pipeline-pending` in a normal clone).
The pipeline SessionStart hook
surfaces that marker next time Claude Code opens. It clears when the verify stage
resolves (a `/qa-flow:verify` PASS, or the pipeline-coordinator on an explicit N/A), and
can be dismissed any time with `/pipeline:ack` — e.g. a docs/tooling-only merge with
nothing to verify. These NEVER invoke Claude headlessly — they remember, you decide when
to spend tokens. (GitHub Actions adapter is provided
dormant in `pipeline.actions.yml.example` for when cloud minutes are available;
copy to `.github/workflows/` to enable.)

**CI economy:** pipeline's own release/build workflows are already `main`-only. The Rails-default
`.github/workflows/ci.yml`, though, runs the full matrix on *every* PR/push — which duplicates
the local gates + qa-flow and can exhaust Actions minutes on a private repo. `/rails-flow:setup-flow`
proposes scoping `ci.yml` to the `dev → main` gate (approved diff); prefer that so the hosted CI
runs only where it's the independent check, consistent with the pipeline release gate.

## 4. Report

Files created, prerequisites present vs missing (with fix commands), and the entry
point: `/pipeline` to drive the lifecycle, `/pipeline:status` to see where you are.
