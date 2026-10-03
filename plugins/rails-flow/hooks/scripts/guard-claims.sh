#!/usr/bin/env bash
# PreToolUse[Bash] — a PR body that makes numeric claims must have had them checked (#1106).
#
# WHY A HOOK AND NOT DOCTRINE. `claim-verifier` exists, works, covers "any number: counts, ratios,
# versions, timings", and is named in /maintainer-work. It was skipped for an entire working day
# without anyone noticing, and two wrong numbers reached merged PR bodies -- "292 assertions, up
# from 285" (it was 292 before AND after) and "ten times in this release's own bullets" (2 here, 8
# in older published entries). The capability was never the gap. Remembering to use it was.
#
# The only things that changed behaviour that day were the ones that ran without being remembered:
# the duplicate-unreleased rule, the ci-verdict rule, and guard-bash.sh. So this is a wall, not a
# checklist item.
#
# SCOPED TO DURABLE CLAIMS SOMEONE ELSE READS: `gh pr create` / `gh pr edit` / `gh issue comment`
# carrying a body. It cannot misfire on ordinary work, which is what keeps a fail-closed guard from
# being switched off.
#
# `issue comment` WAS THE HOLE. This guard is the only thing that has ever actually stopped a wrong
# number here -- it fired on a PR body carrying eight unverified claims and every one was re-measured
# before the PR opened. On the same day, four issue comments went out carrying counts, and not one
# passed through this check, because the guard watched PRs alone. An issue comment is the same
# artifact: durable, read by someone else, quoted onward. The numbers in it get the same wall.
#
# It is the CONSEQUENCE that is gated, not the cause. A grep with a typo returns empty and an empty
# result is a valid answer, so no hook can tell a broken query from a true negative. What a hook CAN
# see is the moment that output becomes a claim in something another person reads.
#
# Exit 2 blocks the command; stderr is shown to Claude with the reason.
set -uo pipefail
input="$(cat)"

cmd="$(printf '%s' "$input" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("tool_input",{}).get("command",""))' 2>/dev/null || printf '%s' "$input")"

# Not a claim-carrying command -- nothing to say. This is the common case and it must be silent.
printf '%s' "$cmd" | grep -qE '\bgh[[:space:]]+(pr[[:space:]]+(create|edit)|issue[[:space:]]+comment)\b' || exit 0
printf '%s' "$cmd" | grep -qE '(--body-file|--body)\b' || exit 0

# The audited escape. A fail-closed guard with no visible way past it gets disabled the first time
# it is wrong about something, and then it protects nothing.
if [ "${RAILS_FLOW_CLAIMS_OK:-0}" = "1" ]; then
  echo "rails-flow: RAILS_FLOW_CLAIMS_OK=1 — claim check skipped (audited)." >&2
  exit 0
fi

# WHERE THE COMMAND RUNS (#1509). This hook runs in the SESSION's directory, and the command may not:
# `cd ~/projects/other && gh pr create --body-file body.md` was judged against the session repo's
# template and would read a relative body from the session directory. `lib/command_cwd.py` follows the
# command's own `cd`s, in one simple grammar only (an allowlist); exit 3 means it cannot tell, so the
# template is NOT checked rather than checked against the wrong repository, and a relative body is not read
# from the wrong place. Allowed, loudly: the maintainer's decision on #1509.
# It starts from the payload's `cwd` (the session's working directory), not this process's.
cwd_lib="$(dirname "$0")/lib/command_cwd.py"
start="$(printf '%s' "$input" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("cwd",""))' 2>/dev/null)"
cmd_cwd="$(printf '%s' "$cmd" | python3 "$cwd_lib" "$start" 2>/dev/null)"; cwd_rc=$?
# A resolver that is missing or crashed has resolved nothing, and the session directory is not a safe
# default: FAIL CLOSED, here, before a relative body path fails OPEN below (as #1435 ruled for
# pr_template.py). Only with python3 itself absent are the older paths left to decide.
if [ "$cwd_rc" -ne 0 ] && [ "$cwd_rc" -ne 3 ] && command -v python3 >/dev/null 2>&1; then
  echo "BLOCKED by rails-flow claim guard: the command's directory could not be resolved (lib/command_cwd.py missing or exited $cwd_rc), so the body was not judged." >&2
  echo "Fix it, or ship deliberately unchecked: RAILS_FLOW_CLAIMS_OK=1 (audited)." >&2
  exit 2
fi
# The repository the command runs in: the PR template and the skills/** change-type check read it.
if [ "$cwd_rc" -eq 0 ] && [ -n "$cmd_cwd" ]; then
  root="$(git -C "$cmd_cwd" rev-parse --show-toplevel 2>/dev/null || printf '%s' "$cmd_cwd")"
else
  root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
fi

