#!/usr/bin/env bash
# SessionStart — inject repo state as context (stdout becomes context).
set -uo pipefail
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0

branch="$(git branch --show-current 2>/dev/null)"
dirty="$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
last="$(git log -1 --oneline 2>/dev/null)"
base="main"; git show-ref --verify --quiet refs/heads/dev && base="dev"

echo "## rails-flow session context"
echo "- branch: ${branch:-detached} (base: $base) | uncommitted files: $dirty"
echo "- last commit: $last"
[ -f CLAUDE.md ] || echo "- NOTE: no CLAUDE.md — run /rails-flow:setup-flow to scaffold project conventions."
[ -f GUARDRAILS.md ] || echo "- NOTE: no GUARDRAILS.md — run /rails-flow:setup-flow."
if [ -f docs/brain/STATUS.md ]; then
  echo "- brain STATUS (docs/brain/STATUS.md, top):"
  head -8 docs/brain/STATUS.md | sed 's/^/  /'
fi
if [ -f docs/brain/MEMORY.md ]; then
  echo "- memory index (docs/brain/MEMORY.md):"
  head -12 docs/brain/MEMORY.md | sed 's/^/  /'
fi

# brain-review cadence nudge (local, offline). /rails-flow:brain-review stamps an epoch into
# docs/brain/.last-review; if the last sweep is older than the cadence (default 7d, override
# RAILS_FLOW_BRAIN_REVIEW_DAYS), remind. Reminder only — never auto-runs. Fails open.
if [ -f docs/brain/STATUS.md ]; then
  _days="${RAILS_FLOW_BRAIN_REVIEW_DAYS:-7}"
  if [ -f docs/brain/.last-review ]; then
    _ts="$(tr -dc 0-9 < docs/brain/.last-review 2>/dev/null)"
    if [ -n "$_ts" ]; then
      _age=$(( ( $(date +%s) - _ts ) / 86400 ))
      [ "$_age" -ge "$_days" ] && echo "- brain-review due: last swept ${_age}d ago (cadence ${_days}d) — run /rails-flow:brain-review"
    fi
  else
    echo "- brain-review: no sweep on record — run /rails-flow:brain-review to start the maintenance cadence"
  fi
fi

# Issue→fix discipline advisory (fail-open, informational only). If this branch carries several
# fix-shaped commits and neither the branch name nor any commit references an issue, it's a decent
# proxy for ad-hoc hot-fixing outside the file→/rails-flow:fix loop. Never blocks.
if [ -n "${branch:-}" ] && [ "$branch" != "main" ] && [ "$branch" != "dev" ]; then
  _range="$(git merge-base "$base" HEAD 2>/dev/null)"
  if [ -n "$_range" ]; then
    _fixish="$(git log --format=%s "$_range..HEAD" 2>/dev/null | grep -ciE '^(fix|bug|hotfix)' || true)"
    _refs="$(git log --format='%s %b' "$_range..HEAD" 2>/dev/null | grep -coE '#[0-9]+' || true)"
    case "$branch" in *[0-9]*) _refs=$((_refs+1)) ;; esac   # branch names like fix/issue-42-*
    if [ "${_fixish:-0}" -ge 2 ] && [ "${_refs:-0}" -eq 0 ]; then
      echo "- advisory: ${_fixish} fix-shaped commits on '$branch' with no issue reference — defects are meant to be FILED then worked one-at-a-time (/rails-flow:fix · /rails-flow:issues), not stacked on one branch."
    fi
  fi
fi

