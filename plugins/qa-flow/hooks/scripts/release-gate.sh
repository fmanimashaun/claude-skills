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
  # #1569: a `gh api` write or a release publish, in the same coarse words-anywhere spirit.
  if [[ $_in =~ ${_b}gh${_e} ]]; then
    [[ $_in =~ ${_b}api${_e} ]] && [[ $_in =~ (merge|merges|refs|releases|mergePullRequest|updateRef|createRef) ]] && _looks_promotion=1
    [[ $_in =~ ${_b}release${_e} ]] && [[ $_in =~ ${_b}create${_e} ]] && _looks_promotion=1
  fi
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
deny() { echo "BLOCKED by qa-flow release gate: $1" >&2; exit 2; }

needs_dev=0      # judged at dev's tip: a push, a `git merge`, a PR whose head could not be resolved
pr_heads=""      # the HEAD of every PR merged into main (#1569): each is judged by its own certification
releases=""      # every `gh release create` / POST .../releases, one `RELEASE <tag> <target>` line each

# resolve_pr <selector|""> <owner/repo|""> -> base, head ("" when gh could not say)
resolve_pr() {
  local out=""
  if [ -n "$1" ] && [ -n "$2" ]; then out="$(gh pr view "$1" -R "$2" --json baseRefName,headRefOid -q '.baseRefName + " " + .headRefOid' 2>/dev/null || true)"
  elif [ -n "$1" ]; then out="$(gh pr view "$1" --json baseRefName,headRefOid -q '.baseRefName + " " + .headRefOid' 2>/dev/null || true)"
  else out="$(gh pr view --json baseRefName,headRefOid -q '.baseRefName + " " + .headRefOid' 2>/dev/null || true)"; fi
  base="${out%% *}"; head=""
  case "$out" in *" "*) head="${out#* }" ;; esac
}
# note_pr: act on base/head. The certification must be for the commit the PR merges, so a PR whose
# base or head cannot be resolved is DENIED here (#1569): judging it at dev's tip would certify a
# commit the merge may not contain. A PR into any other branch is not a promotion.
# (Decided at the end, once the override and the marketplace exemption have had their say.)
unresolved_pr=""
note_pr() {
  case "$base" in
    main|master)
      targets_main=1
      if [ -n "$head" ]; then pr_heads="${pr_heads}${head}"$'\n'; else unresolved_pr=1; fi ;;
    "") targets_main=1; unresolved_pr=1 ;;
  esac
}
if [ "$_mentions" = 1 ] && [ -f "$_pt" ]; then
  if _found="$(printf '%s' "$cmd" | python3 "$_pt" --classify 2>/dev/null)"; then
    while IFS= read -r _line; do
      case "$_line" in
        "PUSH_MAIN "*) targets_main=1; needs_dev=1 ;;
        GIT_MERGE)
          git rev-parse --abbrev-ref HEAD 2>/dev/null | grep -qE '^(main|master)$' && { targets_main=1; needs_dev=1; } ;;
        PR_MERGE*)
          # The PR the command NAMES (number, URL or branch); bare = the current branch's PR.
          _sel="${_line#PR_MERGE}"; _sel="${_sel# }"
          resolve_pr "$_sel" ""; note_pr ;;
        "API_PR_MERGE "*)
          # #1569: `gh api -X PUT .../pulls/N/merge`. `<n> <owner/repo>`, `-` = unknown (placeholder).
          _rest="${_line#API_PR_MERGE }"; _n="${_rest%% *}"; _r="${_rest#* }"
          [ "$_n" = "-" ] && _n=""; [ "$_r" = "-" ] && _r=""
          if [ -z "$_n" ]; then base=""; head=""; else resolve_pr "$_n" "$_r"; fi
          note_pr ;;
        API_MAIN) targets_main=1; needs_dev=1 ;;        # a REST merge/ref write whose base or ref is main
        "GQL_PR "*|"GQL_REF "*)
          # #1569: GraphQL mergePullRequest / updateRef name a node id; ask GitHub what it is.
          _id="${_line#* }"; base=""; head=""
          if [ "$_id" != "-" ]; then
            case "$_line" in
              GQL_PR*)
                _out="$(gh api graphql -F id="$_id" -f query='query($id:ID!){node(id:$id){... on PullRequest{baseRefName headRefOid}}}' -q '.data.node.baseRefName + " " + .data.node.headRefOid' 2>/dev/null || true)"
                base="${_out%% *}"; case "$_out" in *" "*) head="${_out#* }" ;; esac ;;
              *)
                base="$(gh api graphql -F id="$_id" -f query='query($id:ID!){node(id:$id){... on Ref{name}}}' -q '.data.node.name' 2>/dev/null || true)"
                case "$base" in main|master) targets_main=1; needs_dev=1 ;; "") targets_main=1; needs_dev=1 ;; esac
                base="other" ;;
            esac
          fi
          case "$_line" in GQL_PR*) note_pr ;; *) [ "$_id" = "-" ] && { targets_main=1; needs_dev=1; } ;; esac ;;
        "RELEASE "*) releases="${releases}${_line}"$'\n' ;;
      esac
    done <<EOF_FOUND
