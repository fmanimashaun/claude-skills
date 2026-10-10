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
`ghcr.io/fmanimashaun/fidara-ledger`), `mode` (`local` | `cloud`), and two OPTIONAL
mappings that shape the build: `build_args` and `labels` (below). Absent → tell the
user to run `/pipeline:setup-pipeline`.

## Build → tag → push (both modes)

Rails 8 ships the Dockerfile; use it. Build for a stable arch, tag with the certified
sha AND a moving tag:

```bash
SHA=$(git rev-parse --short origin/dev)
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/release_build.py" --image "$IMAGE" --sha "$SHA" \
  && echo "$KAMAL_REGISTRY_PASSWORD" | docker login ghcr.io -u "$REGISTRY_USER" --password-stdin \
  && docker push "$IMAGE:$SHA" && docker push "$IMAGE:latest"
```

A failed build (exit non-zero) stops the chain before the login and the push: never push `latest`
after a build that did not happen, or the registry's `latest` is a previous release's image.

**The build is `release_build.py`, not a bare `docker build`** (#1701). A project declares what its
image needs in `pipeline.yml`, and the script passes each entry to `docker build`:

```yaml
build_args: { APP_VERSION: "{{release_name}}" }   # --build-arg APP_VERSION=...
labels:     { service: myapp }                    # --label service=myapp (Kamal reads this one)
```

- `{{sha}}` is the short certified sha; `{{release_name}}` is `$RELEASE_NAME` when the user gave
  the release a name (`RELEASE_NAME=v1.3.0` before running the command), else the sha. No other
  `{{variable}}` exists, and an unknown one stops the build.
- Double braces are RESERVED for those two variables: a `{{` or `}}` anywhere else in a value (a nested JSON
  label such as `{"a": {"b": 1}}` has a `}}`) is an error that names the value, never text. Single braces are fine.
- With neither key set the command is exactly `docker build -t "$IMAGE:$SHA" -t "$IMAGE:latest" .`.
- Build args are visible in the image's history: never put a secret in `build_args`.
- A `pipeline.yml` the script cannot read (a list, a bad name, a twice-declared key) is exit 2 and
  nothing is built. Do not "repair" it silently and build anyway.
- `--dry-run` prints the exact command and the report without building.
- The report lists every build arg and label passed, and names each Dockerfile `ARG` that has no
  default and that `build_args` does not feed (`UNFED ARG`). **Relay that line verbatim** and ask
  the user whether the ARG is meant to stay unset; it does not stop the build. An app that shows
  "version not set" has this line to thank for being told before it shipped.

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

**That decision belongs in the script, not here.** `--if-present` makes a missing graph a
clean exit-0 skip, so this doc carries no branching at all:

```bash
python3 .claude/scripts/architecture_graph.py --check --if-present
python3 .claude/scripts/architecture_graph.py --delta origin/main
```

Run them plainly. **Do not wrap either in `|| echo` or `|| true`** — the exit code *is* the
verdict, and consuming it produces a release that looks verified and is not. If the script is
not vendored at that path the command fails loudly on its own, which is the correct outcome for
a project that opted into the graph and cannot check it.

Why it is shaped this way, since the temptation to "make it robust" with a shell guard is what
caused the defect: v1.21.0 shipped `--check || echo "graph STALE…"`. It printed a warning and
released anyway (#151). The guard existed because `--check` treated *absent* and *stale* the
same, so the doc compensated in prose — and prose is the one layer nothing tests. `--if-present`
moves that judgement into tested Python and leaves the doc with a command instead of a program.

(If the script lives elsewhere, adjust the path — but keep it a plain call.)

Paste the `--delta` output into the release notes verbatim. **New nodes, removed nodes and
flows that changed shape** are the structural story of the release — "flow *Create an
invoice* gained a step" tells a reviewer something the image digest and a 40-file diff
cannot. A stale graph is a release defect, not a documentation chore: regenerate and commit
before tagging.

## Monitoring advisory (never blocks, #1366)

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/apm_advisory.py" Gemfile.lock
```

Always exits `0`. Silence means a performance-monitoring gem is present; an
`apm advisory:` line means none is. Relay that line in the report verbatim and do not
act on it — the release is not held, and the install steps live in the `rails-8`
skill's `references/observability.md` §7.

## Report

Image ref + digest (the pullable release), the build args and labels passed (and any
`UNFED ARG` line, verbatim), boot/deploy verdict, the registry URL a future server would
pull from, the architecture-graph verdict, and the monitoring advisory line if one was
printed.

State the graph verdict **explicitly, as one of three words** — `verified`, `skipped` (no graph
in this project), or `FAILED` — followed by the delta (or "no structural change"). Never report
a skip in language that could be read as a pass: "graph OK" for a project that has no graph is
how an unverified release comes to look like a verified one.
