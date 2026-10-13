# Audit — pipeline and design-flow plugins (2026-10-12)

Scope: `plugins/pipeline` and `plugins/design-flow` (135 files between them), against dev 16b13fc7. Method: plugin audit (hooks for portability and fail-open or fail-closed role, manifests and READMEs against what ships, documented paths against the tree). Open-issue signal: none (`comp:pipeline` and `comp:design-flow` had no open issue). No earlier audit of either plugin under `docs/evidence/audits/`. Run by hand, no agent fan-out.

## Findings (filed, not fixed in place)

| # | Component | Finding | Evidence |
|---|---|---|---|
| #1945 | design-flow | `plugin.json` description names 3 of 5 agents; `check_misdescribed_agents` reads only `marketplace.json` | compared each plugin's `plugin.json` description to `agents/` and `commands/` |
| #1945 (found while fixing it) | rails-flow | `plugin.json` claims "eleven specialist subagents" and the plugin ships 13; surfaced when the rule was extended to plugin manifests | the extended `check_misdescribed_agents` reported it on the first run |
| #1946 | pipeline | `pipeline-status.sh` resolves `pipeline.yml` and `qa/CERTIFICATION` against the cwd: no nudge from a subdirectory | scratch repo: nudge printed from the root, nothing from `sub/`, exit 0 |
| #1947 | pipeline | README describes a blocking release gate and fail-safe interpreter guards the plugin does not ship | search of `plugins/pipeline` for `release-gate`; `pre-push` header says FAIL CLOSED and needs no python3 |

## Confirmed correct (the audit is evidence the claims held)

- Every shell file in both plugins passes `bash -n`.
- Every `${CLAUDE_PLUGIN_ROOT}/...` and `plugins/<name>/...` path named in a plugin's markdown, JSON and YAML exists: pipeline 28 of 28, design-flow 43 of 43.
- Hooks start with `/bin/bash -p` and source `lib/trusted-env.sh` (#1850): `pipeline-status.sh`, `board-refresh.sh`, `design-tells.sh`.
- `design-tells.sh` and the two pipeline hooks are advisory and fail open (every early exit is `exit 0`), which matches the harness-doctrine test; `board-refresh.sh` is opt-in, throttled and time-boxed under its 15 s hook timeout.
- The pipeline README's "Python floor is 3.9" is enforced: `scripts/check_python_floor.py` is a doctor gate (`shipped python parses on 3.9`).
- `git-hooks/pre-push` states its limits (tags, `--no-verify`, a clone with no hook) beside what it enforces.

## Not audited (stated)

Command and agent prose for `release`, `deploy-cloud`, `kamal-configurator` and the design-flow `generate` / `assets` flows against Kamal 2 and Docker documentation (external claims: each needs `doctrine-verifier` before an edit, so none was changed or filed from reading); the brand packs; `scripts/release_build.py` and `scripts/breaker.py` behaviour.
