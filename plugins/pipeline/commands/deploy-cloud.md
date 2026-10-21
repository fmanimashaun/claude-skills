---
description: One-command autonomous cloud deploy — the project's stack declares its deploy target and agent; this command gates, bounds and reports the run
argument-hint: "[optional: destination, e.g. production | staging]"
disable-model-invocation: true
---

# /pipeline:deploy-cloud — $ARGUMENTS

Deploy the project to its cloud target with no prompting for values. The lifecycle here is
stack-neutral: gate, choose the agent, bound the run, report. **What a deploy IS for this
project belongs to its stack plugin**, which declares a deploy target, an artifact and an agent
in its stack descriptor; this command never assumes one.

## Preconditions (hard)

1. `qa/CERTIFICATION` PASSes for the current dev sha (release gate). Override only via the
   audited deploy-guard override and explicit say-so.
2. A release artifact for this sha exists, of the kind the target below names, or build it first
   (`/pipeline:release`).
3. The delegated agent's own preconditions (its briefing sheet, its prepared config) hold. Missing
   → it STOPs and lists them. Never prompt, never half-deploy.

## Choose the target — from the descriptor, never a default

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/deploy_target.py"
```

On exit `0` it prints the detected `stacks` and the descriptor's `target`, `artifact` and `agent`.
Delegate to **that `agent`**, by name, and no other.

- Exit `1` — no stack was detected, or the detected stack declares no deploy target: STOP and
  quote what it printed. There is nothing to deploy with.
- Exit `2` — it cannot judge (an unreadable manifest, two stacks that both declare a deploy
  target, a descriptor naming an agent that does not exist): STOP and quote its problems.

**Never fall back** to a target you know, on either exit. A guess at which host to push to is the
failure this step exists to refuse, and a stack plugin that is not installed is a reason to say
so, not to pick another.

## Bound the run before it starts (#128)

This is the most autonomous command in the marketplace and its blast radius is a live host, so
the agent's *"self-troubleshoot and re-run"* is bounded rather than open-ended. Open a ledger
first; the doctrine, the numbers and the four forbidden escapes are in
`${CLAUDE_PLUGIN_ROOT}/reference/stop-conditions.md`.

```bash
BREAKER="${CLAUDE_PLUGIN_ROOT}/scripts/breaker.py"
python3 "$BREAKER" start --stages configure,deploy,health
python3 "$BREAKER" report
```

Exit `0` proceed · `1` STOP · `2` unusable — never `|| true`, never `|| echo`. The `out-of-order`
refusal is the useful one here: `deploy` cannot be attempted until `configure` has passed, so a
half-configured deploy is refused by the ledger and not only by the prose above.

## Delegate

Launch the agent from the JSON, with the destination (`$ARGUMENTS`, possibly empty) and these four
**absolute paths**, which the agent cannot resolve for itself because it ships in another plugin:

```text
BREAKER=${CLAUDE_PLUGIN_ROOT}/scripts/breaker.py
SECRET_SCAN=${CLAUDE_PLUGIN_ROOT}/scripts/scan_committed_secrets.py
APM_ADVISORY=${CLAUDE_PLUGIN_ROOT}/scripts/apm_advisory.py
STOP_CONDITIONS=${CLAUDE_PLUGIN_ROOT}/reference/stop-conditions.md
```

Substitute the plugin's real install directory for `${CLAUDE_PLUGIN_ROOT}` before sending, so
each line is a path the agent can open. The agent routes its values, runs its blocking safety
pass, shows the resolved plan (names only, never values) with the monitoring advisory, and
**waits for explicit approval** before it deploys. It records every attempt through `BREAKER`.

## Post-deploy

Report each destination written (names only), the deploy result and the live-URL health check.
Failures are re-run **within the attempt cap**: three attempts, or two identical signatures, ends
it: write the diagnosis with `breaker.py stop` and hand back rather than deploying again. A fourth
attempt at an unchanged auth failure has never been the one that works, and each one is a real
push to a real registry. Never print secret values.

Close with `breaker.py report` and relay its verdict verbatim — `complete`, `partial` or
`stopped`. A deploy reported as done when the health check never passed is the worst available
outcome here: the next person believes production is serving.
