#!/usr/bin/env bash
# PreToolUse[Bash] — block dev->main promotion unless QA certified the exact dev sha.
# Independent of rails-flow's guard; both can run. Exit 2 blocks with a reason.
set -uo pipefail
# The whole payload, read with a BUILTIN: `cat` missing would leave it empty, and an empty command
# is never a promotion -- a fail-open (#1437 review, round 3).
IFS= read -r -d '' input || true
# python3, git, and the text tools the normaliser and the promotion detection use are all REQUIRED.
# BLOCKING gate -> fail CLOSED when any is missing, but only for a command that looks like a
# main-ward promotion. The fallback below uses bash builtins ONLY ([[ =~ ]], no grep): "grep:
# command not found" reads as a non-match, which is exactly how a fallback fails open.
_missing=""
for _t in python3 git sed awk tr grep head; do
  type -P "$_t" >/dev/null 2>&1 || _missing="$_missing $_t"
done
if [ -n "$_missing" ]; then
  # Judged with builtins, and deliberately COARSER than the full detection below, because it cannot
  # parse the JSON or run the normaliser: it must not be steerable by syntax it cannot see (#1437
  # round 3). JSON whitespace escapes (\t, \n, \u0009, ...) become spaces first, so an escaped tab
  # is whitespace. Then it looks for the WORDS, anywhere, with anything between them -- so git's
  # global options (`git -C . push`, `git -c k=v push`) cannot hide the verb. It over-blocks in a
  # degraded environment (a message that merely mentions `git push … main` is denied), which is the
  # safe direction for a gate that cannot tell. A ref under a path (`feature/main`) is not `main` --
  # except the fully qualified `refs/heads/main`, which is exactly main (#1437 round 4).
  _in="$input"
  for _esc in '\t' '\n' '\r' '\u0009' '\u000a' '\u000A' '\u000d' '\u000D' '\u0020'; do
    _in="${_in//"$_esc"/ }"
  done
  _b='(^|[^[:alnum:]_])'; _e='([^[:alnum:]_]|$)'
  _looks_promotion=0
  if [[ $_in =~ ${_b}git${_e} ]]; then
    if [[ $_in =~ ${_b}push${_e} ]] && [[ $_in =~ (^|[^[:alnum:]_/.-]|refs/heads/)(main|master)${_e} ]]; then
      _looks_promotion=1
    fi
    [[ $_in =~ ${_b}merge${_e} ]] && _looks_promotion=1
  fi
  [[ $_in =~ ${_b}gh${_e} ]] && [[ $_in =~ ${_b}pr${_e} ]] && [[ $_in =~ ${_b}merge${_e} ]] && _looks_promotion=1
  if [ "$_looks_promotion" = "1" ]; then
    [ "${QA_ALLOW_MAIN:-0}" = "1" ] && { echo "qa-flow:${_missing} missing but QA_ALLOW_MAIN=1 — allowed (audited)." >&2; exit 0; }
    echo "BLOCKED by qa-flow release gate: not found on PATH:${_missing} — cannot verify certification. Install them (python3 on Windows: run Claude Code in WSL/Git Bash), or set QA_ALLOW_MAIN=1 to override." >&2
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
_here="${BASH_SOURCE[0]%/*}"; [ "$_here" = "${BASH_SOURCE[0]}" ] && _here=.
_lib="$_here/lib/normalize_cmd.sh"
if [ -f "$_lib" ] && . "$_lib" 2>/dev/null && type normalize_segments >/dev/null 2>&1; then
  seg="$(printf '%s' "$cmd" | normalize_segments)"
else
  seg="$cmd"