$_found
EOF_FOUND
  else
    targets_main=1; needs_dev=1
    # #1569: a `gh api` / `gh release` the classifier could not read (a body file that is missing or
    # on stdin, a path built by the shell) may merge ANY commit, so dev's stamp proves nothing about
    # it: deny, rather than judge it at dev's tip.
    case "$_probe" in *gh*api*|*gh*release*) unresolved_pr=1 ;; esac
  fi
elif [ "$_mentions" = 1 ]; then
  # The classifier is missing: the pre-#1410 detection, with the whole-word match over the RAW
  # command so a quoted `"main"` is still seen. Over-blocks a `-main` branch name; never under-blocks
  # what it used to catch.
  printf '%s\n' "$seg" | grep -qE '^[[:space:]]*git[[:space:]]+push\b' \
    && printf '%s' "$cmd" | grep -qE '\b(main|master)\b' && { targets_main=1; needs_dev=1; }
  printf '%s\n' "$seg" | grep -qE '^[[:space:]]*git[[:space:]]+merge\b' \
    && git rev-parse --abbrev-ref HEAD 2>/dev/null | grep -qE '^(main|master)$' && { targets_main=1; needs_dev=1; }
  if printf '%s\n' "$seg" | grep -qE '^[[:space:]]*gh[[:space:]]+pr[[:space:]]+merge\b'; then
    num="$(printf '%s' "$seg" | grep -oE '(^|[[:space:]])[0-9]+([[:space:]]|$)' | tr -d ' ' | head -1)"
    resolve_pr "$num" ""; note_pr
  fi
  # #1569: without the classifier a `gh api` write or a release cannot be read, so it is a promotion.
  printf '%s\n' "$seg" | grep -qE '^[[:space:]]*gh[[:space:]]+(api|release[[:space:]]+create)\b' \
    && printf '%s' "$cmd" | grep -qiE 'merge|refs|releases|release[[:space:]]+create|mutation' && { targets_main=1; needs_dev=1; }
fi
[ "$targets_main" -eq 1 ] || [ -n "$releases" ] || exit 0

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

# The STAMP is read as COMMITTED, never from this checkout's working tree: main receives what is
# committed, so an uncommitted or locally edited stamp certifies nothing that will ship (#1437 review,
# round 3).
stamp_tmp="$(mktemp 2>/dev/null || printf '%s' "${TMPDIR:-/tmp}/qa-certification.$$")"
evtmp="$(mktemp 2>/dev/null || printf '%s' "${TMPDIR:-/tmp}/qa-release-evidence.$$")"
trap 'rm -f "$stamp_tmp" "$evtmp"' EXIT
reader="${CLAUDE_PLUGIN_ROOT:-}/scripts/read_certification.py"
ev="${CLAUDE_PLUGIN_ROOT:-}/scripts/release_evidence.py"
JWHY=""

