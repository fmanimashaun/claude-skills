---
disable-model-invocation: true
description: 'Take the machine-wide coordinator role for THIS session, from inside it, without going to the other session to fight for it. The override a session was elected the wrong role needs: same claim as RAILS_FLOW_ROLE=coordinator, no restart.'
---

# /rails-flow:claim-coordinator

One session per machine is the coordinator (the claim is the directory `~/.claude/rails-flow/coordinator`). When this
session ended up as an implementation session, or with no role, and should coordinate, run:

```bash
node "${CLAUDE_PLUGIN_ROOT}/scripts/claim_coordinator.mjs" "$PPID" "$CLAUDE_CODE_SESSION_ID"
```

It writes the claim for this session's Claude Code process (the Bash tool's `$PPID`), whoever holds it now. It does
not message the previous holder: that session re-reads the claim at its next turn and demotes itself to
implementation. This session's role updates at its next turn too, so say what you did and carry on.

This is the owner's call. Run it only when the owner (or the coordinator-election rule in CLAUDE.md) says this session
coordinates; never to take work from a live coordinator on your own judgement.