fi
targets_main=0
# #1410 / #1470. The destination is decided by `push_targets.py --classify`, over the RAW command:
# the normaliser answers only for a segment that STARTS with the verb, so `timeout 60 git push origin
# main`, `sudo -u x git ...`, `( git push ... )`, `bash -c '...'` and `eval` all passed it. The
# classifier finds git and gh anywhere in a segment, recurses into `sh -c` strings and `eval`, and
# prints one line per finding: PUSH_MAIN <dst>, GIT_MERGE, PR_MERGE <selector>. Exit 0 = read;
# anything else = could not judge (an unreadable refspec, such as one a substitution builds, or a
# crash), which is treated as a promotion -- CLOSED. What a `$( )`, `<( )`, `>( )` or backtick
# substitution RUNS is read as a command in its own right (#1550), so a push inside one is classified
# like any other. It runs only when the raw command mentions git or gh at all.
# KNOWN LIMITS (the threat model is an honest mistake, not obfuscation -- coordinator's ruling on
# #1470; listed in push_targets.py): `bash -c $'...'`, `eval "$(...)"` (the output of a substitution
# that is then executed), a run-time verb (`$(echo git) push`, `$g push`), here-strings, `... | bash`,
# `fish -c`, and aliases defined in git config.
_pt="${CLAUDE_PLUGIN_ROOT:-}/scripts/push_targets.py"
# Quotes and backslashes are dropped before the pre-check: `g''it`, `gi\t` and `"g"it` are all git
# to the shell, and a literal `*git*` test sent them past the classifier (41's delta review).
_probe="$(printf '%s' "$cmd" | tr -d "'\"\\\\")"
case "$_probe" in
  *git*|*gh*) _mentions=1 ;;
  *) _mentions=0 ;;
esac
if [ "$_mentions" = 1 ] && [ -f "$_pt" ]; then
  if _found="$(printf '%s' "$cmd" | python3 "$_pt" --classify 2>/dev/null)"; then
    while IFS= read -r _line; do
      case "$_line" in
        "PUSH_MAIN "*) targets_main=1 ;;
        GIT_MERGE)
          git rev-parse --abbrev-ref HEAD 2>/dev/null | grep -qE '^(main|master)$' && targets_main=1 ;;
        PR_MERGE*)
          # The PR the command NAMES (number, URL or branch); bare = the current branch's PR.
          _sel="${_line#PR_MERGE}"; _sel="${_sel# }"
          if [ -n "$_sel" ]; then
            base="$(gh pr view "$_sel" --json baseRefName -q .baseRefName 2>/dev/null || true)"
          else
            base="$(gh pr view --json baseRefName -q .baseRefName 2>/dev/null || true)"
          fi
          case "$base" in main|master|"") targets_main=1 ;; esac ;;  # unresolved base -> promotion
      esac
    done <<EOF_FOUND
$_found
EOF_FOUND
  else
    targets_main=1
  fi
elif [ "$_mentions" = 1 ]; then
  # The classifier is missing: the pre-#1410 detection, with the whole-word match over the RAW
  # command so a quoted `"main"` is still seen. Over-blocks a `-main` branch name; never under-blocks
  # what it used to catch.
  printf '%s\n' "$seg" | grep -qE '^[[:space:]]*git[[:space:]]+push\b' \
    && printf '%s' "$cmd" | grep -qE '\b(main|master)\b' && targets_main=1
  printf '%s\n' "$seg" | grep -qE '^[[:space:]]*git[[:space:]]+merge\b' \
    && git rev-parse --abbrev-ref HEAD 2>/dev/null | grep -qE '^(main|master)$' && targets_main=1
  if printf '%s\n' "$seg" | grep -qE '^[[:space:]]*gh[[:space:]]+pr[[:space:]]+merge\b'; then
    num="$(printf '%s' "$seg" | grep -oE '(^|[[:space:]])[0-9]+([[:space:]]|$)' | tr -d ' ' | head -1)"
    if [ -n "$num" ]; then
      base="$(gh pr view "$num" --json baseRefName -q .baseRefName 2>/dev/null || true)"
    else
      base="$(gh pr view --json baseRefName -q .baseRefName 2>/dev/null || true)"
    fi
    case "$base" in main|master|"") targets_main=1 ;; esac
  fi
fi
[ "$targets_main" -eq 1 ] || exit 0

deny() { echo "BLOCKED by qa-flow release gate: $1" >&2; exit 2; }

