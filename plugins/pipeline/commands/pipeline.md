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

State the stage, run it, report where the pipeline now sits and the next command.
