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
# The COARSE promotion detector, builtins only (no grep, no python3): sets _looks_promotion from the raw payload.
# Used when a tool is missing (below) AND when the deadline kills the real parse (#1575). Both cannot read the command,
# so both ask the same question the same way and err on the same side.
_coarse_looks_promotion() {
  _in="$input"
  for _esc in '\t' '\n' '\r' '\u0009' '\u000a' '\u000A' '\u000d' '\u000D' '\u0020'; do
    _in="${_in//"$_esc"/ }"
  done
  _b='(^|[^[:alnum:]_])'; _e='([^[:alnum:]_]|$)'
  _looks_promotion=0
  if [[ $_in =~ ${_b}git${_e} ]]; then
    # `heads/main` is git's own shorthand for `refs/heads/main` (`HEAD:heads/main`), so it is main too (#1602 review of
    # the timeout path: the full path denied it, this one allowed it).
    if [[ $_in =~ ${_b}push${_e} ]] && [[ $_in =~ (^|[^[:alnum:]_/.-]|refs/heads/|[^[:alnum:]_/.-]heads/)(main|master)${_e} ]]; then
      _looks_promotion=1
    fi
    # A push of EVERY branch, main among them: `--all`, `--mirror`, or a wildcard refspec (`refs/heads/*:refs/heads/*`,
    # `'*:*'`). The full path classifies all three as PUSH_MAIN; none names main in words. `--tags` is not on this list.
    if [[ $_in =~ ${_b}push${_e} ]]; then
      [[ $_in =~ (^|[^[:alnum:]_-])--(all|mirror)${_e} ]] && _looks_promotion=1
      [[ $_in =~ [*] ]] && _looks_promotion=1
      # #1607 (S3): a destination SPELLED so no word shows: `HEAD:$B`, `mai?`, `ma[i]n`, `ma{in,}`, `'HEAD:ma''in'`. The full path refuses all
      # of them ("cannot tell which commit..."), and `*` already was here. Read as RULES, in the shapes a glob or an expansion takes inside a
      # WORD, and only AFTER `push` in the SAME simple command (no `;`, `&` or `|` between): the payload is JSON and has braces, brackets, commas
      # and quotes of its own, and a `$` in an earlier line, an env prefix or a commit message that merely says "push" is not a destination (the
      # measured over-block of the first version: 5 of 8 new refusals on 486 commands). A `?` followed by a letter is a URL query, not a glob.
      # A verb built by a variable (`git $V push`) is its own rule, since the `$` comes BEFORE `push`.
      # Cost: `git push origin $BRANCH` is refused on a timeout ("retry it").
      _sq="'"
      # #1617 (N6): `push` is a WORD that starts a command word (after a space, `;`, `&`, `|` or `(`) and is not followed by a name character, so
      # `git checkout -b \"feature/push-fix\"` is not a push. The trailing test is an OPTIONAL group (an empty alternative is an invalid regex on macOS), not a consumed
      # character, so a backtick or a quote RIGHT after `push` is still seen by the rules that follow.
      # QUOTES AND BACKSLASHES MAY SIT BEFORE THE WORD: shell quote removal makes `git \"push\" origin HEAD:ma?n` and `git \\push ...` a push (#1617 review:
      # 20 spellings were refused by `dev` and allowed by the first version of this boundary). In the payload a quote is `\"`, so the class has both.
      _pw='(^|[[:space:];&|(])["'"'"'\\]*push'
      _seg="${_pw}"'([^[:alnum:]_./-][^;&|]*)?'
      _seg_cmd="${_pw}"'([^[:alnum:]_./-][^;&|"]*)?'   # ends at the first RAW double quote: inside the command a quote is `\"`, so a later key (`"description":"don't wait"`) is out
      # #1617 (N5): a `?` is a glob unless it opens a URL query, which is `?key=`: `HEAD:ma?n` is main, `https://x.test/r.git?z=1` is not.
      _g_q='[[:alnum:]_/.-][?][[:alnum:]_.%-]*([^[:alnum:]_.%=-]|$)'
      _g_b='[[:alnum:]_/.-][{][^{}"[:space:]]*,[^{}"[:space:]]*[}]'
      _g_s='[[:alnum:]_/.-][[][^]"[:space:][]+[]]'
      # A QUOTE, A BACKSLASH OR A BACKTICK after `push`: a name split by any of them (`HEAD:"ma"in`, `ma\in`, `m'ain'`, an empty pair) is `main` to a
      # shell and no word to a regex, and each new spelling needed a new rule (the #1607 review: 19 of 31 got through the empty-pair one). One class
      # instead of a list of shapes. In the payload a command's own double quote is `\"`, so the backslash covers it, and the JSON's own raw quotes
      # are not in the class. Cost: `git push origin 'feat/x'` and a commit message that mentions `git push` inside backticks are refused on a timeout.
      _g_x="[\\\\${_sq}\`]"
      [[ $_in =~ ${_seg}[$] ]] && _looks_promotion=1
      [[ $_in =~ ${_seg}${_g_q} ]] && _looks_promotion=1
      [[ $_in =~ ${_seg}${_g_b} ]] && _looks_promotion=1
      [[ $_in =~ ${_seg}${_g_s} ]] && _looks_promotion=1
      [[ $_in =~ ${_seg_cmd}${_g_x} ]] && _looks_promotion=1
      [[ $_in =~ ${_b}git[[:space:]]+[$] ]] && _looks_promotion=1
    fi
    [[ $_in =~ ${_b}merge${_e} ]] && _looks_promotion=1
  fi
  [[ $_in =~ ${_b}gh${_e} ]] && [[ $_in =~ ${_b}pr${_e} ]] && [[ $_in =~ ${_b}merge${_e} ]] && _looks_promotion=1
  # #1569: a `gh api` write or a release publish, in the same coarse words-anywhere spirit.
  if [[ $_in =~ ${_b}gh${_e} ]]; then
    [[ $_in =~ ${_b}api${_e} ]] && [[ $_in =~ (merge|merges|refs|releases|mergePullRequest|updateRef|createRef) ]] && _looks_promotion=1
    # A repository dispatch is a `gh api` endpoint, so it stays a word here; the CLI verbs are a rule below.
    [[ $_in =~ ${_b}api${_e} ]] && [[ $_in =~ dispatches ]] && _looks_promotion=1
    # A GraphQL body the gate cannot read: `--input` (a file or stdin) or `-F`/`--field` with `=@file`. A lower-case
    # `-f query=@x` is a LITERAL string in gh, not a file read, and is not on this list (the full path allows it too).
    if [[ $_in =~ ${_b}api${_e} ]] && [[ $_in =~ ${_b}graphql${_e} ]]; then
      [[ $_in =~ (^|[^[:alnum:]_-])--input${_e} ]] && _looks_promotion=1
      [[ $_in =~ (^|[^[:alnum:]_-])(-F|--field)[[:space:]=]*[^[:space:]=]+=@ ]] && _looks_promotion=1
      # #1607 (S4): a body built by substitution (`$(cat q.graphql)`, a backtick, `<(...)`): the full path refuses it, the words are not there.
      case $_in in *'$('*|*'`'*|*'<('*) _looks_promotion=1 ;; esac
    fi
    # #1607 (S1, S2): the full path refuses an unlisted `gh` write by default, and the coarse path was a list of words, so each word narrowed the
    # gap and none closed it. A `gh api` that WRITES is a rule: a write method (PUT, POST, PATCH, DELETE) or any field or --input (gh sends a POST
    # when it is given fields), unless the method is GET. GraphQL keeps its own rules above and below (a QUERY posted with -f is not a write).
    # Cost, accepted for a fallback that runs only when the gate overran its deadline: an ordinary `gh api ... -f body=x` is refused too.
    if [[ $_in =~ ${_b}api${_e} ]] && ! [[ $_in =~ ${_b}graphql${_e} ]]; then
      _m_get='(^|[^[:alnum:]_-])(-X|--method)[^[:alnum:]]{0,3}[Gg][Ee][Tt]([^[:alnum:]_]|$)'
      _m_wr='(^|[^[:alnum:]_-])(-X|--method)[^[:alnum:]]{0,3}([Pp][Uu][Tt]|[Pp][Oo][Ss][Tt]|[Pp][Aa][Tt][Cc][Hh]|[Dd][Ee][Ll][Ee][Tt][Ee])([^[:alnum:]_]|$)'
      _m_fl='(^|[^[:alnum:]_-])(-f|-F|--field|--raw-field)[[:space:]=]*[A-Za-z_][A-Za-z0-9_.]*=|(^|[^[:alnum:]_-])--input([^[:alnum:]_-]|$)'
      if [[ $_in =~ $_m_wr ]]; then
        _looks_promotion=1
      elif ! [[ $_in =~ $_m_get ]] && [[ $_in =~ $_m_fl ]]; then
        _looks_promotion=1
      fi
    fi
    # #1617: THE CLI VERBS ARE A RULE, NOT A LIST OF THE ONES THAT WRITE. The full path refuses a verb it cannot place, and 13 of 23 verbs
    # slipped through a word list here (`gh release delete`, `gh workflow disable`, an alias). A `gh` call whose verb is not on the full path's own
    # safe list is refused (`gh api` has its own rules above). Cost, accepted for a fallback that runs only when the gate overran its deadline: a verb
    # the full path cannot place (`gh repo rename`, `gh release delete`, `gh workflow disable`, an alias) is refused ("retry it").
  fi
  # The words are the payload with its JSON and shell punctuation turned into spaces, command separators kept as `;`.
  _t="${_in//[;&|()]/ ; }"
  _t="${_t//[\"\{\}\\\`\$\']/ }"
  _cw=(); read -ra _cw <<< "$_t"
  _n=${#_cw[@]}; _i=0
  while [ "$_i" -lt "$_n" ]; do
    _tool="${_cw[$_i]}"
    if [ "$_tool" = gh ] || [ "$_tool" = git ]; then
      _v1=""; _v2=""; _words=""; _j=$((_i + 1))
      while [ "$_j" -lt "$_n" ] && [ "${_cw[$_j]}" != ";" ]; do
        case ${_cw[$_j]} in
          -R|--repo|-C|-c|--hostname|--git-dir|--work-tree|--namespace) _j=$((_j + 2)); continue ;;
          -*) ;;
          *) if [ -z "$_v1" ]; then _v1="${_cw[$_j]}"; elif [ -z "$_v2" ]; then _v2="${_cw[$_j]}"; fi; _words="$_words ${_cw[$_j]}" ;;
        esac
        _j=$((_j + 1))
      done
      if [ "$_tool" = gh ] && [ -n "$_v1" ]; then
        # THE FULL PATH'S OWN SAFE LIST (`GH_GROUPS_ANY` and `GH_GROUPS_SOME` in push_targets.py): a verb it allows cannot merge into main or
        # publish a release, and a verb it does not list is one it cannot place. A fixture compares the two, so they cannot drift apart.
        case "$_v1" in
          issue|auth|config|status|browse|search|label|gist|extension|alias|completion|help|version|cache|variable|secret|ssh-key|gpg-key|project|\
          attestation|agent-task|licenses|preview|api) ;;
          *) case "$_v1 $_v2" in
               "pr view"|"pr list"|"pr create"|"pr checks"|"pr diff"|"pr status"|"pr checkout"|"pr comment"|"pr edit"|"pr review"|"pr close"|"pr reopen"|\
               "pr ready"|"pr lock"|"pr unlock"|"repo view"|"repo list"|"repo clone"|"repo fork"|"repo gitignore"|"repo license"|"run list"|"run view"|\
               "run watch"|"run download"|"run cancel"|"run delete"|"workflow list"|"workflow view"|"release list"|"release view"|"release download"|\
               "release upload"|"release delete-asset"|"ruleset list"|"ruleset view"|"ruleset check"|"org list") ;;
               *) _looks_promotion=1 ;;
             esac ;;
        esac
      fi
      # #1617 (N4): a git alias hides `push` (`git p origin main` after `git config alias.p push`). A verb git does not have as a command, with
      # main or master among its arguments (`origin main`, `HEAD:main`), is refused. A real verb that is not `push` is handled by its own rule.
      if [ "$_tool" = git ] && [ -n "$_v1" ]; then
        case $_v1 in
          push|status|log|diff|show|add|commit|checkout|switch|branch|fetch|pull|merge|rebase|stash|reset|restore|tag|remote|config|rev-parse|rev-list|\
          ls-remote|ls-files|ls-tree|worktree|clean|blame|grep|cherry-pick|revert|describe|shortlog|bisect|apply|am|archive|bundle|cat-file|count-objects|\
          fsck|gc|help|init|clone|mv|rm|notes|reflog|show-ref|symbolic-ref|update-ref|var|version|whatchanged|diff-tree|name-rev|merge-base|for-each-ref|\
          submodule|sparse-checkout|maintenance|format-patch|range-diff|cherry|check-ignore|hash-object|write-tree|read-tree|commit-tree|prune|repack|rerere|\
          difftool|mergetool|request-pull|stage|annotate|verify-commit|verify-tag|credential|filter-branch) ;;
          *) case " $_words " in
               *" main "*|*" master "*|*" refs/heads/main "*|*" heads/main "*|*:main\ *|*:master\ *|*:refs/heads/main\ *|*:heads/main\ *|*:refs/heads/master\ *) _looks_promotion=1 ;;
             esac ;;
        esac
      fi
    fi
    _i=$((_i + 1))
  done
  # #1575 (#1602 review F1): ANY GraphQL mutation. The full path denies one by shape; this path cannot parse, so it
  # denies by the word, whatever the mutation is called or how the flag is spelled (-f, -F, --raw-field). A list of
  # mutation NAMES let enablePullRequestAutoMerge, createCommitOnBranch and updatePullRequestBranch through.
  [[ $_in =~ ${_b}gh${_e} ]] && [[ $_in =~ ${_b}api${_e} ]] && [[ $_in =~ ${_b}graphql${_e} ]] && [[ $_in =~ mutation ]] && _looks_promotion=1
}

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
  _coarse_looks_promotion
  if [ "$_looks_promotion" = "1" ]; then
    [ "${QA_ALLOW_MAIN:-0}" = "1" ] && { echo "qa-flow:${_missing} missing but QA_ALLOW_MAIN=1 — allowed (audited)." >&2; exit 0; }
    echo "BLOCKED by qa-flow release gate: not found on PATH:${_missing} — cannot verify certification. Install them (python3 on Windows: run Claude Code in WSL/Git Bash), or set QA_ALLOW_MAIN=1 to override." >&2
    exit 2
  fi
  exit 0
