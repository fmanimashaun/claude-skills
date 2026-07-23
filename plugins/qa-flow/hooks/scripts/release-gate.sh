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
# Order matters:
#  1. Un-quote heredoc delimiters (<<'EOF'/<<"EOF" -> <<EOF) so a REAL quoted-delimiter
#     heredoc survives the quote-strip below, while a <<EOF that lives only inside a quote
#     (echo "<<EOF") or a comment (# <<EOF) does NOT survive and can't be read as an opener.
#  2. Strip quoted spans, THEN comments — quotes first so a '#' inside a string
#     (e.g. -m "fix #43") is already removed and never mis-cut as a comment (which would
#     drop a later `git push origin main` on the same line → fail OPEN).
#  3. Strip heredoc BODIES (unquoted text that quote-stripping can't remove).
# Here-strings (<<<) are intentionally left alone.
_unquote_delims() { sed -E "s/<<(-?)[[:space:]]*[\"']([A-Za-z0-9_][A-Za-z0-9_-]*)[\"']/<<\1\2/g"; }
_strip_quotes()   { sed -E "s/'[^']*'//g; s/\"[^\"]*\"//g"; }
_strip_comments() { sed -E "s/^[[:space:]]*#.*\$//; s/([[:space:]])#.*\$/\1/"; }
_strip_heredocs() {
  awk '
    inh { t=$0; if (dash) sub(/^\t+/,"",t); if (t==delim) inh=0; next }
    {
      if (match($0, /<<-?[ \t]*[A-Za-z0-9_][A-Za-z0-9_-]*/)) {
        before=(RSTART>1)?substr($0,RSTART-1,1):""
        if (before != "<") {
          op=substr($0,RSTART,RLENGTH); dash=(op ~ /^<<-/)?1:0
          d=op; sub(/^<<-?[ \t]*/,"",d)
          delim=d; inh=1
        }
      }
      print
    }
  '
}

# Detect promotion to main/master. Match the INVOKED command, not any substring: split on
# ; | && || then require the verb at the START of a segment. Also peel leading
# env-assignments, sudo/env, and git global options (-C, -c, --git-dir, ...) so prefixed
# promotions (FOO=1 git push …, sudo git push …, git -C repo push origin main) are caught.
clean="$(printf '%s' "$cmd" | _unquote_delims | _strip_quotes | _strip_comments | _strip_heredocs)"
seg="$(printf '%s' "$clean" | tr ';|&' '\n' \
  | sed -E 's/^[[:space:]]+//' \
  | sed -E 's/^(([A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*)[[:space:]]+)+//' \
  | sed -E 's/^(sudo|env)[[:space:]]+//' \
  | sed -E 's/^(([A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*)[[:space:]]+)+//' \
  | sed -E 's/^git[[:space:]]+((-C|-c|--git-dir|--work-tree|--namespace|--exec-path)([[:space:]]*=?[[:space:]]*[^[:space:]]+)?[[:space:]]+)+/git /')"
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
