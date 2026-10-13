#!/usr/bin/env bash
# SessionStart — surface certification status vs current dev so staleness is visible.
set -uo pipefail
. "${BASH_SOURCE[0]%/*}/lib/trusted-env.sh" 2>/dev/null   # #1850: scrub PYTHON*/GIT_*/BASH_ENV and rebuild PATH from outside the repository, before any python3, git or gh
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0
type -P python3 >/dev/null 2>&1 || exit 0   # no python3 → skip (non-blocking status only)
[ -f qa/CERTIFICATION ] || { [ -d qa ] && echo "- qa-flow: no certification yet — /qa-flow:certify before dev->main."; exit 0; }
# #721. Same one reader as release-gate.sh. This banner said "certification stale" forever on a
# non-conforming stamp, which is permanent false-negative noise -- and an advisory nobody can clear
# is an advisory people learn to ignore.
reader="${CLAUDE_PLUGIN_ROOT:-}/scripts/read_certification.py"
csha="$(python3 "$reader" --field sha 2>/dev/null || true)"
csha="${csha:0:12}"
verdict="$(python3 "$reader" --field verdict 2>/dev/null || true)"
if [ -z "$verdict" ]; then
  # Say what is actually wrong instead of implying the stamp is merely out of date.
  why="$(python3 "$reader" --field verdict --explain 2>/dev/null || true)"
  [ -n "$why" ] && echo "- qa-flow: $why"
  exit 0
fi
devsha="$(git rev-parse origin/dev 2>/dev/null | cut -c1-12 || true)"
if [ -n "$devsha" ] && [ "$verdict" = "PASS" ]; then
  # #1955. "Cleared for main" used to rest on the stamp's sha and verdict alone, which is weaker than what the release gate asks (the release-only layers of #1428, the stamp
  # as COMMITTED at dev's tip). So the banner asks the GATE: release-gate.sh is run, in a child, on the command that promotes dev's tip (`git push origin <sha>:main`), and what it
  # answers is what the banner says. One judgement, not a copy of it. QA_ALLOW_MAIN is unset for the child (an override must never read as "certified") and its deadline is cut
  # below this hook's 10 s timeout. Anything but a clear allow is NOT "cleared": the banner says the gate refuses, or that it could not be asked. The old test (the stamp's sha EQUAL to
  # origin/dev) is gone with the weaker evidence: a committed stamp is always a commit AFTER the one it certifies, so it was false for exactly the state the gate permits, and true only for a
  # stamp not yet committed, which the gate refuses. The gate's own sha binding decides.
  full="$(git rev-parse --verify -q origin/dev 2>/dev/null || true)"
  gate="${CLAUDE_PLUGIN_ROOT:-}/hooks/scripts/release-gate.sh"
  said=""; rc=1
  if [ -n "$full" ] && [ -f "$gate" ]; then
    said="$(printf '{"tool_input":{"command":"git push origin %s:main"}}' "$full" | env -u QA_ALLOW_MAIN RAILS_FLOW_HOOK_DEADLINE=6 /bin/bash -p "$gate" 2>&1 >/dev/null)"; rc=$?
  fi
  if [ "$rc" = 0 ] && printf '%s' "$said" | grep -q 'certification valid for'; then
    echo "- qa-flow: dev ($devsha) is CERTIFIED — the release gate's own check passes, cleared for main."
  elif [ "$rc" = 2 ]; then
    reason="$(printf '%s' "$said" | grep -m1 'BLOCKED by qa-flow release gate' | sed 's/^BLOCKED by qa-flow release gate: //' | cut -c1-240)"
    case "$reason" in
      "the gate took longer than "*) echo "- qa-flow: dev ($devsha) has a PASS stamp, but the release gate could not be judged in time, so \"cleared for main\" is not claimed — retry, or run /qa-flow:certify." ;;
      *) echo "- qa-flow: dev ($devsha) has a PASS stamp, but the release gate would refuse a promotion: ${reason:-no reason given}" ;;
    esac
  elif [ "$rc" = 0 ]; then
    echo "- qa-flow: dev ($devsha) has a PASS stamp; the release gate allowed it for another reason; certification not shown, so \"cleared for main\" is not claimed."
  else
    echo "- qa-flow: dev ($devsha) has a PASS stamp, but the release gate's check could not be run here (exit $rc), so \"cleared for main\" is not claimed — /qa-flow:certify or retry."
  fi
else
  echo "- qa-flow: certification stale (stamped ${csha:-none}, dev ${devsha:-?}) — re-run /qa-flow:certify before promoting."
fi
exit 0
