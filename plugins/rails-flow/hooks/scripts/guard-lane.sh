#!/usr/bin/env bash
# PreToolUse[Edit|Write|MultiEdit] — refuse a write outside an ASSIGNED lane. #660
#
# `parallel-session-lane` §1 says "Work only inside the worktree you were assigned" and nothing made
# it true. An agent that skipped §1 produced a clean-looking branch in the wrong worktree, silently,
# while another session was working there — and nothing said so until a human read a diff that did
# not belong.
#
# SCOPED TO AN ASSIGNED LANE, AND DORMANT OTHERWISE. With no lane assigned this exits 0 without
# looking at anything: a single-session run must not pay for a multi-session feature. That is the
# same distinction release-gate.sh draws — fail closed for the command it guards, 0 for everything
# else — because a guard that fired on ordinary work would be switched off, and then the protocol
# has nothing behind it at all.
#
# READS ARE NOT POLICED. §1 also says do not diff other branches; refusing reads would break
# legitimate context-gathering, and that over-reach is how a hook gets disabled.
#
# FAILS CLOSED. If python3 is missing the payload is scanned raw, so the path still matches.
set -uo pipefail

# The lane is assigned by whatever launched this session. No lane, no opinion.
lane="${RAILS_FLOW_LANE:-}"
[ -n "$lane" ] || exit 0

input="$(cat)"
path="$(printf '%s' "$input" \
  | python3 -c 'import json,sys
d=json.load(sys.stdin).get("tool_input",{})
print(d.get("file_path") or d.get("path") or "")' 2>/dev/null || printf '%s' "$input")"
[ -n "$path" ] || exit 0

# NORMALISE BOTH SIDES, then compare. A lane of `app/models` and a path of `./app/models/x.rb` are
# the same place, and a plain string-prefix test calls them different -- which the first version of
# this guard did, blocking a write that was inside its own lane. Found by running it, not by reading
# it: the comment already claimed both sides were resolved.
#
# Done in pure shell because this hook must fail CLOSED when python3 is absent; a normaliser that
# needed python3 would take the whole guard with it.
_norm() {
  local v="$1"
  case "$v" in /*) ;; *) v="$PWD/$v" ;; esac
  while :; do
    case "$v" in
      */./*) v="${v%%/./*}/${v#*/./}" ;;
      ./*)   v="${v#./}" ;;
      */)    v="${v%/}" ;;
      *)     break ;;
    esac
  done
  printf '%s' "$v"
}
# `..` IS REFUSED, NOT RESOLVED (#823). `_norm` collapses `/./` but a parent segment needs real
# path arithmetic, and `app/models/../../config/routes.rb` walked straight past the prefix match
# below -- a one-segment hole in a fail-closed guard. Refusing keeps this pure shell (python3 may
# be absent) and costs nothing: no legitimate write names its target through `..`; the only reason
# to is to leave the lane.
case "/$path/" in
  */../*)
    {
      echo "BLOCKED by rails-flow lane guard: a path containing '..' is refused while a lane is"
      echo "assigned (lane: $lane). Name the file by its plain path instead."
    } >&2
    exit 2 ;;
esac

abs="$(_norm "$path")"
lane_abs="$(_norm "$lane")"

case "$abs" in
  "$lane_abs"|"$lane_abs"/*) exit 0 ;;
esac

{
  echo "BLOCKED by rails-flow lane guard: this session is assigned the lane"
  echo "  $lane"
  echo "and the write targets"
  echo "  $path"
  echo
  echo "Another session may be working there. parallel-session-lane §1: work only inside the"
  echo "worktree you were assigned. If the lane is wrong, change RAILS_FLOW_LANE deliberately —"
  echo "do not widen it to make one write pass."
} >&2
exit 2
