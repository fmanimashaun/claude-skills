---
name: feedback-filter-ci-runs-by-event
description: A branch's Gates runs include the pull_request (fast, skips mutation coverage) AND the push (full) run; read the push run's conclusion before promoting, never "the latest green"
type: feedback
---

On 2026-09-04 the v1.117.0 promotion's release run failed in `mutation coverage` — the one gate the
PR sweep skips. The push-to-dev full runs on both arm commits had ALREADY failed; beside each sat the
pull_request run, green, and that was the one I read (`gh run list --branch dev` lists both under
one workflow name).

**Why:** `gates.yml` runs `--fast` on pull_request and everything on push; the two runs share the
workflow name and the head sha, so a listing without `event` cannot tell them apart.

**How to apply:** `gh run list --branch dev --json event,status,conclusion,headSha` and read the
`push` row for the sha you are promoting. Also: after touching any hook harness, run the FULL
`mutation_check.py` (it exceeds a 10-minute foreground call now — run it in the background) because
every `hook_*` guard executes the whole harness and stages only what its `needs` lists.
**It recurred on 2026-09-21, and the note above had already said what to do.** #1106 added
guard-claims fixtures to `check_hook_gates.py` — the hook harness — which gained a dependency on
`extract_claims.py` that no guard declared. Six `hook_*` guards went INERT at once: the unmutated
selftest already failed in the staged tempdir, so every mutation read as "caught". `dev`'s full
sweep went red at 16:06 and **three more merges landed on top of it**, each green on its own PR
because `--fast` skips `mutation coverage`.

The instruction was right here and I did not act on it. **So stop relying on this file for it**: the
durable fix is mechanical — a check that notices the harness changed and refuses the merge until the
full sweep has run. Reading a memo at session start is not a control.

**Also: read the push run AFTER merging, not only before promoting.** The loop `check PR → merge →
assert ancestry` never looks at the full sweep, because that sweep only exists after the merge.

Related: [[assert-ancestry-not-merge-output]], [[verify-counts-before-stating-them]],
[[a-harness-that-cannot-see-a-broken-mutation]].

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, filter-ci-runs-by-event.md._