fi
# #1575: from here to the final `exit 0` runs in `_gate_main`, in its own process group, under a deadline (the end of this file).
_gate_main() {
cmd="$(printf '%s' "$input" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("tool_input",{}).get("command",""))' 2>/dev/null || printf '%s' "$input")"

# --- Normalize the command so promotion detection can't be fooled (must fail CLOSED) ---
# One normaliser, shared with rails-flow's guard-bash.sh: `lib/normalize_cmd.sh` beside this script
# (plugins install alone, so each ships a copy; the maintainer lint `hook-lib-drift` keeps the two
# byte-identical, #906). It strips quoted spans, comments and heredoc bodies, splits on ; | && ||
# and newlines, and peels env/sudo/git-global-option prefixes, so the verb is at the START of a
# segment. FAIL CLOSED if the lib is missing: match the raw text, as before #3/#7/#48.
_here="${BASH_SOURCE[0]%/*}"; [ "$_here" = "${BASH_SOURCE[0]}" ] && _here=.
_lib="$_here/lib/normalize_cmd.sh"
# `LC_ALL=C` and a fail-closed reading (#1657 review): sed and the lib's other stages are not byte-safe in a UTF-8 locale, and
# macOS's sed aborts on an invalid byte ("illegal byte sequence"), which left the line, or the whole command, with NO segments:
# `git push origin main \xff` read as nothing and passed. The caller's locale is not ours to trust, and an output the normaliser
# could not produce (a non-zero status, or nothing for a command that is not empty) is "could not read", never "nothing to judge".
_seg_unread=0
if [ -f "$_lib" ] && . "$_lib" 2>/dev/null && type normalize_segments >/dev/null 2>&1; then
  seg="$(printf '%s' "$cmd" | LC_ALL=C normalize_segments)" || { seg="$cmd"; _seg_unread=1; }
  [ -n "$seg" ] || [ -z "$cmd" ] || _seg_unread=1
else
  seg="$cmd"
fi
targets_main=0
# #1410 / #1470. The destination is decided by `push_targets.py --classify`, over the RAW command:
# the normaliser answers only for a segment that STARTS with the verb, so `timeout 60 git push origin
# main`, `sudo -u x git ...`, `( git push ... )`, `bash -c '...'` and `eval` all passed it. The
# classifier finds git and gh anywhere in a segment, recurses into `sh -c` strings and `eval`, and
# prints one line per finding: PUSH_MAIN <dst>, GIT_MERGE (GIT_MERGE_MAIN, GIT_PULL_MAIN: on main by the command's own doing), PR_MERGE <selector>. Exit 0 = read;
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
# `LC_ALL=C`: macOS tr aborts at an invalid byte in a UTF-8 locale and drops the rest, so `echo \xff` + a newline + a push read as no git at all (#1657 review).
_probe="$(printf '%s' "$cmd" | LC_ALL=C tr -d "'\"\\\\")"
# #1569: AND any command with a shell expansion in it. `g$'h' api`, `$'\x67h'`, `g{h,}` and `$g` all run gh
# without the letters g-h-t-h next to each other, so the probe above never saw them. The classifier
# finds nothing in a command that has no effect and denies one whose command word it cannot read.
case "$_probe" in
  *git*|*gh*) _mentions=1 ;;
  *'$'*|*'{'*|*'`'*) _mentions=1 ;;
  *) _mentions=0 ;;