body=""
if printf '%s' "$cmd" | grep -qE '\-\-body-file\b'; then
  # A separator (`;`, `&`, `|`, `)`) ends the path: `--body-file b.md; fi` names b.md (#1509 review).
  body="$(printf '%s' "$cmd" | sed -nE 's/.*--body-file[[:space:]]+"?([^";&|)[:space:]]+)"?.*/\1/p' | head -1)"
fi
if [ -n "$body" ] && [ "${body#/}" = "$body" ]; then
  # Exit 3: the body's directory is unknown, so it is not read from the wrong one. (A crash has
  # already BLOCKED above; with no python3 the path is left alone and the template check FAILS CLOSED.)
  if [ "$cwd_rc" -eq 0 ] && [ -n "$cmd_cwd" ]; then
    body="$cmd_cwd/$body"
  elif [ "$cwd_rc" -eq 3 ]; then
    # Said here, because the fail-open below would otherwise be the only message (#1516 review, S-a).
    echo "rails-flow: the body, the PR template and the change type NOT checked (the directory gh runs in could not be resolved, so the relative --body-file cannot be located)." >&2
    body=""
  fi
fi
# No readable body file (inline --body, a heredoc, a path we cannot resolve): say so and allow.
# FAILING OPEN HERE IS DELIBERATE -- this guard's job is to make the check happen when it can, not
# to become an obstacle to opening a PR. It is loud about what it could not read.
if [ -z "$body" ] || [ ! -r "$body" ]; then
  echo "rails-flow: could not read a --body-file to check claims; verify any numbers by hand." >&2
  exit 0
fi

# ---------------------------------------------------------------------------------------------
# THE REPO'S OWN PR TEMPLATE (#1389). A downstream pr-reviewer BLOCKED 5 of 5 PRs in a day for the
# same finding -- the body lacked the template's sections -- and 3 had merged without them. The rule
# was prose, followed 0 times in 5. Its sections are read from the template, never hardcoded; a
# section the template marks conditional ('If ...', 'Optional', '(optional)', '(if ...)') may be left
# out; a section that does not apply stays and says N/A. PR bodies only: an issue comment has no template. Dormant with no template.
if printf '%s' "$cmd" | grep -qE '\bgh[[:space:]]+pr[[:space:]]+(create|edit)\b'; then
  tpl_lib="$(dirname "$0")/lib/pr_template.py"
  # Exit status, not stdout alone: 0 is clean, 1 names the missing sections, and anything else (a
  # crash, a missing helper or python3) is said out loud. Reading only stdout let a crash pass
  # silently through a fail-closed hook (pre-release review of #1398).
  # `-R/--repo` targets another repository, whose template this checkout does not have: say so rather
  # than judge the body against the wrong template (pre-release review of #1398).
  # Only the `gh pr create|edit` segment's own flags: an unrelated `grep -R` earlier in the chain, or
  # an `-R` inside a heredoc body, must not switch the check off (second pre-release review).
  # Quoted strings are removed first, so `-R` or a `|` inside `--title '…'` is text, not a flag or a
  # pipe (third pre-release review). GH_REPO, and every other GIT_*/GH_* variable, is lib/command_cwd.py's
  # class rule (#1516, round 6): set on the command or inherited, it gives the NOT-checked notice there.
  # One left-to-right scan, so `"it's"`, an escaped `\"` and a quote inside the other kind are read as
  # the shell reads them (#1435). A sed pair stripped '…' first and mis-paired `"it's -R"`. No python3
  # here means an empty result, and the helper check below then BLOCKS for the same missing python3.
  unquoted="$(printf '%s' "$cmd" | python3 -c '
import sys
s, out, q, i = sys.stdin.read(), [], "", 0
while i < len(s):
    c = s[i]
    if not q:
        if c in "\x27\"":
            q = c
        else:
            out.append(c)
    elif q == "\"" and c == "\\":
        i += 1
    elif c == q:
        q = ""
    i += 1
sys.stdout.write("".join(out))
' 2>/dev/null)"
  pr_seg="$(printf '%s' "$unquoted" | grep -oE 'gh[[:space:]]+pr[[:space:]]+(create|edit)[^;&|]*' | head -1)"
  if printf '%s' "$pr_seg" | grep -qE '(^|[[:space:]])(-R|--repo)'; then
    echo "rails-flow: PR-template sections NOT checked (-R/--repo targets another repository's template)." >&2
  elif [ ! -f "$tpl_lib" ] || ! command -v python3 >/dev/null 2>&1; then
    # FAIL CLOSED (owner decision on #1435): this is a gate, and a gate whose checker is missing has
    # not checked anything. The audited escape stays.
    echo "BLOCKED by rails-flow claim guard: the PR-template check cannot run (lib/pr_template.py or python3 unavailable)." >&2
    echo "Fix the install, or ship deliberately unchecked: RAILS_FLOW_CLAIMS_OK=1 (audited)." >&2
    exit 2
  elif [ "$cwd_rc" -eq 3 ]; then
    # The directory gh runs in is unknown, so the template it would judge against is too. Say so (#1509).
    echo "rails-flow: PR-template sections NOT checked (the directory gh runs in could not be resolved, so the target repository is unknown)." >&2
  else
    gaps="$(python3 "$tpl_lib" "$root" "$body" 2>/dev/null)"; tpl_rc=$?
    # pr_template.py exits 1 ONLY with the missing sections listed; any failure to judge is exit 3.
    if [ "$tpl_rc" -ne 0 ] && [ "$tpl_rc" -ne 1 ]; then
      echo "BLOCKED by rails-flow claim guard: the PR-template check crashed (pr_template.py exited $tpl_rc), so the body was not judged." >&2
      echo "Fix it, or ship deliberately unchecked: RAILS_FLOW_CLAIMS_OK=1 (audited)." >&2
      exit 2
    elif [ "$tpl_rc" -eq 1 ] && [ -z "$gaps" ]; then
      # Exit 1 with nothing listed is not a verdict: the helper died before main() (an ImportError, a
      # SyntaxError from a broken edit, a python3 too old for it). FAIL CLOSED (#1435).
      echo "BLOCKED by rails-flow claim guard: the PR-template check died before judging (exit 1, no sections listed)." >&2
      echo "Fix it, or ship deliberately unchecked: RAILS_FLOW_CLAIMS_OK=1 (audited)." >&2
      exit 2
    elif [ "$tpl_rc" -eq 1 ]; then
      echo "BLOCKED by rails-flow claim guard: this PR body is missing section(s) the repo's PR template requires:" >&2
      printf '%s\n' "$gaps" | sed 's/^/  ## /' >&2
      echo "" >&2
      echo "Add each one. A section that does not apply stays, saying N/A and why; only a section the template marks conditional ('## If ...', '(optional)', '(if ...)') may be left out." >&2
      echo "Deliberately shipping without them: RAILS_FLOW_CLAIMS_OK=1 (audited)." >&2
      exit 2
    fi
  fi
fi

extract="${CLAUDE_PLUGIN_ROOT:-}/scripts/extract_claims.py"
if [ ! -f "$extract" ] || ! command -v python3 >/dev/null 2>&1; then
  echo "rails-flow: extract_claims.py or python3 unavailable — claims NOT checked." >&2
  exit 0
fi

# ---------------------------------------------------------------------------------------------
# THE CHANGE-TYPE DECLARATION (doctrine-map's one tracked gap).
#
# CLAUDE.md: "State which kind of change you are making, in the PR, before editing. Silence is not
# exemption." The doctrine map carried this as a GAP with its reason spelled out -- "mechanisable
# in principle ... but it would live in CI against the PR body, WHICH NO GATE IN THIS REPO READS."
# This hook reads the PR body, so that blocker is gone.
#
# Scoped to a PR that touches `skills/**`, because that is where the rule bites: skills are doctrine
# other people's agents follow verbatim, and a framework claim carried through unverified is the
# defect the whole gate exists for.
# Read in the repository the command RUNS in, not the session's (#1509 review): a session with a staged
# skills/ file was blocking a `cd <other repo> && gh pr create` that touches nothing there. With the
# directory unresolved (exit 3) the target is unknown, so this check says NOT checked rather than guess.
if [ "$cwd_rc" -eq 3 ]; then
  echo "rails-flow: change-type declaration NOT checked (the directory gh runs in could not be resolved)." >&2
elif git -C "$root" diff --name-only HEAD 2>/dev/null | grep -q '^skills/' || \
   git -C "$root" diff --name-only --cached HEAD 2>/dev/null | grep -q '^skills/'; then
  if ! grep -qiE 'framework claim|architecture decision|change type|our own (design|doctrine|architecture)' "$body"; then
    echo "BLOCKED by rails-flow claim guard: this PR touches skills/** and names no CHANGE TYPE." >&2
    echo "" >&2
    echo "Say which it is, in the body, before editing doctrine:" >&2
    echo "  * a FRAMEWORK CLAIM      -> needs a doctrine-verifier verdict and a citation" >&2
    echo "  * an ARCHITECTURE DECISION -> needs the maintainer's decision recorded on the issue" >&2
    echo "Silence is not exemption, and a mixed change must be split (CLAUDE.md, The gate)." >&2
    echo "Deliberately shipping without one: RAILS_FLOW_CLAIMS_OK=1 (audited)." >&2
    exit 2
  fi
fi

claims="$(python3 "$extract" "$body" 2>/dev/null)" || exit 0
n="$(printf '%s' "$claims" | sed -nE 's/^([0-9]+) load-bearing claim.*/\1/p' | head -1)"
[ -n "${n:-}" ] && [ "$n" -gt 0 ] 2>/dev/null || exit 0

# A body that already shows its working is what we are asking for, so recognise it and stand aside.
if grep -qiE 'verified against|re-verified|measured [a-z]*[[:space:]]*(on|against)|CONFIRMED' "$body"; then
  exit 0
fi

echo "BLOCKED by rails-flow claim guard: this PR body makes ${n} load-bearing claim(s) and shows no evidence any were checked." >&2
echo "" >&2
printf '%s\n' "$claims" >&2
echo "" >&2
echo "Run each one down, then say so in the body — 'verified against <tag>', 'measured 2026-..-..', or CONFIRMED." >&2
echo "Two wrong numbers reached merged PR bodies the day this guard was written; both would have been caught here (#1106)." >&2
echo "Deliberately shipping an unchecked body: RAILS_FLOW_CLAIMS_OK=1 (audited)." >&2
exit 2