if [ -f .claude/skills/.manifest.tsv ]; then
  # THREE outcomes per row, not two: matches, drifted, or COULD NOT BE HASHED. The last one used
  # to be silently folded into "matches" -- the row was skipped by a `[ -n "$cur" ] &&` guard, so a
  # machine that could not hash counted zero drift and printed nothing, indistinguishable from a
  # clean tree while the rest of this hook ran normally and made the session look healthy. A check
  # that did not run is not a pass.
  #
  # Counting unhashable rows -- rather than probing for the tool up front -- is deliberate. A
  # `command -v` probe answers "is it installed", and the failure that actually matters is "did
  # this row hash", which also covers a hasher that is present and broken. The probe below only
  # PICKS a command; it is never the thing that decides the verdict.
  #
  # `sha256sum` is GNU coreutils and NOT POSIX -- the same portability point the cksum note below
  # already makes about this very hook. Apple began shipping /sbin/sha256sum only recently; macOS
  # has always had `shasum`, whose `-a 256` output is byte-identical in the field `cut` reads.
  _rf_hash="sha256sum"
  command -v sha256sum >/dev/null 2>&1 || _rf_hash="shasum -a 256"
  stale=0
  unhashed=0
  while IFS="$(printf '\t')" read -r src hash; do
    [ -n "$src" ] && [ -f "$src" ] || continue
    # Deliberately unquoted: $_rf_hash may carry the `-a 256` argument and must word-split.
    # shellcheck disable=SC2086
    cur="$($_rf_hash "$src" 2>/dev/null | cut -c1-12)"
    if [ -z "$cur" ]; then
      unhashed=$((unhashed+1))
    elif [ "$cur" != "$hash" ]; then
      stale=$((stale+1))
    fi
  done < .claude/skills/.manifest.tsv
  [ "$stale" -gt 0 ] && echo "- $stale curated doc(s) drifted from their project skills — run /rails-flow:curate"
  [ "$unhashed" -gt 0 ] && echo "- $unhashed curated doc(s) could NOT be hashed (no working sha256sum or shasum) — drift is UNKNOWN for them, not clean"
fi

# ---------------------------------------------------------------------------------------
# #723 — UNLANED CONCURRENCY. The lane guard (#660) is dormant unless RAILS_FLOW_LANE is set,
# and `assign_lanes.py` (#661) has to be run BEFORE the sessions open. So the coordination
# protocol was built, shipped, and never activated: activation depended on a human remembering.
#
# What that cost, observed in one working directory with four unlaned sessions: one session's
# `git checkout -b` switched another's branch out from under it mid-work; uncommitted work from
# several sessions piled into one tree; and the Stop gate failed one session's turn over ANOTHER
# session's red specs, because it evaluates one tree it assumes belongs to one session.
#
# DETECTION IS BY MARKER, NOT BY PROCESS INTROSPECTION. Each session start drops a marker keyed
# by this working directory, under TMPDIR — never inside the repo, because a status hook must not
# write to someone's tree. Liveness is `kill -0` on the recorded PPID (the process that spawned
# this hook), so dead sessions prune themselves.
#
# IT UNDER-DETECTS ON PURPOSE. If PPID is not the session process, or a peer started before this
# mechanism shipped, we simply say nothing. A false nudge on ordinary single-session work is how
# an advisory gets ignored, and this whole feature exists because an advisory nobody acts on is
# worth nothing. Missing a case costs a reminder; crying wolf costs the channel.
#
# Advisory, and fails open at every step: no lane, no TMPDIR, no marker dir — all exit quietly.
# ---------------------------------------------------------------------------------------
if [ -z "${RAILS_FLOW_LANE:-}" ]; then
  _rf_sess_dir="${TMPDIR:-/tmp}/rails-flow-sessions"
  if mkdir -p "$_rf_sess_dir" 2>/dev/null; then
    # cksum, not sha256sum: it is in POSIX and present everywhere this hook runs.
    _rf_key="$(printf '%s' "$PWD" | cksum 2>/dev/null | tr -cd '0-9')"
    if [ -n "$_rf_key" ]; then
      _rf_f="$_rf_sess_dir/$_rf_key"
      _rf_live=""
      _rf_n=0
      if [ -f "$_rf_f" ]; then
        while IFS= read -r _rf_pid; do
          case "$_rf_pid" in ''|*[!0-9]*) continue ;; esac
          [ "$_rf_pid" = "$PPID" ] && continue          # do not count a previous run of ourselves
          if kill -0 "$_rf_pid" 2>/dev/null; then
            _rf_live="${_rf_live}${_rf_pid}
"
            _rf_n=$((_rf_n+1))
          fi
        done < "$_rf_f"
      fi
      printf '%s%s\n' "$_rf_live" "$PPID" > "$_rf_f" 2>/dev/null || true
      if [ "$_rf_n" -gt 0 ]; then
        _rf_total=$((_rf_n+1))
        echo "- rails-flow: ${_rf_total} sessions share this working directory and NONE has a lane assigned."
        echo "  Unlaned, they will collide: one session's branch switch moves another's HEAD, uncommitted"
        echo "  work from several sessions piles into one tree, and the Stop gate judges one session by"
        echo "  another's red specs. The lane guard is dormant without RAILS_FLOW_LANE."
        echo "  Run: python3 \"\${CLAUDE_PLUGIN_ROOT}/scripts/assign_lanes.py\" <subtree> <subtree>"
        echo "  then relaunch each session in its own worktree with RAILS_FLOW_LANE set."
      fi
    fi
  fi
fi

exit 0
