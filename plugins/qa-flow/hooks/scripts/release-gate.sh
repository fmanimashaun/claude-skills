#!/usr/bin/env bash
# PreToolUse[Bash] — block dev->main promotion unless QA certified the exact dev sha.
# Independent of rails-flow's guard; both can run. Exit 2 blocks with a reason.
set -uo pipefail
input="$(cat)"
# python3 is required to parse certification + tool input. BLOCKING gate → fail CLOSED
# if it's missing, but only when the command looks like a main-ward promotion.
if ! type -P python3 >/dev/null 2>&1; then
  # Word-boundary match on main/master as whole refs (not substrings like
  # "maintenance"), mirroring the promotion detection below. Fail CLOSED only for a
  # real promotion; stay out of the way otherwise.
  _looks_promotion=0
  printf '%s' "$input" | grep -qE 'git[[:space:]]+push\b.*\b(origin[[:space:]]+)?(HEAD:)?(main|master)\b' && _looks_promotion=1
  printf '%s' "$input" | grep -qE 'git[[:space:]]+merge\b'   && _looks_promotion=1
  printf '%s' "$input" | grep -qE 'gh[[:space:]]+pr[[:space:]]+merge\b' && _looks_promotion=1
  if [ "$_looks_promotion" = "1" ]; then
    [ "${QA_ALLOW_MAIN:-0}" = "1" ] && { echo "qa-flow: python3 missing but QA_ALLOW_MAIN=1 — allowed (audited)." >&2; exit 0; }
    echo "BLOCKED by qa-flow release gate: python3 not found — cannot verify certification. Install python3 (on Windows, run Claude Code in WSL/Git Bash), or set QA_ALLOW_MAIN=1 to override." >&2
    exit 2
  fi
  exit 0
fi
cmd="$(printf '%s' "$input" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("tool_input",{}).get("command",""))' 2>/dev/null || printf '%s' "$input")"

# --- Normalize the command so promotion detection can't be fooled (must fail CLOSED) ---
# One normaliser, shared with rails-flow's guard-bash.sh: `lib/normalize_cmd.sh` beside this script
# (plugins install alone, so each ships a copy; the maintainer lint `hook-lib-drift` keeps the two
# byte-identical, #906). It strips quoted spans, comments and heredoc bodies, splits on ; | && ||
# and newlines, and peels env/sudo/git-global-option prefixes, so the verb is at the START of a
# segment. FAIL CLOSED if the lib is missing: match the raw text, as before #3/#7/#48.
_lib="$(dirname "${BASH_SOURCE[0]}")/lib/normalize_cmd.sh"
if [ -f "$_lib" ] && . "$_lib" 2>/dev/null && type normalize_segments >/dev/null 2>&1; then
  seg="$(printf '%s' "$cmd" | normalize_segments)"
else
  seg="$cmd"
fi
push_seg=0; merge_seg=0; ghmerge_seg=0
printf '%s\n' "$seg" | grep -qE '^[[:space:]]*git[[:space:]]+push\b.*\b(origin[[:space:]]+)?(HEAD:)?(main|master)\b' && push_seg=1
printf '%s\n' "$seg" | grep -qE '^[[:space:]]*git[[:space:]]+merge\b' && merge_seg=1
printf '%s\n' "$seg" | grep -qE '^[[:space:]]*gh[[:space:]]+pr[[:space:]]+merge\b' && ghmerge_seg=1

targets_main=0
[ "$push_seg" = 1 ] && targets_main=1
[ "$merge_seg" = 1 ] && git rev-parse --abbrev-ref HEAD 2>/dev/null | grep -qE '^(main|master)$' && targets_main=1
# gh pr merge: base is the PR's target. Handle explicit number AND bare (current branch).
if [ "$ghmerge_seg" = 1 ]; then
  # a bare integer arg (from the cleaned command) = PR number; else current branch's PR
  num="$(printf '%s' "$seg" | grep -oE '(^|[[:space:]])[0-9]+([[:space:]]|$)' | tr -d ' ' | head -1)"
  if [ -n "$num" ]; then
    base="$(gh pr view "$num" --json baseRefName -q .baseRefName 2>/dev/null || true)"
  else
    base="$(gh pr view --json baseRefName -q .baseRefName 2>/dev/null || true)"
  fi
  case "$base" in main|master) targets_main=1 ;; esac
  # If we couldn't resolve the base at all on a merge command, fail safe: treat as promotion.
  [ -z "$base" ] && targets_main=1
fi
[ "$targets_main" -eq 1 ] || exit 0

deny() { echo "BLOCKED by qa-flow release gate: $1" >&2; exit 2; }
[ "${QA_ALLOW_MAIN:-0}" = "1" ] && { echo "qa-flow: QA_ALLOW_MAIN=1 override — promotion allowed without a fresh stamp (audited)." >&2; exit 0; }

stamp="qa/CERTIFICATION"
[ -f "$stamp" ] || deny "no certification found. Run /qa-flow:certify against staging first."

# #721. One reader, shared with qa-status.sh. Four inline `json.load` copies lived here and there,
# kept in step by nothing -- the shape of #699, where two copies of an extractor meant a bug survived
# its own discovery because only one got fixed.
#
# It also has to say WHAT is wrong. A live project sat permanently denied with "certification verdict
# is not PASS" when the file was not JSON at all: json.load raised, `|| true` swallowed it, and the
# gate named the wrong problem. Re-certifying does not replace a hand-written stamp, so the reader
# re-certified and the loop closed. A gate that misdiagnoses is worse than one that merely blocks.
#
# Fail-closed is unchanged: `|| true` still swallows a missing python3 or a missing script, an empty
# value still denies, and this whole block is still reached only for a command targeting `main`.
reader="${CLAUDE_PLUGIN_ROOT:-}/scripts/read_certification.py"
verdict="$(python3 "$reader" --field verdict 2>/dev/null || true)"
csha="$(python3 "$reader" --field sha 2>/dev/null || true)"
# TWO conditions, not one, because they need different sentences. Empty means the stamp could not
# be READ -- ask the reader why. Non-empty but not PASS means the stamp is fine and the verdict is
# genuinely negative; the reader has nothing to add, and calling --explain there produced the useless
# "the stamp is readable and verdict is set" while denying the promotion. Caught by running it.
if [ -z "$verdict" ]; then
  why="$(python3 "$reader" --field verdict --explain 2>/dev/null || true)"
  # A gate must still deny when it cannot explain itself.
  deny "${why:-certification verdict could not be read. Re-certify.}"
elif [ "$verdict" != "PASS" ]; then
  deny "certification verdict is ${verdict}, not PASS. Fix the defects and re-certify."
fi

# #2: the sha binding IS the gate — empty/garbled sha must fail closed, not pass on PASS alone.
[ -n "$csha" ] || deny "certification has no sha — the stamp is invalid. Re-run /qa-flow:certify."

devsha="$(git rev-parse origin/dev 2>/dev/null || git rev-parse dev 2>/dev/null || true)"
if [ -n "$devsha" ]; then
  case "$devsha" in
    "$csha"*) : ;;
    *) deny "certification is for sha ${csha:0:12}, but dev is at ${devsha:0:12}. dev moved — re-certify before promoting." ;;
  esac
else
  deny "cannot resolve dev sha to compare against the certification. Fetch dev and retry."
fi
echo "qa-flow: certification valid for ${csha:0:12} — promotion permitted." >&2
exit 0