esac
deny() { echo "BLOCKED by qa-flow release gate: $1" >&2; exit 2; }

needs_dev=0      # judged at dev's tip: a push of `main` to this repo's own remote, with no explicit source
ship=""          # one line per commit the command puts on main: "<sha><TAB><repo or -><TAB><label>" (#1569)
releases=""      # every release the command publishes: "<tag> <target> <repo ctx>"; `-` = not given
unresolved_pr="" # set when the commit, PR, ref, release or repository a command acts on cannot be resolved:
                 # decided at the end, once the override and the marketplace exemption have had their say
_crepo="-"; _cdir="-"; _dir_seen=""
_foreign=""      # set when any effect acts on a repository other than this checkout's

# --- WHICH REPOSITORY (#1569). The stamp is read from the repository the command ACTS on. `gh -R`,
# GH_REPO, a `repos/<o>/<r>/` path and a git remote other than origin each make a command act on
# a repository other than this checkout's, and reading THIS checkout's stamp for it certified the
# wrong thing. repo_of_url: owner/repo (lower case) of a GitHub remote URL, "" for anything else.
repo_of_url() {
  local u="$1" r
  case "$u" in ""|.*|/*|~*) return 0 ;; esac
  r="$(printf '%s' "$u" | sed -E 's#^(ssh://)?([^@/]+@)?github\.com[:/]+##; s#^https?://([^@/]+@)?github\.com/##; s#^git://github\.com/##; s#\.git/?$##; s#/+$##')"
  printf '%s\n' "$r" | grep -E '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$' | tr 'A-Z' 'a-z'
}
# ctx_repo <ctx field>: sets _R. "" = THIS checkout's repository; else the owner/repo the command acts on.
# `-` falls back to GH_REPO from the hook's environment. An unreadable repository marks the command
# unjudgeable.
ctx_repo() {
  local f="$1" n u r L orig
  _R=""
  # The CONFIGURED url (not the rewritten one `get-url` prints): `insteadOf` is a transport detail.
  orig="$(git config --get remote.origin.url 2>/dev/null || true)"
  L="$(repo_of_url "$orig")"
  case "$f" in
    remote:*)
      n="${f#remote:}"
      case "$n" in
        *://*|*@*:*) u="$n" ;;
        .|..|/*|./*|../*|~*) unresolved_pr=1; return 0 ;;
        *) u="$(git config --get "remote.${n}.url" 2>/dev/null || true)" ;;
      esac
      if [ -z "$u" ]; then
        # No such remote. `origin` unconfigured is the old behaviour (judged here); any other name is unknown.
        [ "$n" = "origin" ] || unresolved_pr=1
        return 0
      fi
      [ "$u" = "$orig" ] && return 0
      r="$(repo_of_url "$u")"
      [ -n "$r" ] || { unresolved_pr=1; return 0; } ;;
    -) f="${GH_REPO:-}"
       [ -n "$f" ] || return 0
       r="$(printf '%s' "$f" | tr 'A-Z' 'a-z')" ;;
    *) r="$(printf '%s' "$f" | tr 'A-Z' 'a-z')" ;;
  esac
  grep -qE '^[a-z0-9_.-]+/[a-z0-9_.-]+$' <<<"$r" || { unresolved_pr=1; return 0; }
  [ "$r" = "$L" ] && return 0
  _R="$r"; _foreign=1
}
# plain_ref <value>: a ref taken from the GATED COMMAND'S TEXT is a plain branch, tag or commit name before it reaches
# `git fetch` (#1600). This hook runs BEFORE the permission prompt, so a value that starts with "-" would be read as an
# OPTION: `git fetch origin --upload-pack=<program>` RUNS the program when origin is a local path or ssh. Also refused: a
# `:` (a refspec would write a local ref) and `..`, a space or any other character a name does not have. The caller
# fetches nothing, the ref stays unresolved, and the command is denied as one the hook cannot judge.
# (#1610) It also refuses what `git check-ref-format` refuses in a name: a leading, doubled or trailing slash, a component that starts
# with a dot, a `.lock` ending and a trailing dot, so the API is never asked about a name no repository can hold.
plain_ref() { case "$1" in ""|-*|*[!A-Za-z0-9._/-]*|*..*|/*|*//*|*/|.*|*/.*|*.lock|*.lock/*|*.) return 1 ;; esac; return 0; }
# A LOOKUP THAT ERRORS IS UNRESOLVED, NOT AN ANSWER (#1626). Real `gh api graphql` exits 1 and prints the raw error body to STDOUT
# (`{"data":{"node":null},"errors":[...]}`), so `2>/dev/null || true` kept the body, `base` became that JSON, was neither `main` nor empty,
# and a GraphQL merge into main was allowed. `gh_lookup` prints what a read-only `gh` call printed ONLY when it exited 0, and nothing when it
# did not. Where the answer decides WHICH BRANCH a command acts on, the caller then checks the SHAPE of what is left (a plain ref name), so a
# body that arrives with exit 0 is no answer either. Unresolved is refused downstream.
gh_lookup() { local _o; _o="$(gh "$@" 2>/dev/null)" || return 1; printf '%s' "$_o"; }
# resolve_pr <selector|""> <ctx repo> -> base, head, _PRR ("" when gh could not say). Resolved the way
# the command resolves it: the same selector, the same -R/GH_REPO, the same directory.
resolve_pr() {
  local out="" repo="" a
  ctx_repo "$2"
  [ -z "$_R" ] || repo="$_R"
  a=(pr view); [ -z "$1" ] || a+=("$1"); [ -z "$repo" ] || a+=(-R "$repo")
  out="$(gh_lookup "${a[@]}" --json baseRefName,headRefOid,url -q '.baseRefName + " " + .headRefOid + " " + .url' || true)"
  base="${out%% *}"; head=""; _PRR=""
  case "$out" in *" "*) out="${out#* }"; head="${out%% *}"
                 _PRR="$(printf '%s' "${out#* }" | sed -E 's#^https?://[^/]+/##; s#/pull/.*##' | tr 'A-Z' 'a-z')" ;; esac
  sane_pr_lookup
}
# A name GITHUB RETURNED is judged more loosely than a ref typed into a command (`plain_ref`): `release+2026`, `feature#7` and `user@team/topic`
# are branches, and a PR into one is not a promotion, so refusing them as "unresolved" would block merges `dev` allowed. What is rejected is what an
# error body contains (whitespace, braces, quotes, brackets) and what git forbids in a ref name (: ? * ^ ~ \).
ref_name_returned() { case "$1" in ""|*[[:space:]]*|*\{*|*\}*|*\"*|*\[*|*\]*|*:*|*\?*|*\**|*\^*|*\~*|*\\*) return 1 ;; esac; return 0; }
# What a PR lookup returned must LOOK like a base ref name; else it is no answer (base and head "" = unresolved, refused by note_pr).
# #1628: a looked-up ref may come back qualified (`refs/heads/main`, `heads/main`); the coarse detector already reads those as main, so strip ONE prefix.
short_ref() { local r="$1"; r="${r#refs/heads/}"; [ "$r" = "$1" ] && r="${r#heads/}"; printf '%s' "$r"; }
sane_pr_lookup() { ref_name_returned "$base" && base="$(short_ref "$base")" || { base=""; head=""; _PRR=""; }; }
# add_ship <sha> <repo or -> <label>
add_ship() { ship="${ship}${1}"$'\t'"${2:--}"$'\t'"${3}"$'\n'; }
# add_commit <ref> <ctx repo> <local|branch> <label>: queue the commit <ref> names, or mark the command
# unjudgeable. `local`: a ref of THIS checkout (what `git push <src>:main` and `git merge <ref>` carry).
# `branch`: a ref of the repository the command acts on (a REST merge's `head`, a ref write's `sha`).
add_commit() {
  local c="" ref="$1"
  ctx_repo "$2"
  case "$3" in
    local) c="$(git rev-parse --verify -q "${ref}^{commit}" 2>/dev/null || true)" ;;
    *)
      if [ -z "$_R" ]; then
        c="$(git rev-parse --verify -q "refs/remotes/origin/${ref}^{commit}" 2>/dev/null || git rev-parse --verify -q "${ref}^{commit}" 2>/dev/null || true)"
        if [ -z "$c" ] && plain_ref "$ref"; then
          git fetch -q --end-of-options origin "$ref" 2>/dev/null && c="$(git rev-parse --verify -q 'FETCH_HEAD^{commit}' 2>/dev/null || true)"
        fi
      else
        # Another repository: the ref becomes part of an API path, so it is a plain name, as on the local path above.
        # `#` is a legal character in a ref name and starts a fragment in a URL: the gate would ask about `abc` while the
        # command acts on `abc#frag`. A ref that is not plain is left unresolved, and the command is denied (#1606).
        ! plain_ref "$ref" || c="$(gh_lookup api "repos/${_R}/commits/${ref}" -q .sha || true)"
      fi ;;
  esac
  if [ -n "$c" ]; then add_ship "$c" "${_R:--}" "$4"; else unresolved_pr=1; fi
}
# note_pr <ctx repo>: act on base/head/_PRR. The certification must be for the commit the PR merges, so
# a PR whose base or head cannot be resolved is DENIED (#1569): judging it at dev's tip would certify a
# commit the merge may not contain. A PR into any other branch is not a promotion.
# split_match <payload>: a classifier payload may end in ` MATCH:<value>` (#1571), the commit the command pins as
# the head it expects. Sets _PMG (1 when it pins one), _PM (the value; `-` when the command's own text could not
# name it) and _SPLIT_REST (the payload without it).
split_match() {
  case "$1" in
    *MATCH:*) _PMG=1; _PM="${1##*MATCH:}"; _SPLIT_REST="${1%%MATCH:*}"; _SPLIT_REST="${_SPLIT_REST% }" ;;
    *) _PMG=0; _PM=""; _SPLIT_REST="$1" ;;
  esac
}
# pin_head <head>: a merge into main must pin the head THIS gate judged (#1571). The gate reads the head, then
# GitHub merges whatever the head is a moment later: a commit pushed to the PR in between would ride on the
# certification. `--match-head-commit` (or `sha=` / `expectedHeadOid`) makes GitHub refuse unless the head is still
# the commit that was judged. A short value counts only as a prefix of the judged head, at least 7 hex digits (git's
# own abbreviation floor), compared without regard to case. The denial prints the exact command to run.
pin_head() {
  local h="$1" m fix
  m="$(printf '%s' "$_PM" | tr 'A-F' 'a-f')"
  if [ "$_PMG" = 1 ] && [ "${#m}" -ge 7 ]; then
    case "$m" in *[!0-9a-f]*) ;; *) case "$h" in "$m"*) return 0 ;; esac ;; esac
  fi
  case "${_PINKIND:-cli}" in
    api) fix="Add -f sha=${h} to the gh api call." ;;
    gql) fix="Set expectedHeadOid: \"${h}\" in the mutation's input." ;;
    *)   fix="Run it as: gh pr merge ${_PINSEL:+${_PINSEL} }--match-head-commit ${h}   (keep your other flags)." ;;
  esac
  # Recorded, not denied here: the marketplace's own repo and the audited QA_ALLOW_MAIN override are decided AFTER
  # classification, and either must still be able to let this merge through. The denial is made where the stamp is
  # judged, once both have been read.
  [ -n "${pin_fail:-}" ] || pin_fail="this merges a pull request into ${base} without pinning the head the gate judged (${h:0:12}), so a commit pushed to the PR between this check and the merge would ride on that certification. ${fix}"
}
note_pr() {
  case "$base" in
    main|master)
      targets_main=1
      if [ -n "$head" ]; then ctx_repo "${_PRR:--}"; add_ship "$head" "${_R:--}" "the PR head"; pin_head "$head"; else unresolved_pr=1; fi ;;
    "") targets_main=1; unresolved_pr=1 ;;
  esac
}
if [ "$_mentions" = 1 ] && [ -f "$_pt" ]; then
  # `LC_ALL=C`: under a UTF-8 locale the classifier decodes strictly and an invalid byte anywhere in the command made it fail, which this gate reads as
  # "could not judge" and refuses (a harmless `git status` too, with a misleading message). In the C locale it reads the bytes and judges the command.
  if _found="$(printf '%s' "$cmd" | LC_ALL=C python3 "$_pt" --classify 2>/dev/null)"; then
    while IFS= read -r _line; do
      case "$_line" in
        "CTX "*)
          # Where the NEXT effect runs and which repository it acts on. A `cd` or `git -C` moves where
          # this hook must read the stamp; two different places cannot be judged by one checkout.
          _rest="${_line#CTX }"; _crepo="${_rest%% *}"; _cdir="${_rest#* }"
          if [ -z "$_dir_seen" ]; then
            _dir_seen="$_cdir"
            if [ "$_cdir" != "-" ]; then cd "$_cdir" 2>/dev/null || unresolved_pr=1; fi
          elif [ "$_dir_seen" != "$_cdir" ]; then
            unresolved_pr=1
          fi ;;
        "PUSH_MAIN "*)
          # No explicit source: `git push origin main` ships the LOCAL branch main, so that commit is what
          # must be certified -- not dev's tip (#1569: a cherry-pick onto main rode dev's stamp). `--all`,
          # `--mirror` and `:` push every local branch, main included: judge each of main/master that
          # exists, and deny when neither does.
          targets_main=1
          _d="${_line#PUSH_MAIN }"
          case "$_d" in
            main|master) add_commit "refs/heads/${_d}" "$_crepo" local "the commit being merged or pushed" ;;
            *) _n=0
               for _b in main master; do
                 if git rev-parse --verify -q "refs/heads/${_b}^{commit}" >/dev/null 2>&1; then
                   add_commit "refs/heads/${_b}" "$_crepo" local "the commit being merged or pushed"; _n=1
                 fi
               done
               [ "$_n" = 1 ] || unresolved_pr=1 ;;
          esac ;;
        GIT_PULL_MAIN)
          # (#1571) The same, on main by the COMMAND'S OWN doing: `git switch main && git pull`. The hook's HEAD
          # is read before the command runs, so the classifier says it outright.
          targets_main=1; unresolved_pr=1 ;;
        GIT_PULL)
          # `git pull` on main merges commits that are not fetched yet, so no commit can be named: deny.
          if grep -qE '^(main|master)$' <<<"$(git rev-parse --abbrev-ref HEAD 2>/dev/null)"; then targets_main=1; unresolved_pr=1; fi ;;
        "PUSH_REF "*)
          # #1569: `git push <remote> <src>:main` ships <src>, so <src> is what must be certified.
          targets_main=1; add_commit "${_line#PUSH_REF }" "$_crepo" local "the commit being merged or pushed" ;;
        GIT_MERGE_MAIN*)
          # (#1571) `git switch main && git merge <ref>`: on main by the command's own doing, whatever HEAD was
          # when the hook read it. Judged exactly like a merge on main.
          targets_main=1
          _refs="${_line#GIT_MERGE_MAIN}"; _refs="${_refs# }"
          [ -n "$_refs" ] || _refs='@{upstream}'
          for _r in $_refs; do add_commit "$_r" "-" local "the commit being merged or pushed"; done ;;
        GIT_MERGE*)
          # #1569: `git merge <ref>` on main brings in <ref>'s commit (bare = the upstream; --continue =
          # MERGE_HEAD). An unresolvable ref denies. Off main it is not a promotion.
          if grep -qE '^(main|master)$' <<<"$(git rev-parse --abbrev-ref HEAD 2>/dev/null)"; then
            targets_main=1
            _refs="${_line#GIT_MERGE}"; _refs="${_refs# }"
            [ -n "$_refs" ] || _refs='@{upstream}'
            for _r in $_refs; do add_commit "$_r" "-" local "the commit being merged or pushed"; done
          fi ;;
        PR_MERGE*)
          # The PR the command NAMES (number, URL or branch); bare = the current branch's PR.
          _sel="${_line#PR_MERGE}"; _sel="${_sel# }"
          split_match "$_sel"; _sel="$_SPLIT_REST"; _PINKIND=cli; _PINSEL="$_sel"
          resolve_pr "$_sel" "$_crepo"; note_pr ;;
        "API_PR_MERGE "*)
          # #1569: `gh api -X PUT .../pulls/N/merge`; `-` = a number the command does not spell out.
          _n="${_line#API_PR_MERGE }"
          split_match "$_n"; _n="$_SPLIT_REST"; _PINKIND=api; _PINSEL=""
          if [ "$_n" = "-" ]; then base=""; head=""; else resolve_pr "$_n" "$_crepo"; fi
          note_pr ;;
        "API_MERGE "*|"API_REF "*)
          # #1569: a REST merge into main, or a write of main's ref: judged by the commit it WRITES (`head`,
          # `sha`, `oid`), not by dev's tip. Unknown denies.
          targets_main=1; _v="${_line#* }"
          if [ "$_v" = "-" ]; then unresolved_pr=1; else add_commit "$_v" "$_crepo" branch "the commit being merged or pushed"; fi ;;
        "GQL_PR "*)
          # #1569: GraphQL mergePullRequest names a node id; ask GitHub which PR, base and head it is.
          _id="${_line#GQL_PR }"; split_match "$_id"; _id="$_SPLIT_REST"; _PINKIND=gql; _PINSEL=""
          base=""; head=""; _PRR=""
          if [ "$_id" != "-" ]; then
            _out="$(gh_lookup api graphql -F id="$_id" -f query='query($id:ID!){node(id:$id){... on PullRequest{baseRefName headRefOid baseRepository{nameWithOwner}}}}' -q '.data.node.baseRefName + " " + .data.node.headRefOid + " " + .data.node.baseRepository.nameWithOwner' 2>/dev/null || true)"
            base="${_out%% *}"; _out="${_out#* }"; head="${_out%% *}"; _PRR="$(printf '%s' "${_out#* }" | tr 'A-Z' 'a-z')"
            sane_pr_lookup   # #1626: a base that is not a ref name, or a head that is not a commit, is no answer
          fi
          note_pr ;;
        "GQL_REF "*)
          # #1569: GraphQL updateRef names a ref node id and the commit it moves it to (`oid`).
          _rest="${_line#GQL_REF }"; _id="${_rest%% *}"; _oid="${_rest#* }"
          _out=""
          [ "$_id" = "-" ] || _out="$(gh_lookup api graphql -F id="$_id" -f query='query($id:ID!){node(id:$id){... on Ref{name repository{nameWithOwner}}}}' -q '.data.node.name + " " + .data.node.repository.nameWithOwner' || true)"
          ref_name_returned "${_out%% *}" || _out=""   # #1626: a lookup that printed anything but a ref name first is no answer
          case "$(short_ref "${_out%% *}")" in
            main|master)
              targets_main=1
              if [ "$_oid" = "-" ]; then unresolved_pr=1
              else add_commit "$_oid" "$(printf '%s' "${_out#* }" | tr 'A-Z' 'a-z')" branch "the commit being merged or pushed"; fi ;;
            "") targets_main=1; unresolved_pr=1 ;;
          esac ;;
        "RELEASE "*) ctx_repo "$_crepo"; releases="${releases}${_line#RELEASE } ${_crepo}"$'\n' ;;
        "RELEASE_EDIT "*)
          # #1569: `gh release edit <tag> --draft=false` publishes. The tag a draft will get does not exist
          # yet, so the target is the one the release records: ask GitHub (the same -R, the same directory).
          _rest="${_line#RELEASE_EDIT }"; _tag="${_rest%% *}"; _tgt="${_rest#* }"
          if [ "$_tgt" = "-" ]; then
            ctx_repo "$_crepo"
            _a=(release view "$_tag"); [ -z "$_R" ] || _a+=(-R "$_R")
            _tgt="$(gh_lookup "${_a[@]}" --json targetCommitish -q .targetCommitish || true)"
            if [ -z "$_tgt" ]; then unresolved_pr=1; targets_main=1; _tgt="-"; fi
          fi
          releases="${releases}${_tag} ${_tgt} ${_crepo}"$'\n' ;;
        "RELEASE_ID "*)
          # #1569: `gh api PATCH .../releases/<id>` with draft false. The id names no tag; ask GitHub.
          _id="${_line#RELEASE_ID }"
          ctx_repo "$_crepo"
          _rp="$_R"; [ -n "$_rp" ] || _rp='{owner}/{repo}'
          _out="$(gh_lookup api "repos/${_rp}/releases/${_id}" -q '.tag_name + " " + .target_commitish' || true)"
          case "$_out" in
            "") unresolved_pr=1; targets_main=1 ;;
            *) _tag="${_out%% *}"; _tgt="${_out#* }"; [ -n "$_tgt" ] || _tgt="-"
               releases="${releases}${_tag:--} ${_tgt} ${_crepo}"$'\n' ;;
          esac ;;
      esac
    done <<EOF_FOUND
$_found
EOF_FOUND
  else
    targets_main=1; needs_dev=1
    # #1569: a command the classifier could not read (a body file that is missing or on stdin, a path
    # or command word built by the shell, an ANSI-C string it cannot decode) may merge ANY commit in ANY
    # repository, so dev's stamp proves nothing about it: deny, rather than judge it at dev's tip.
    unresolved_pr=1
  fi
elif [ "$_mentions" = 1 ]; then
  # The classifier is missing: the pre-#1410 detection, with the whole-word match over the RAW
  # command so a quoted `"main"` is still seen. Over-blocks a `-main` branch name; never under-blocks
  # what it used to catch.
  # `LC_ALL=C` on each grep: BSD grep stops at an invalid byte in a UTF-8 locale, so a push on a LATER line of the same command read as no match.
  # The normaliser could not be read (above): over-blocks a command that is only comments, never under-blocks one it lost.
  [ "$_seg_unread" = 1 ] && { targets_main=1; needs_dev=1; unresolved_pr=1; }
  # #1720: THE RAW COMMAND TOO. The normaliser splits a command substitution into its own segment, so `git -C $(pwd) push origin
  # main` reaches here as `git` | `pwd` | `push origin main` (and a quoted `"$(pwd)"` loses `push` altogether): no segment starts
  # with `git push`, and the push to main was allowed. `git` and `push` as whole words anywhere in the raw command count as a push;
  # this over-blocks a command that only mentions them, never under-blocks one that runs it.
  _raw_git() { LC_ALL=C grep -qE "(^|[^[:alnum:]_.-])git([^[:alnum:]_.-]|\$)" <<<"$cmd" && LC_ALL=C grep -qE "(^|[^[:alnum:]_.-])$1([^[:alnum:]_.-]|\$)" <<<"$cmd"; }
  { LC_ALL=C grep -qE '^[[:space:]]*git[[:space:]]+push\b' <<<"$seg" || _raw_git push; } \
    && LC_ALL=C grep -qE '\b(main|master)\b' <<<"$cmd" && { targets_main=1; needs_dev=1; }
  { LC_ALL=C grep -qE '^[[:space:]]*git[[:space:]]+merge\b' <<<"$seg" || _raw_git merge; } \
    && LC_ALL=C grep -qE '^(main|master)$' <<<"$(git rev-parse --abbrev-ref HEAD 2>/dev/null)" && { targets_main=1; needs_dev=1; }
  if LC_ALL=C grep -qE '^[[:space:]]*gh[[:space:]]+pr[[:space:]]+merge\b' <<<"$seg"; then
    num="$(printf '%s' "$seg" | LC_ALL=C grep -oE '(^|[[:space:]])[0-9]+([[:space:]]|$)' | tr -d ' ' | head -1)"
    resolve_pr "$num" "-"; note_pr
  fi
  # #1569: without the classifier a `gh api` write or a release cannot be read, so it is a promotion.
  LC_ALL=C grep -qE '^[[:space:]]*gh[[:space:]]+(api|release[[:space:]]+(create|edit))\b' <<<"$seg" \
    && LC_ALL=C grep -qiE 'merge|refs|releases|release[[:space:]]+(create|edit)|mutation' <<<"$cmd" && { targets_main=1; needs_dev=1; }
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
# The discriminator is the repository's REAL identity, not a file the command or an earlier command can
# create: `.claude-plugin/marketplace.json` is what makes a tree a marketplace, but any repo can add one, so
# it exempts only a checkout whose `origin` is the marketplace's own repository (#1569). A command that also
# acts on ANOTHER repository (`-R`, GH_REPO, a remote) is never exempt: the exemption describes this checkout.
MARKETPLACE_REPO="fmanimashaun/claude-skills"
# (#1571 review) The CONFIGURED origin url is not where a command goes: `remote.origin.pushurl`, `url.X.pushInsteadOf`
# and `url.X.insteadOf` each send a push, merge or release to another repository while `remote.origin.url` still
# names the marketplace, and gh acts on its resolved default repository (`remote.*.gh-resolved`, GH_REPO), not on
# origin. So the exemption holds only when EVERY target the command could reach is the marketplace: every remote's
# fetch and push url as git resolves them (`git remote get-url [--push] --all`), every gh-resolved repository, and
# GH_REPO. One that is another repository, or that cannot be read (an empty or unrecognisable value never equals the
# marketplace), withdraws it: fail closed, never "probably origin".
only_marketplace_targets() {
  local r u v mode
  [ "$(repo_of_url "$(git config --get remote.origin.url 2>/dev/null || true)")" = "$MARKETPLACE_REPO" ] || return 1
  while IFS= read -r r; do
    [ -n "$r" ] || continue
    for mode in "" "--push"; do
      u="$(git remote get-url $mode --all "$r" 2>/dev/null)"
      while IFS= read -r v; do
        [ "$(repo_of_url "$v")" = "$MARKETPLACE_REPO" ] || return 1
      done <<EOF
$u
EOF
    done
  done <<EOF
$(git remote 2>/dev/null)
EOF
  while IFS= read -r v; do
    case "$v" in ""|base|other) ;; *) [ "$(printf '%s' "$v" | tr 'A-Z' 'a-z')" = "$MARKETPLACE_REPO" ] || return 1 ;; esac
  done <<EOF
$(git config --get-regexp '^remote\..*\.gh-resolved$' 2>/dev/null | awk '{print $2}')
EOF
  [ -z "${GH_REPO:-}" ] || [ "$(printf '%s' "$GH_REPO" | tr 'A-Z' 'a-z')" = "$MARKETPLACE_REPO" ] || return 1
  return 0
}
if [ -f ".claude-plugin/marketplace.json" ] && [ -z "$_foreign" ] && only_marketplace_targets; then
  echo "qa-flow: this is the marketplace repo itself, which ships qa-flow rather than consuming it — release gate not applicable." >&2
  exit 0
fi

# The override is read from THIS PROCESS's environment only. The command's own text cannot set it: an
# inline `QA_ALLOW_MAIN=1 gh ...`, `env QA_ALLOW_MAIN=1 ...` or `export QA_ALLOW_MAIN=1; ...` runs AFTER
# this hook, in a shell that is not the hook's, so none of them is read here (#1569).
[ "${QA_ALLOW_MAIN:-0}" = "1" ] && { echo "qa-flow: QA_ALLOW_MAIN=1 override — promotion allowed without a fresh stamp (audited)." >&2; exit 0; }

# (#1571) A merge into main that does not pin the head the gate judged (see pin_head). Denied only now, after the
# marketplace exemption and the override above had their say.
[ -z "${pin_fail:-}" ] || deny "$pin_fail"

# The STAMP is read as COMMITTED, never from this checkout's working tree: main receives what is
# committed, so an uncommitted or locally edited stamp certifies nothing that will ship (#1437 review,
# round 3).
stamp_tmp="$(mktemp 2>/dev/null || printf '%s' "${TMPDIR:-/tmp}/qa-certification.$$")"
evtmp="$(mktemp 2>/dev/null || printf '%s' "${TMPDIR:-/tmp}/qa-release-evidence.$$")"
trap 'rm -f "$stamp_tmp" "$evtmp"' EXIT
reader="${CLAUDE_PLUGIN_ROOT:-}/scripts/read_certification.py"
ev="${CLAUDE_PLUGIN_ROOT:-}/scripts/release_evidence.py"
JWHY=""

# extra_files <evidence paths>: reads changed paths on stdin and prints those that are neither the stamp nor
# evidence the stamp names. ONE definition for this checkout and for another repository (#1591): the delta
# since the certified commit may be the stamp and the evidence it names, and nothing else.
extra_files() {
  local evidence="$1" f p ok
  while IFS= read -r f; do
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
  done
}

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
  # (#1600) The stamp is data from the repository being promoted: its sha is a commit id, never an option or a path.
  case "$csha" in *[!0-9a-fA-F]*) JWHY="certification sha is not a commit id (${csha:0:20}) — the stamp is invalid. Re-run /qa-flow:certify."; return 1 ;; esac
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
      extra="$(printf '%s\n' "$delta" | extra_files "$evidence")"
      if [ -n "$extra" ]; then
        JWHY="certification is for sha ${csha:0:12}; ${what} (${tgt:0:12}) has changed more than the stamp since: $(printf '%s' "$extra" | head -3 | tr '\n' ' '). Re-certify before promoting."; return 1
      fi
      ;;
  esac
  echo "qa-flow: certification valid for ${csha:0:12} — ${what} ${tgt:0:12} permitted." >&2
  return 0
}

# bounded <seconds> <command...>: run a command that talks to the network and stop it when the time is up (exit 124).
# A PreToolUse hook that outlives its timeout (15 s) does not deny, it lets the command through, so a call that can
# stall (`gh api`) must be cut short here and read as a failure, which every caller turns into a denial (#1591).
bounded() {
  python3 -c 'import subprocess, sys
try:
    done = subprocess.run(sys.argv[2:], capture_output=True, timeout=float(sys.argv[1]), stdin=subprocess.DEVNULL)
except subprocess.TimeoutExpired:
    sys.exit(124)
except OSError:
    sys.exit(127)
sys.stdout.buffer.write(done.stdout)
sys.stderr.buffer.write(done.stderr)
sys.exit(done.returncode)' "$@"
}
# judge_remote <sha> <owner/repo> <what>: the stamp of a repository this checkout is NOT, read through the
# API at that sha (#1569). It needs the stamp at the sha to be PASS and to certify it exactly, or to sit
# on top of the tested sha with nothing else changed but the stamp and the evidence it names. The release-only
# layers (#1428) are judged exactly as for this checkout, from the evidence committed in THAT repository:
# remote_evidence.py fetches the commit into a scratch repository and runs release_evidence.py there (#1591),
# inside the time the hook has left, because a hook that outlives its timeout (15 s, hooks.json) does not deny: it
# lets the command through. The whole gate also runs under a deadline (#1575, `_deadline_s`, 13 s by default since #1607, 10 s before), past which
# its process group is killed and a promotion refused. So the helper runs LAST, after the cheap API calls, with what is
# left of that deadline minus 2 s (never more than 8), so ITS denial speaks first, and a command that has no time left is
# denied. Several ships in one command share that one deadline.
judge_remote() {
  local sha="$1" repo="$2" what="$3" verdict csha why cmp status files evidence budget
  # (#1610) The commit id comes from GitHub's answer, not from the command, and it is joined into a URL below: it is a commit id.
  case "$sha" in ""|*[!0-9a-fA-F]*) JWHY="${repo}: ${what} (${sha:0:20}) is not a commit id, so its certification cannot be read."; return 1 ;; esac
  if ! bounded 4 gh api -H 'Accept: application/vnd.github.raw+json' "repos/${repo}/contents/qa/CERTIFICATION?ref=${sha}" >"$stamp_tmp" 2>/dev/null; then
    JWHY="this command acts on ${repo}, not on this checkout's repository, and its qa/CERTIFICATION could not be read at ${what} (${sha:0:12}) through the GitHub API. Run it from a checkout of ${repo} that holds a PASS stamp, or set QA_ALLOW_MAIN=1."
    return 1
  fi
  verdict="$(python3 "$reader" --stamp "$stamp_tmp" --field verdict 2>/dev/null || true)"
  csha="$(python3 "$reader" --stamp "$stamp_tmp" --field sha 2>/dev/null || true)"
  if [ -z "$verdict" ]; then
    why="$(python3 "$reader" --stamp "$stamp_tmp" --field verdict --explain 2>/dev/null || true)"
    JWHY="${repo}: ${why:-certification verdict could not be read. Re-certify.}"; return 1
  elif [ "$verdict" != "PASS" ]; then
    JWHY="${repo}: certification verdict is ${verdict}, not PASS. Fix the defects and re-certify."; return 1
  fi
  [ -n "$csha" ] || { JWHY="${repo}: certification has no sha — the stamp is invalid. Re-run /qa-flow:certify."; return 1; }
  case "$csha" in *[!0-9a-fA-F]*) JWHY="${repo}: certification sha is not a commit id (${csha:0:20}) — the stamp is invalid. Re-run /qa-flow:certify."; return 1 ;; esac
  # The cheap API call first: how the judged commit relates to the certified one.
  cmp=""
  case "$sha" in
    "$csha"*) : ;;
    *)
      if ! cmp="$(bounded 4 gh api "repos/${repo}/compare/${csha}...${sha}" --jq '.status, (.files[].filename)' 2>/dev/null)"; then
        JWHY="${repo}: certification is for sha ${csha:0:12}, and ${what} (${sha:0:12}) could not be compared with it through the GitHub API. Re-certify."; return 1
      fi
      status="$(printf '%s\n' "$cmp" | head -1)"
      case "$status" in ahead|identical) : ;; *)
        JWHY="${repo}: certification is for sha ${csha:0:12}, which is not an ancestor of ${what} (${sha:0:12}). ${what} moved — re-certify before promoting."; return 1 ;;
      esac ;;
  esac
  # (#1591) The release-only layers (#1428), as for this checkout, judged LAST and inside the time the hook has left
  # (SECONDS counts from the hook's start). Fail-closed: any error, and no time, denies.
  budget=$(( ${_deadline_s:-12} - 2 - SECONDS )); [ "$budget" -le 8 ] || budget=8
  if [ "$budget" -lt 3 ]; then
    JWHY="${repo}: there is no time left in this hook to judge the release-only layers (#1428) of ${what} (${sha:0:12}): the command acts on too many commits or repositories at once. Split it."; return 1
  fi
  if evidence="$(python3 "${CLAUDE_PLUGIN_ROOT:-}/scripts/remote_evidence.py" --repo "$repo" --sha "$sha" --budget "$budget" 2>"$evtmp")"; then
    grep '^WARNING' "$evtmp" | sed "s|^WARNING |qa-flow: ${repo}: |" >&2
  else
    why="$(grep -E '^(FAIL|unusable)' "$evtmp" 2>/dev/null | head -3 | tr '\n' ' ')"
    JWHY="${repo}: the release-only layers do not pass (#1428): ${why:-remote_evidence.py could not run.} Fix them and re-certify."; return 1
  fi
  # What changed since the certified commit may be the stamp and the evidence it names, and nothing else.
  files="$(printf '%s\n' "$cmp" | sed 1d | extra_files "$evidence" | head -3 | tr '\n' ' ')"
  if [ -n "$files" ]; then
    JWHY="${repo}: certification is for sha ${csha:0:12}; ${what} (${sha:0:12}) has changed more than the stamp since: ${files}. Re-certify before promoting."; return 1
  fi
  echo "qa-flow: ${repo}: certification valid for ${csha:0:12} — ${what} ${sha:0:12} permitted." >&2
  return 0
}
# judge_in <sha> <repo or -> <what>
judge_in() { if [ "$2" = "-" ]; then judge "$1" "$1" "$3"; else judge_remote "$1" "$2" "$3"; fi; }

# (0) A command whose commit, PR, ref, release or repository could not be resolved cannot be matched to a
# stamp: deny (#1569). Decided here, after the override and the marketplace exemption.
[ -z "$unresolved_pr" ] || deny "cannot tell which commit or repository this command merges or publishes (a PR, ref, release or repository could not be resolved, a query or body file could not be read, or the command could not be parsed), so no certification can be matched to it. Name the PR by number, give a readable file, authenticate gh, and retry."

# (1) dev's tip: a push of `main` to this repo's own remote with no explicit source.
if [ "$needs_dev" = 1 ]; then
  # `--verify -q` prints NOTHING for a missing ref; plain `rev-parse origin/dev` echoes the literal
  # "origin/dev" before failing (found by the #1337 fixtures).
  devsha="$(git rev-parse --verify -q origin/dev 2>/dev/null || git rev-parse --verify -q dev 2>/dev/null || true)"
  [ -n "$devsha" ] || deny "cannot resolve dev sha to compare against the certification. Fetch dev and retry."
  judge "$devsha" "$devsha" dev || deny "$JWHY"
fi

# (2) #1569: every commit the command puts on main -- a PR's HEAD (a hotfix by its own stamp, not dev's), the
# commit a `<src>:main` push or a `git merge <ref>` carries, the `head` of a REST merge, the `sha` of a ref
# write -- judged in the repository it goes to.
while IFS=$'\t' read -r _c _crp _lab; do
  [ -n "$_c" ] || continue
  if [ "$_crp" = "-" ] && ! git cat-file -e "${_c}^{commit}" 2>/dev/null; then
    git fetch -q --end-of-options origin "$_c" 2>/dev/null || true       # an object id by construction (#1600)
    git cat-file -e "${_c}^{commit}" 2>/dev/null || deny "${_lab} ${_c:0:12} is not in this clone and could not be fetched, so its certification cannot be read. Fetch it and retry."
  fi
  judge_in "$_c" "$_crp" "$_lab" || deny "$JWHY"
done <<EOF_SHIP
$ship
EOF_SHIP

# (3) #1569: publishing. In a consumer the release is the step that builds and ships the image, so it
# needs a PASS stamp for the exact commit it publishes, resolved the way GitHub resolves it: a tag that
# ALREADY EXISTS on the remote wins and `--target` is ignored; else `--target`; else the default branch.
# (A tag only in this clone is not the remote's; gh refuses to publish it without a target.)
default_tip() {
  local r
  r="$(git symbolic-ref -q refs/remotes/origin/HEAD 2>/dev/null || true)"
  [ -z "$r" ] || { git rev-parse --verify -q "${r}^{commit}" 2>/dev/null && return 0; }
  for r in refs/remotes/origin/main refs/remotes/origin/master refs/heads/main refs/heads/master; do
    git rev-parse --verify -q "${r}^{commit}" 2>/dev/null && return 0
  done
  return 1
}
# resolve_release <tag> <target> (with _R set by ctx_repo): sets _rsha. Returns 1 when it cannot say.
resolve_release() {
  local tag="$1" tgt="$2" o t
  _rsha=""
  if [ -z "$_R" ]; then
    # (#1610) A tag becomes a `git ls-remote` PATTERN below, and a pattern takes a glob (`v*` lists every v tag).
    [ -z "$tag" ] || plain_ref "$tag" || return 1
    if [ -n "$tag" ] && git remote get-url origin >/dev/null 2>&1; then
      o="$(git ls-remote origin "refs/tags/${tag}" "refs/tags/${tag}^{}" 2>/dev/null)" || return 1
      if [ -n "$o" ]; then
        t="$(printf '%s\n' "$o" | awk '$2 ~ /\^\{\}$/ {p=$1} $2 !~ /\^\{\}$/ {d=$1} END {print (p != "" ? p : d)}')"
        # What `git ls-remote` printed goes to `git fetch` below: it must be an object id, whatever the origin says (#1606).
        case "$t" in ""|*[!0-9a-fA-F]*) return 1 ;; esac
        _rsha="$(git rev-parse --verify -q "${t}^{commit}" 2>/dev/null || true)"
        if [ -z "$_rsha" ]; then
          git fetch -q --end-of-options origin "$t" 2>/dev/null || true
          _rsha="$(git rev-parse --verify -q "${t}^{commit}" 2>/dev/null || true)"
        fi
        [ -n "$_rsha" ]; return
      fi
    fi
    if [ -n "$tgt" ]; then
      _rsha="$(git rev-parse --verify -q "refs/remotes/origin/${tgt}^{commit}" 2>/dev/null || git rev-parse --verify -q "${tgt}^{commit}" 2>/dev/null || true)"
    elif [ -n "$tag" ] && git rev-parse --verify -q "refs/tags/${tag}^{commit}" >/dev/null 2>&1; then
      _rsha="$(git rev-parse --verify -q "refs/tags/${tag}^{commit}")"
    else
      _rsha="$(default_tip 2>/dev/null | head -1)"
    fi
  else
    # Another repository: a tag or target becomes part of an API path, so each is a plain name, else the commit cannot be
    # named (#1606). This is the same splice as add_commit's, three more times.
    [ -z "$tag" ] || plain_ref "$tag" || return 1
    [ -z "$tgt" ] || plain_ref "$tgt" || return 1
    if [ -n "$tag" ]; then
      o="$(gh api "repos/${_R}/git/matching-refs/tags/${tag}" --jq '.[].ref' 2>/dev/null)" || return 1
      if grep -qx "refs/tags/${tag}" <<<"$o"; then
        _rsha="$(gh_lookup api "repos/${_R}/commits/${tag}" --jq .sha || true)"; [ -n "$_rsha" ]; return
      fi
    fi
    if [ -n "$tgt" ]; then
      _rsha="$(gh_lookup api "repos/${_R}/commits/${tgt}" --jq .sha || true)"
    else
      t="$(gh_lookup api "repos/${_R}" --jq .default_branch || true)"
      plain_ref "$t" || t=""
      [ -z "$t" ] || _rsha="$(gh_lookup api "repos/${_R}/commits/${t}" --jq .sha || true)"
    fi
  fi
  [ -n "$_rsha" ]
}
while read -r _tag _tgt _rrp; do
  [ -n "$_tag" ] || continue
  [ "$_tag" = "-" ] && _tag=""; [ "$_tgt" = "-" ] && _tgt=""
  ctx_repo "${_rrp:--}"
  [ -z "$unresolved_pr" ] || deny "the repository this release is created in could not be resolved, so no certification can be matched to it."
  resolve_release "$_tag" "$_tgt" || deny "cannot resolve the commit release ${_tag:-<no tag>} would publish (target '${_tgt:-none}'${_R:+, repository $_R}). Fetch it, or pass --target <sha>."
  if [ -n "$_R" ]; then
    judge_remote "$_rsha" "$_R" "the release target" || deny "no PASS qa/CERTIFICATION covers the commit this release publishes (${_rsha:0:12}${_tag:+, tag $_tag}): ${JWHY}"
    continue
  fi
  _first=""; _ok=0
  # The stamp is read at the commit itself or at the REMOTE's main/dev. A local branch of the same name
  # is whatever the last command left there, so it counts only when there is no remote at all.
  _ats="$_rsha refs/remotes/origin/main refs/remotes/origin/dev"
  git remote get-url origin >/dev/null 2>&1 || _ats="$_ats refs/heads/main refs/heads/dev"
  for _at in $_ats; do
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
}

# THE DEADLINE (#1575). qa-flow's gate sources the same normaliser as guard-bash, and a normaliser that spins left
# awk children behind for hours. Past the deadline the whole process group is killed. This gate refuses only a
# main-ward promotion, so a timeout does too: the COARSE builtin detector above judges the raw payload; a command
# that does not look like a promotion is allowed (blocking every slow command would be the failure here), and one that
# does is denied, QA_ALLOW_MAIN=1 honoured and audited exactly as in the missing-tool path. The default is 13 s, under the
# hook's 15 s timeout (hooks.json), and RAILS_FLOW_HOOK_DEADLINE is clamped at 13. It was 10 until #1607: the foreign-repository judgment
# (#1612) plans for up to about 12 s of its own and bounds each of its calls, so the deadline must sit ABOVE that budget, where it only
# catches a call nobody bounded, and not cut a slow-but-bounded judgment off first with a less useful reason. The gate's NETWORK calls (`gh pr view`,
# and since #1601 `gh api .../commits/...`, `git fetch` of a ref the command names, and `git ls-remote` of a release tag) are
# reached only after the classifier has read the command as one that puts a commit on main or publishes a release, which
# are the shapes the coarse detector denies, so a slow network fails closed. It also means a legitimate promotion on a
# slow network is refused with "retry it", which is the cost of a bounded hook.
_dl="$(dirname "${BASH_SOURCE[0]}")/lib/deadline.sh"
if [ -f "$_dl" ] && . "$_dl" 2>/dev/null && type deadline_run >/dev/null 2>&1; then
  # The margin to the hook's 15 s timeout is about 1.85 s (measured at load 22 to 33: the deadline's denial arrives at 13.14 s). A timed-out hook
  # lets the command through, and the load that makes a hook time out is the load that makes this loop's one-second sleep drift: do not raise it.
  deadline_seconds 13 13
  deadline_run "$_deadline_s" _gate_main; _rc=$?
  if [ "$_rc" -ge 128 ]; then
    _coarse_looks_promotion
    if [ "$_looks_promotion" = "1" ]; then
      [ "${QA_ALLOW_MAIN:-0}" = "1" ] && { echo "qa-flow: the gate hit its ${_deadline_s}s deadline but QA_ALLOW_MAIN=1 — allowed (audited)." >&2; exit 0; }
      echo "BLOCKED by qa-flow release gate: the gate took longer than ${_deadline_s}s, and this command looks like a promotion to main, so it is refused rather than guessed at. Retry it; if it keeps timing out, run /qa-flow:certify and check the repo and network." >&2
      exit 2
    fi
    exit 0
  fi
  exit "$_rc"
fi
_gate_main
exit $?
