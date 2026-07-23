---
description: Dismiss the post-merge QA-verify nudge marker (.git/pipeline-pending) without another merge or a manual rm. Nudge-only — never spends tokens or invokes anything.
---

# /pipeline:ack

Clear the pending-stage nudge left by the post-merge git hook. Use this when the nudge
has been handled, or when the triggering merge had nothing to QA-verify (docs / tooling /
config / brain / agent-definition changes) so there is no stage to run.

## Do

1. Resolve the marker path the git hook actually writes to (worktree-safe). **Guard the
   resolution** — if `git rev-parse` fails or is empty (not a git repo), stop; never let the
   path collapse to a root-level `/pipeline-pending` that the `rm -f` below could delete:
   ```bash
   gitdir="$(git rev-parse --git-dir 2>/dev/null)" || { echo "not inside a git repo — no pending nudge."; exit 0; }
   [ -n "$gitdir" ] || { echo "not inside a git repo — no pending nudge."; exit 0; }
   marker="$gitdir/pipeline-pending"
   ```
2. If it exists, show what it said, then remove it — nothing else:
   ```bash
   if [ -f "$marker" ]; then
     echo "clearing nudge: $(head -c 200 "$marker")"
     rm -f "$marker"
     echo "dismissed — SessionStart won't re-surface it."
   else
     echo "no pending nudge to clear."
   fi
   ```

That is the entire operation. **Nudge-only**: no build, no test, no Claude invocation, no
token spend — consistent with the hook contract (`setup-pipeline.md`). It does not advance
the lifecycle; to actually run QA verify, use `/qa-flow:verify` or `/pipeline`.

## Report

Whether a marker was present and what it said, or that there was nothing to clear.
