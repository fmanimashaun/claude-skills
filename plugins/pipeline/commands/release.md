---
description: Build the release artifact — a versioned Docker image pushed to ghcr.io, pull-and-run verified locally; Kamal deploy when cloud config is present
---

# /pipeline:release

Produce the release artifact. The artifact is a Docker image — the SAME image you'll
later pull onto a cloud server with Kamal. "Local vs cloud" is only *where it's
pulled*, never a different build.

## Gate (hard)

Refuse unless `qa/CERTIFICATION` exists, verdict PASS, and its sha matches
`git rev-parse origin/dev`. Uncertified code is never imaged. (The qa-flow release
gate hook enforces this at the git layer too; this is the flow-level check.)

## Read config

`pipeline.yml`: `registry` (default `ghcr.io`), `image` (e.g.
`ghcr.io/fmanimashaun/fidara-ledger`), `mode` (`local` | `cloud`). Absent → tell the
user to run `/pipeline:setup-pipeline`.

## Build → tag → push (both modes)

Rails 8 ships the Dockerfile; use it. Build for a stable arch, tag with the certified
sha AND a moving tag:

```bash
SHA=$(git rev-parse --short origin/dev)
docker build -t "$IMAGE:$SHA" -t "$IMAGE:latest" .
echo "$KAMAL_REGISTRY_PASSWORD" | docker login ghcr.io -u "$REGISTRY_USER" --password-stdin
docker push "$IMAGE:$SHA" && docker push "$IMAGE:latest"
```

The `$SHA` tag is the immutable release; `latest` is convenience. Registry auth uses
a GitHub PAT with `write:packages` as `KAMAL_REGISTRY_PASSWORD` (Kamal's own var name,
so the same secret works later). Never echo the token; prefer `--password-stdin`.

## Deploy action — mode-aware

**mode: local (default today)** — prove the artifact boots by pulling it FRESH and
health-checking, the honest smoke test of the image itself:

```bash
docker rm -f pipeline-verify 2>/dev/null || true
docker run -d --name pipeline-verify -p 3001:3000 \
  -e RAILS_MASTER_KEY="$RAILS_MASTER_KEY" -e RAILS_ENV=production \
  "$IMAGE:$SHA"
# poll /up (Rails 8 health endpoint) until 200 or timeout
for i in $(seq 1 30); do
  curl -fsS localhost:3001/up && { echo "image boots ✓"; break; }
  sleep 2
done
docker rm -f pipeline-verify
```

A build that passes `/up` from a fresh pull is a real release candidate; a build that
only `docker build`s is not. Report the image ref, digest, and boot result.

**mode: cloud (when a server exists)** — same image, deployed by Kamal:
`kamal deploy` (config/deploy.yml already points at `ghcr.io` with the same
`$IMAGE`). Production deploy requires explicit user approval — the rails-flow deploy
guard blocks `kamal deploy` without `RAILS_FLOW_ALLOW_DEPLOY=1`. Cloud notes for
later: bind DB/internal ports to loopback (Docker bypasses UFW); decide migration
strategy in `bin/docker-entrypoint` (`db:prepare` on boot) vs a one-off `kamal app
exec`.

## Report

Image ref + digest (the pullable release), boot/deploy verdict, and the registry URL
a future server would pull from.