# judge <commit being shipped> <commit whose tree holds the stamp> <what to call the commit>
# Returns 0 when a PASS stamp certifies <commit> (exactly, or through the stamp's own commit and the
# evidence it names), 1 with JWHY set otherwise. One judgement for all three subjects (#1569): dev's
# tip for a push or a `git merge`, the HEAD of the PR for a merge (a hotfix branch is judged by its own
# commit, not dev's), and the commit a release publishes. It never exits: the caller decides.
judge() {
  local tgt="$1" at="$2" what="$3" verdict csha why full delta extra f p ok
  if ! git show "${at}:qa/CERTIFICATION" >"$stamp_tmp" 2>/dev/null; then
    JWHY="no qa/CERTIFICATION is committed at ${what} (${at:0:12}). Run /qa-flow:certify against staging, then commit the stamp to ${what} by PR -- an uncommitted stamp is not what main will receive."
    return 1
  fi
  # #721. One reader, shared with qa-status.sh, that says WHAT is wrong (a hand-written stamp is not
  # JSON; calling it "not PASS" sent a project round a loop). `|| true` swallows a missing python3 or
  # script; an empty value still denies.
  verdict="$(python3 "$reader" --stamp "$stamp_tmp" --field verdict 2>/dev/null || true)"
  csha="$(python3 "$reader" --stamp "$stamp_tmp" --field sha 2>/dev/null || true)"
  if [ -z "$verdict" ]; then
    why="$(python3 "$reader" --stamp "$stamp_tmp" --field verdict --explain 2>/dev/null || true)"
    JWHY="${why:-certification verdict could not be read. Re-certify.}"; return 1
  elif [ "$verdict" != "PASS" ]; then
    JWHY="certification verdict is ${verdict}, not PASS. Fix the defects and re-certify."; return 1
  fi
  # #2: the sha binding IS the gate -- empty/garbled sha must fail closed, not pass on PASS alone.
  if [ -z "$csha" ]; then JWHY="certification has no sha — the stamp is invalid. Re-run /qa-flow:certify."; return 1; fi
  # #1428. A PASS also claims the two release-only layers ran and passed (the first-boot walkthrough
  # and the forged-request sweep); judged from the evidence COMMITTED at the stamp (--rev), not the
  # working tree, where a staged fix could hide a committed HOLE. Fail-closed: any error denies.
  if evidence="$(python3 "$ev" stamp --rev "$at" 2>"$evtmp")"; then
    grep '^WARNING' "$evtmp" | sed 's/^WARNING /qa-flow: /' >&2
  else
    why="$(grep -E '^(FAIL|unusable)' "$evtmp" 2>/dev/null | head -3 | tr '\n' ' ')"
    JWHY="the release-only layers do not pass (#1428): ${why:-release_evidence.py could not run.} Fix them and re-certify."; return 1
  fi
  case "$tgt" in
    "$csha"*) : ;;
    *)
      # #1337. Committing the stamp moves the commit to one nobody tested, so an exact-sha match denied
      # the very promotion the stamp was written for. Accept an ANCESTOR only when the delta since it
      # is the stamp itself (or nothing, or the evidence it names). Any other change means re-certify.
      # A failed rev-parse or diff denies: an error must not read as "nothing changed".
      full="$(git rev-parse --verify -q "${csha}^{commit}" 2>/dev/null || true)"
      if [ -z "$full" ] || ! git merge-base --is-ancestor "$full" "$tgt" 2>/dev/null; then
        JWHY="certification is for sha ${csha:0:12}, but ${what} is at ${tgt:0:12}. ${what} moved — re-certify before promoting."; return 1
      fi
      # quotePath off: a non-ASCII evidence filename must arrive as itself (#1437 review). --no-renames:
      # a rename lists BOTH paths, so code moved into the evidence folder is still seen leaving app/.
      if ! delta="$(git -c core.quotePath=false diff --no-renames --name-only "$full" "$tgt" 2>/dev/null)"; then
        JWHY="could not diff the certified sha ${csha:0:12} against ${what} ${tgt:0:12}. Fetch and retry, or re-certify."; return 1
      fi
      # The stamp's own commit may also carry the evidence it names (#1428): recorded AFTER the tested
      # sha, so requiring it before would be circular.
      extra="$(printf '%s\n' "$delta" | while IFS= read -r f; do
        [ -z "$f" ] && continue
        [ "$f" = "qa/CERTIFICATION" ] && continue
        ok=0
        while IFS= read -r p; do
          [ -n "$p" ] || continue
          # A directory (trailing "/") matches as a prefix; the sweep is ONE file and matches exactly.
          # The leading "(" matters: inside $( ) a bare `pattern)` closes the substitution.
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
        JWHY="certification is for sha ${csha:0:12}; ${what} (${tgt:0:12}) has changed more than the stamp since: $(printf '%s' "$extra" | head -3 | tr '\n' ' '). Re-certify before promoting."; return 1
      fi
      ;;
  esac
  echo "qa-flow: certification valid for ${csha:0:12} — ${what} ${tgt:0:12} permitted." >&2
  return 0
}

