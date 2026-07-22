---
description: Report where the repo sits in the lifecycle and the exact next command
---

# /pipeline:status

Delegate to `pipeline-coordinator` for stage detection only — no execution. Report:
current branch and base, dev sha, certification state (sha + verdict + freshness vs
dev), any open `qa,from-qa` issues, whether a release image exists for the current
sha, and the single next command to advance. Read-only; spends almost nothing.
