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

# Strip heredoc BODIES so their text is never read as a command (completes the #1
# residual). A body (<<EOF … EOF, incl. <<-EOF and quoted <<'EOF'/<<"EOF") is unquoted,
# so quote-stripping alone can't remove it; drop body + terminator lines, keep the
# command line that opens the heredoc. Here-strings (<<<) are left alone.
_strip_heredocs() {
  awk '
    inh {
      t=$0; if (dash) sub(/^\t+/,"",t)
      if (t==delim) inh=0
      next
    }
    {
      if (match($0, /<<-?[ \t]*["'\'']?[A-Za-z_][A-Za-z0-9_]*["'\'']?/)) {
        before=(RSTART>1)?substr($0,RSTART-1,1):""
        if (before != "<") {
          op=substr($0,RSTART,RLENGTH); dash=(op ~ /^<<-/)?1:0
          d=op; sub(/^<<-?[ \t]*/,"",d); gsub(/["'\'']/,"",d)
          delim=d; inh=1
        }
      }
      print
    }
  '
}

# Detect promotion to main/master. #1: match the INVOKED command, not any substring of
# the line. Drop heredoc bodies, strip quoted spans (commit messages, -m/--body, echo
# bodies), then require the pattern at the START of a command segment (split on ; | && ||).
# A commit/PR body/echo/heredoc that merely MENTIONS a merge/push no longer trips the gate.
seg="$(printf '%s' "$cmd" | _strip_heredocs | sed -E "s/'[^']*'//g; s/\"[^\"]*\"//g" | tr ';|&' '\n')"
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

verdict="$(python3 -c 'import json;print(json.load(open("qa/CERTIFICATION")).get("verdict",""))' 2>/dev/null || true)"
csha="$(python3 -c 'import json;print(json.load(open("qa/CERTIFICATION")).get("sha",""))' 2>/dev/null || true)"
[ "$verdict" = "PASS" ] || deny "certification verdict is not PASS. Re-certify."
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