# NOT THE MARKETPLACE'S OWN REPO. This hook gates a CONSUMER project's promotion: it asks whether
# QA certified the app before it ships. The repository that SHIPS qa-flow is not a consumer of it
# -- it has no app, no staging and no `qa/` surface, so there is nothing to certify and never will
# be. Until this check existed the gate denied every promotion of its own source repo, which is a
# gate that is wrong about correct code: the maintainer either overrides it every release, or
# switches it off, and then it protects nobody.
#
# `.claude-plugin/marketplace.json` is the discriminator because it is what MAKES a tree a
# marketplace -- no consumer project has one, and a consumer cannot acquire one by accident.
# Deliberately NOT keyed on "the project has no qa/ directory": that is the ordinary state of an
# app which has simply never run `/qa-flow:setup-qa`, and exempting it would let every such app
# promote unchecked. That distinction is the whole safety of this block, and the harness carries
# both cases -- a marketplace tree that must PASS and a bare repo that must still be BLOCKED.
if [ -f ".claude-plugin/marketplace.json" ]; then
  echo "qa-flow: this is the marketplace repo itself, which ships qa-flow rather than consuming it — release gate not applicable." >&2
  exit 0
fi

[ "${QA_ALLOW_MAIN:-0}" = "1" ] && { echo "qa-flow: QA_ALLOW_MAIN=1 override — promotion allowed without a fresh stamp (audited)." >&2; exit 0; }

# `--verify -q` prints NOTHING for a missing ref. Plain `rev-parse origin/dev` echoes the literal
# "origin/dev" to stdout before failing, so the fallback's sha arrived on a second line and no stamp
# could ever match in a repo without a fetched origin/dev (found by the #1337 fixtures).
devsha="$(git rev-parse --verify -q origin/dev 2>/dev/null || git rev-parse --verify -q dev 2>/dev/null || true)"
[ -n "$devsha" ] || deny "cannot resolve dev sha to compare against the certification. Fetch dev and retry."

# The STAMP is read as COMMITTED at dev, never from this checkout's working tree: main receives dev,
# so an uncommitted or locally edited stamp certifies nothing that will ship (#1437 review, round 3).
stamp_tmp="$(mktemp 2>/dev/null || printf '%s' "${TMPDIR:-/tmp}/qa-certification.$$")"
evtmp="$(mktemp 2>/dev/null || printf '%s' "${TMPDIR:-/tmp}/qa-release-evidence.$$")"
trap 'rm -f "$stamp_tmp" "$evtmp"' EXIT
if ! git show "${devsha}:qa/CERTIFICATION" >"$stamp_tmp" 2>/dev/null; then
  deny "no qa/CERTIFICATION is committed at dev (${devsha:0:12}). Run /qa-flow:certify against staging, then commit the stamp to dev by PR -- an uncommitted stamp is not what main will receive."
fi

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
verdict="$(python3 "$reader" --stamp "$stamp_tmp" --field verdict 2>/dev/null || true)"
csha="$(python3 "$reader" --stamp "$stamp_tmp" --field sha 2>/dev/null || true)"
# TWO conditions, not one, because they need different sentences. Empty means the stamp could not
# be READ -- ask the reader why. Non-empty but not PASS means the stamp is fine and the verdict is
# genuinely negative; the reader has nothing to add, and calling --explain there produced the useless
# "the stamp is readable and verdict is set" while denying the promotion. Caught by running it.
if [ -z "$verdict" ]; then
  why="$(python3 "$reader" --stamp "$stamp_tmp" --field verdict --explain 2>/dev/null || true)"
  # A gate must still deny when it cannot explain itself.
  deny "${why:-certification verdict could not be read. Re-certify.}"
elif [ "$verdict" != "PASS" ]; then
  deny "certification verdict is ${verdict}, not PASS. Fix the defects and re-certify."
fi

# #2: the sha binding IS the gate — empty/garbled sha must fail closed, not pass on PASS alone.
[ -n "$csha" ] || deny "certification has no sha — the stamp is invalid. Re-run /qa-flow:certify."