# (1) dev's tip: a push to main, a `git merge` on main, or a merge whose PR could not be resolved.
if [ "$needs_dev" = 1 ]; then
  # `--verify -q` prints NOTHING for a missing ref; plain `rev-parse origin/dev` echoes the literal
  # "origin/dev" before failing (found by the #1337 fixtures).
  devsha="$(git rev-parse --verify -q origin/dev 2>/dev/null || git rev-parse --verify -q dev 2>/dev/null || true)"
  [ -n "$devsha" ] || deny "cannot resolve dev sha to compare against the certification. Fetch dev and retry."
  judge "$devsha" "$devsha" dev || deny "$JWHY"
fi

[ -z "$unresolved_pr" ] || deny "cannot tell which commit this command merges or publishes (the PR or ref could not be resolved, or a query/body file could not be read), so no certification can be matched to it. Name the PR by number, give a readable file, authenticate gh, and retry."

# (2) #1569: a PR merged into main is judged by the HEAD it merges -- dev's tip for a promotion, the
# hotfix branch's own commit for a hotfix. Judging a hotfix by dev's stamp certified the wrong tree.
while IFS= read -r _head; do
  [ -n "$_head" ] || continue
  if ! git cat-file -e "${_head}^{commit}" 2>/dev/null; then
    git fetch -q origin "$_head" 2>/dev/null || true
    git cat-file -e "${_head}^{commit}" 2>/dev/null || deny "the PR head ${_head:0:12} is not in this clone and could not be fetched, so its certification cannot be read. Fetch it and retry."
  fi
  judge "$_head" "$_head" "the PR head" || deny "$JWHY"
done <<EOF_HEADS
$pr_heads
EOF_HEADS

# (3) #1569: publishing. In a consumer the release is the step that builds and ships the image, so it
# needs a PASS stamp for the exact commit it publishes: --target / target_commitish, else the tag's
# commit when the tag exists, else the default branch's tip.
resolve_release_target() {
  local tag="$1" tgt="$2" r
  if [ -n "$tgt" ]; then
    git rev-parse --verify -q "refs/remotes/origin/${tgt}^{commit}" 2>/dev/null \
      || git rev-parse --verify -q "${tgt}^{commit}" 2>/dev/null; return
  fi
  if [ -n "$tag" ] && git rev-parse --verify -q "refs/tags/${tag}^{commit}" 2>/dev/null; then return 0; fi
  for r in refs/remotes/origin/main refs/remotes/origin/master refs/heads/main refs/heads/master; do
    git rev-parse --verify -q "${r}^{commit}" 2>/dev/null && return 0
  done
  return 1
}
while IFS= read -r _rel; do
  [ -n "$_rel" ] || continue
  _rest="${_rel#RELEASE }"; _tag="${_rest%% *}"; _tgt="${_rest#* }"
  [ "$_tag" = "-" ] && _tag=""; [ "$_tgt" = "-" ] && _tgt=""
  _rsha="$(resolve_release_target "$_tag" "$_tgt" | head -1)"
  [ -n "$_rsha" ] || deny "cannot resolve the commit release ${_tag:-<no tag>} would publish (target '${_tgt:-none}'). Fetch it, or pass --target <sha>."
  _first=""; _ok=0
  for _at in "$_rsha" refs/remotes/origin/main refs/remotes/origin/dev refs/heads/main refs/heads/dev; do
    _atsha="$(git rev-parse --verify -q "${_at}^{commit}" 2>/dev/null || true)"
    [ -n "$_atsha" ] || continue
    if judge "$_rsha" "$_atsha" "the release target" 2>/dev/null; then _ok=1; break; fi
    [ -n "$_first" ] || _first="$JWHY"
  done
  [ "$_ok" = 1 ] || deny "no PASS qa/CERTIFICATION covers the commit this release publishes (${_rsha:0:12}${_tag:+, tag $_tag}): ${_first:-no stamp found.} Certify that commit (/qa-flow:certify), commit the stamp, then publish."
done <<EOF_RELS
$releases
EOF_RELS
exit 0
