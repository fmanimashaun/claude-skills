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

## Architecture graph — verify, then report the delta

A release is the second cadence at which the architecture graph must be true (the first is
session end, via rails-flow's `doc-updater`). Before reporting, confirm it is current and
capture what changed since the last release:

The graph is **opt-in**, and `--check` exits 1 on a missing `graph.json` (that is the
"never generated" signal, correct for a project that opted in). So the absence test must
come first — an unguarded `--check` would report every graph-less project as a failed
release.

But the guard decides **whether to run** the check; it must never soften the verdict. Three
distinct outcomes, three branches:

```bash
GRAPH=.claude/scripts/architecture_graph.py
if [ ! -f docs/architecture/graph.json ]; then
  echo "no architecture graph in this project — skipping (the graph is opt-in)"
elif [ ! -f "$GRAPH" ]; then
  echo "ERROR: docs/architecture/graph.json exists but $GRAPH is not vendored."
  echo "Copy it from the rails-flow plugin; this project opted into the graph, so the"
  echo "release cannot verify it and must not proceed unverified."
  exit 1
else
  python3 "$GRAPH" --check          # exits 1 on drift — never swallow this
  python3 "$GRAPH" --delta origin/main
fi
```

Two rules this encodes, both learned the hard way:

- **Never `--check || echo`.** That consumes the non-zero exit (including under `set -e`), so
  a stale graph prints a warning and the release ships anyway. Worse than having no check,
  because the message makes it look like the gate ran.
- **Never conflate "no graph" with "no script".** A project that opted into the graph and then
  cannot verify it must **stop**, not skip. Silent skipping is how a guarantee erodes — and
  since the graph is opt-in per project while the script is vendored manually, that combination
  is likely, not exotic.

(If the script lives elsewhere, point `GRAPH` at
`${CLAUDE_PLUGIN_ROOT}/../rails-flow/scripts/architecture_graph.py` instead — but keep the
three-branch shape.)

Paste the `--delta` output into the release notes verbatim. **New nodes, removed nodes and
flows that changed shape** are the structural story of the release — "flow *Create an
invoice* gained a step" tells a reviewer something the image digest and a 40-file diff
cannot. A stale graph is a release defect, not a documentation chore: regenerate and commit
before tagging.

## Report

Image ref + digest (the pullable release), boot/deploy verdict, the registry URL
a future server would pull from, and the architecture-graph verdict.

State the graph verdict **explicitly, as one of three words** — `verified`, `skipped` (no graph
in this project), or `FAILED` — followed by the delta (or "no structural change"). Never report
a skip in language that could be read as a pass: "graph OK" for a project that has no graph is
how an unverified release comes to look like a verified one.