# #1428. A PASS is also a claim that the two release-only layers ran and passed: the first-boot
# operator walkthrough on an empty database, and the forged-request authorization sweep. A release
# certified without them shipped a root admin who could not create staff and three authorization
# holes. `release_evidence.py stamp` re-judges the evidence the stamp names and prints its paths; an
# older stamp (no schema 2) passes with a warning while it is grandfathered, for one release.
# Fail-closed: a missing script, or any error, is a non-zero exit, and that denies.
# The evidence check judges the evidence COMMITTED at dev (--rev), not this checkout's working tree,
# where a staged fix could hide a committed HOLE (#1437 review).
ev="${CLAUDE_PLUGIN_ROOT:-}/scripts/release_evidence.py"
if evidence="$(python3 "$ev" stamp --rev "$devsha" 2>"$evtmp")"; then
  grep '^WARNING' "$evtmp" | sed 's/^WARNING /qa-flow: /' >&2
else
  why="$(grep -E '^(FAIL|unusable)' "$evtmp" 2>/dev/null | head -3 | tr '\n' ' ')"
  deny "the release-only layers do not pass (#1428): ${why:-release_evidence.py could not run.} Fix them and re-certify."
fi
# devsha was resolved above, before the stamp was read.
if [ -n "$devsha" ]; then
  case "$devsha" in
    "$csha"*) : ;;
    *)
      # #1337. Committing the stamp to dev by PR moves dev to a commit nobody tested, so an exact-sha
      # match denied the very promotion the stamp was written for. Accept an ANCESTOR of dev only when
      # the delta since it is the stamp itself (or nothing). Any other change still means re-certify.
      # A failed rev-parse or diff denies: an error must not read as "nothing changed".
      full="$(git rev-parse --verify -q "${csha}^{commit}" 2>/dev/null || true)"
      if [ -z "$full" ] || ! git merge-base --is-ancestor "$full" "$devsha" 2>/dev/null; then
        deny "certification is for sha ${csha:0:12}, but dev is at ${devsha:0:12}. dev moved — re-certify before promoting."
      fi
      # quotePath off: a non-ASCII evidence filename must arrive as itself, not "\303\251"-quoted, or a
      # legitimate evidence commit reads as an unrecognised change and is denied (#1437 review).
      # --no-renames: a rename lists BOTH paths. With rename detection on, moving app/x.rb into the
      # evidence folder listed only the new path, so the code's removal from app/ was never judged
      # (#1437 review, driven to rc 0).
      if ! delta="$(git -c core.quotePath=false diff --no-renames --name-only "$full" "$devsha" 2>/dev/null)"; then
        deny "could not diff the certified sha ${csha:0:12} against dev ${devsha:0:12}. Fetch and retry, or re-certify."
      fi
      # The stamp's own commit may also carry the evidence it names (#1428): the walkthrough and the
      # sweep are recorded AFTER the tested sha, so requiring them before it would be circular.
      # Anything else changed since the tested sha still means re-certify.
      extra="$(printf '%s\n' "$delta" | while IFS= read -r f; do
        [ -z "$f" ] && continue
        [ "$f" = "qa/CERTIFICATION" ] && continue
        ok=0
        while IFS= read -r p; do
          [ -n "$p" ] || continue
          # A directory (trailing "/") matches as a prefix; the sweep is ONE file and matches exactly,
          # or `sweep.csv.rb` would ride along. The leading "(" matters: inside $( ) a bare
          # `pattern)` closes the substitution.
          case "$p" in
            (*/) case "$f" in ("$p"*) ok=1 ;; esac ;;
            (*) [ "$f" = "$p" ] && ok=1 ;;
          esac
        done <<EVIDENCE
$evidence
EVIDENCE
        [ "$ok" = 1 ] || printf '%s\n' "$f"
      done)"
      if [ -n "$extra" ]; then
        deny "certification is for sha ${csha:0:12}; dev (${devsha:0:12}) has changed more than the stamp since: $(printf '%s' "$extra" | head -3 | tr '\n' ' '). Re-certify before promoting."
      fi
      ;;
  esac
else
  deny "cannot resolve dev sha to compare against the certification. Fetch dev and retry."
fi
echo "qa-flow: certification valid for ${csha:0:12} — promotion permitted." >&2
exit 0
