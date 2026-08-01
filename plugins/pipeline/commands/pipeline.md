---
description: Drive the software lifecycle — detect the current stage and run the next flow (build → verify → certify → release), honoring every gate
argument-hint: "[feature description to start a new feature, or blank to advance the current stage]"
---

# /pipeline — $ARGUMENTS

The lifecycle coordinator. It doesn't replace rails-flow or qa-flow — it sequences
them and stops at every gate.

## Run

1. Delegate to `pipeline-coordinator` to detect the current stage (git state,
   `qa/CERTIFICATION`, `pipeline.yml`).
2. If `$ARGUMENTS` describes a new feature, start at DEVELOPING with
   `/rails-flow:feature $ARGUMENTS`. Otherwise advance from the detected stage.
3. Execute the next stage, honor its gate, report, and either stop (gate needs a
   human — QA failure, production approval) or continue if the user asked to run the
   whole pipeline.

## The chain (each arrow is a gate, never skipped)

```
/rails-flow:feature  →(PR merged to dev)→  /qa-flow:verify  →(PASS)→
  /qa-flow:certify  →(CERTIFICATION matches dev sha)→  /pipeline:release
```

- feature→dev: rails-flow's own gates (spec-first, review CLEAN, PR contract).
- dev verify: smoke → sanity → targeted regression. FAIL → /rails-flow:issues
  label:qa, no advance.
- certify: full regression + release layers → the stamp.
- release: containerized image, gated on the stamp (see /pipeline:release).

## Unattended runs are bounded (#128)

"Run the whole pipeline" is an unattended run, and the gates say when a stage may *advance* —
nothing said when to stop **trying**. An agent that cannot make progress does not idle: it
re-pushes the image, re-runs the deploy, reaches for the audited override because the gate is
"obviously" wrong. Each looks like activity in a log.

So a chained run is opened against a ledger and every stage asks first. Full doctrine — the
numbers, the five refusals, the four forbidden escapes, and why *escalate-and-continue* does not
apply to a gated chain — is in `${CLAUDE_PLUGIN_ROOT}/reference/stop-conditions.md`.

```bash
BREAKER="${CLAUDE_PLUGIN_ROOT}/scripts/breaker.py"
python3 "$BREAKER" start --stages verify,certify,release   # once, at the top of the run
python3 "$BREAKER" check certify                           # before spending on a stage
python3 "$BREAKER" record certify --outcome fail --signature "<the exact failure>"
python3 "$BREAKER" report                                  # the verdict, at the end
```

`check` exits `0` proceed · `1` STOP (`already-passed`, `out-of-order`, `attempt-cap`,
`no-progress`, `budget`) · `2` unusable. On a STOP, write the diagnosis with `breaker.py stop`
and **end the run** — in a gated chain nothing downstream is independent of a stopped stage, so
"continuing" past it is the out-of-order escape under a friendlier name. Never wrap any of these
in `|| true` or `|| echo`: the exit code is the verdict.

One invocation of a single stage does not need the ledger. Opening one costs nothing, though, and
a run that turns out to need three attempts is one you wanted bounded from the start.

State the stage, run it, report where the pipeline now sits and the next command. When the run was
chained, close with `breaker.py report` and relay its verdict verbatim — **complete**, **partial**
or **stopped** — naming every stage that was not attempted. The command exits `0` only for
`complete`, so a partial run cannot be relayed as a success by anything that reads the code.
