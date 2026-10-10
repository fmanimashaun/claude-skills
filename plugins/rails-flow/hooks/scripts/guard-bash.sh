#!/usr/bin/env bash
# PreToolUse[Bash] guardrails — mechanical enforcement of GUARDRAILS.md.
# Exit 2 blocks the command; stderr is shown to Claude with the reason.
set -uo pipefail
# The `read` BUILTIN, never `cat`: with no `cat` on PATH, `$(cat)` read nothing and every rule passed
# (#1529 review). Stops at a NUL, which JSON cannot contain.
input=""; IFS= read -r -d '' input || true

# #1575: EVERYTHING below runs in `_guard_main`, in its own process group, under a wall-clock deadline (lib/deadline.sh,
# at the bottom of this file). The body is not re-indented, to keep the diff reviewable.
_guard_main() {

# #1526: decoded with `surrogateescape`, so an invalid UTF-8 byte cannot make the parse fail. A failed
# parse left the raw JSON as `cmd`, where the command sits inside double quotes the normaliser strips:
# `git add -A \xff` was allowed.
parsed=1
cmd="$(printf '%s' "$input" | python3 -c 'import json,sys
d=json.loads(sys.stdin.buffer.read().decode("utf-8","surrogateescape"))
sys.stdout.buffer.write(str(d.get("tool_input",{}).get("command","")).encode("utf-8","replace"))' 2>/dev/null)" || { parsed=0; cmd="$input"; }

deny() { echo "BLOCKED by rails-flow guardrails: $1" >&2; exit 2; }

# MATCH THE INVOKED COMMAND, NOT ANY SUBSTRING (#906). The raw text blocked `grep -c "git add -A"
# GUARDRAILS.md`, `echo "never git add -A"` and a commit message quoting the rule, while
# `git -C repo add -A` slipped through. `seg` is one invoked segment per line, verb first, with
# quotes, comments and heredoc bodies stripped and env/sudo/git-global-option prefixes peeled.
# FAIL CLOSED: if the lib cannot be sourced, match the raw text as before — a guard that goes
# quiet because a file is missing is the one failure this hook must not have.
_lib="$(dirname "${BASH_SOURCE[0]}")/lib/normalize_cmd.sh"
#
# #1526: the lib needs awk, sed, tr and grep. Without awk it printed NOTHING, so every rule passed. An
# unparsed payload, a missing lib, or a normaliser that EXITED NON-ZERO puts the hook in DEGRADED mode.
# The exit status, not an empty result, decides: a comment-only command normalises to nothing and is a
# mention (#906). A missing tool needs no check of its own -- the shell's 127 fails the pipeline under
# `pipefail` and the lib returns it (#1529 review) -- and a `command -v` per tool changed no outcome,
# which the mutation guard measured. `LC_ALL=C`: macOS awk aborts on an invalid byte in a UTF-8 locale.
degraded=0
if [ "$parsed" = 1 ] && [ -f "$_lib" ] && . "$_lib" 2>/dev/null && type normalize_segments >/dev/null 2>&1; then
  seg="$(printf '%s' "$cmd" | LC_ALL=C normalize_segments)" || { seg="$cmd"; degraded=1; }
else
  seg="$cmd"; degraded=1
fi
# DEGRADED MEANS UNANCHORED (#1529 review). Every rule is anchored `^git`, and the raw text is the
# JSON payload or a compound command (`cd x && git add -A`), so an anchored rule never matched it and
# "fall back to the raw text" passed everything. In degraded mode a rule matches ANYWHERE: that refuses
# a quoted mention too, which is the right side to err on when the command could not be read. With no
# grep at all, bash's own `=~` matches (`\b` dropped, which only widens the match).
have_grep=0; command -v grep >/dev/null 2>&1 && have_grep=1
hit() {
  local re="$1"
  [ "$degraded" = 1 ] && re="${re#^}"
  if [ "$have_grep" = 1 ]; then
    # pipefail OFF inside the subshell: `grep -q` quits at the first match, `printf` takes SIGPIPE once the
    # text outgrows the pipe buffer, and pipefail reported that 141 as "no match" -- `git add -A` plus
    # 10k lines of echo was allowed. Only grep's own status may decide.
    ( set +o pipefail; printf '%s\n' "$seg" | grep -qE "$re" )
  else
    # LINE BY LINE, as grep matches: one `=~` over the whole text let `^` see only the first segment,
    # so `cd x && git add -A` passed with no grep (#1529 round-3 review).
    re="${re//\\b/}"
    # Split IN MEMORY, never through a heredoc: a heredoc needs a temp file, and with no writable temp
    # dir it failed and `hit()` passed everything (#1529 round-4 review).
    local rest="$seg"$'\n' line
    while [ -n "$rest" ]; do
      line="${rest%%$'\n'*}"; rest="${rest#*$'\n'}"
      [[ $line =~ $re ]] && return 0
    done
    return 1
  fi
}
# THE SAME MATCH OVER RAW TEXT, for the issue-label trigger (#1545). `hit()` reads the normalised `seg`, which strips the quotes the trigger needs to
# see, so the trigger matches the raw command. It has hit()'s no-grep path (bash's own `=~`, line by line, in memory): with no `grep` on PATH the
# trigger used to fail its pipeline, the `if` read false, and the label check never ran.
rawhit() {
  local text="$1" re="$2"
  if [ "$have_grep" = 1 ]; then
    ( set +o pipefail; printf '%s\n' "$text" | grep -qE "$re" )
  else
    local rest="$text"$'\n' line
    while [ -n "$rest" ]; do
      line="${rest%%$'\n'*}"; rest="${rest#*$'\n'}"
      [[ $line =~ $re ]] && return 0
    done
    return 1
  fi
}
# An EXEMPTION (`--force-with-lease`, clean's `-n`, restore's `--staged`) never applies in degraded
# mode: unanchored, its `.*` reaches another segment, so `git clean -fd && echo -n` was exempt (#1529
# review). Refusing a real dry run there is the price of a command that could not be read.
exempt() { [ "$degraded" = 1 ] && return 1; hit "$1"; }

# A rails/rake task segment that names db:reset (not the word inside a quoted string or a grep).
#
# #1734: THE RULE IS SITUATIONAL. "Seeds break test isolation" holds for a project whose suite expects an UNSEEDED test database. A project that
# seeds its test DB on purpose (Retask's config/ci.rb: the seeded Setting rows are part of the test contract) needs the opposite, and the
# sequence this message used to recommend (drop, create, schema:load) left it with 0 locations and 0 users and 158 failing specs. So a project
# DECLARES the choice, the way `mockup-gate: off` is declared: a line `test-db-seeded: yes` of its own in GUARDRAILS.md. Undeclared stays refused.
#
# WHAT A DECLARATION ALLOWS IS ONE COMMAND: `RAILS_ENV=test bin/rails db:reset` (or the `env`, `bundle exec`, `rake` and trailing-assignment spellings),
# and nothing else. It is matched against the WHOLE raw command, so a compound command that also resets the development database, `RAILS_ENV=development`,
# or an unreadable payload (degraded mode: the env prefix the normaliser peels is exactly what this must read) is still refused.
# `bundle exec` is part of the command (#1760 review): its verb is `bundle`, so a rule anchored on rails or rake never saw `bundle exec rails db:reset` at all.
if hit '^(bundle[[:space:]]+exec[[:space:]]+)?(bin/)?(rails|rake)([[:space:]]+[^[:space:]]+)*[[:space:]]+db:reset\b'; then
  _root="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
  _tab=$'\t'
  _seeded=0
  if [ -f "$_root/GUARDRAILS.md" ]; then
    # LINE BY LINE, SKIPPING CODE: a GUARDRAILS.md that EXPLAINS the declaration inside a fenced block (```, ~~~) or an indented one would otherwise
    # declare it by accident, and so would a quoted example (the same defect `mockup-gate: off` had to be fixed for). An unclosed fence hides the rest
    # of the file, which is the safe side. Pure bash, so it needs no grep and no awk.
    _guardrails="$(<"$_root/GUARDRAILS.md")" || _guardrails=""
    _re_fence='^[[:space:]]{0,3}(```|~~~)'
    _re_indented="^([[:space:]]{4,}|${_tab})"
    _re_declares='^[[:space:]]*([-*+][[:space:]]*)?`?test-db-seeded:[[:space:]]*yes`?[[:space:]]*$'
    _fenced=0; _commented=0
    while IFS= read -r _line || [ -n "$_line" ]; do
      # An HTML comment hides what is inside it, across lines: `<!--` opens it, the first `-->` closes it, and an unclosed one hides the rest.
      if [ "$_commented" = 1 ]; then
        [[ $_line == *'-->'* ]] && _commented=0
        continue
      fi
      if [[ $_line =~ $_re_fence ]]; then _fenced=$((1 - _fenced)); continue; fi
      [ "$_fenced" = 1 ] && continue
      if [[ $_line == *'<!--'* ]]; then
        _after_open="${_line#*<!--}"
        [[ $_after_open == *'-->'* ]] || _commented=1
        continue
      fi
      [[ $_line =~ $_re_indented ]] && continue
      if [[ $_line =~ $_re_declares ]]; then _seeded=1; break; fi
    done <<< "$_guardrails"
  fi
  # A SPACE OR A TAB, NEVER [[:space:]]: it matches a newline, and `=~` anchors only at the ends of the whole string, so `RAILS_ENV=test` + newline +
  # `bin/rails db:reset` (a bare assignment, then a DEVELOPMENT reset) matched as one command (#1760 review). With a space or a tab only, a newline or a return
  # can match no part of the pattern, so a command that holds one is refused.
  _s="[ ${_tab}]"
  _runner="((bundle${_s}+exec${_s}+)?(bin/)?(rails|rake))"
  _env_first="^${_s}*(env${_s}+)?RAILS_ENV=test${_s}+${_runner}${_s}+db:reset${_s}*\$"
  _env_last="^${_s}*${_runner}${_s}+db:reset${_s}+RAILS_ENV=test${_s}*\$"
  if [ "$_seeded" = 1 ] && [ "$degraded" = 0 ] && { [[ $cmd =~ $_env_first ]] || [[ $cmd =~ $_env_last ]]; }; then
    :   # declared, and exactly the test-database reset: allowed
  elif [ "$_seeded" = 1 ]; then
    deny "this project declares test-db-seeded in GUARDRAILS.md, so 'RAILS_ENV=test bin/rails db:reset' is allowed, run on its own. Any other db:reset (development, production, or inside a compound command) is refused."
  else
    _ci_hint=""
    if [ -f "$_root/bin/ci" ]; then
      _ci_hint=" If this project's suite needs a SEEDED test database, run bin/ci, which does its own reset."
    elif [ -f "$_root/config/ci.rb" ]; then
      _ci_hint=" If this project's suite needs a SEEDED test database, run its CI script (config/ci.rb), which does its own reset."
    fi
    deny "db:reset is prohibited (seeds break test isolation). Use: db:drop db:create db:schema:load.${_ci_hint} A project that seeds its test DB on purpose declares 'test-db-seeded: yes' in GUARDRAILS.md, which allows 'RAILS_ENV=test bin/rails db:reset'."
  fi
fi

# `--mirror` always forces (every ref made to match), with or without a lease (#1783 review).
if hit '^git[[:space:]]+push\b.*[[:space:]]--mirror\b'; then
  deny "git push --mirror force-updates and deletes every remote branch to match yours; it requires explicit user approval."
fi
# #1706: a bundled `-fu` and a `+<ref>` refspec force as surely as `-f`, the `+` leading the refspec or after its colon (`HEAD:+main`).
if hit '^git[[:space:]]+push\b.*([[:space:]]--force\b|[[:space:]]-[a-zA-Z]*f[a-zA-Z]*\b|[[:space:]]\+[^[:space:]]|:\+[^[:space:]])' && ! exempt '^git[[:space:]]+push\b.*--force-with-lease'; then
  deny "force-push is prohibited. Use --force-with-lease on your own feature branch only, never on main/dev/staging."
fi
# #1708: the protected branch is a whole ref (`main`, `HEAD:main`, `+dev`, `refs/heads/staging`), not the word inside `feature/main-menu`.
# #1708 scope (#1783 review): deleting a protected branch on the remote, `git push origin :main` or `--delete main`.
if hit '^git[[:space:]]+push\b.*([[:space:]]:|=)(refs/heads/)?(main|master|dev|staging)([[:space:]]|$)' \
   || { hit '^git[[:space:]]+push\b.*[[:space:]](--delete|-d)(\b|=)' && hit '^git[[:space:]]+push\b.*[[:space:]](refs/heads/)?(main|master|dev|staging)([[:space:]]|$)'; }; then
  deny "deleting a protected branch (main/dev/staging) on the remote requires explicit user approval."
fi
# `--all` and `--mirror` push every branch, the protected ones included (#1783 review).
if hit '^git[[:space:]]+push\b.*--force-with-lease' && { hit '^git[[:space:]]+push\b.*([[:space:]]|:|\+)(refs/heads/)?(main|master|dev|staging)([[:space:]]|$)' \
   || hit '^git[[:space:]]+push\b.*[[:space:]]--(all|mirror)\b'; }; then
  deny "force-pushing a protected branch (main/dev/staging) requires explicit user approval."
fi

# Leading short flags are allowed through (`-v -A`), `-A` may sit inside a bundle (`-vA`), and the
# repo-root spellings `./` and `:/` count as `.` (#826). Verb at the START of a segment (#906).
# #1706: long options and `--` may come first too (`add --verbose -A`, `add -- .`).
# `git add` IS AN ALLOWLIST (#1783, the coordinator's decision after three review rounds): a list of whole-tree spellings could not
# be completed (`./.`, `**`, `:(top)`, `:!x`, `$PWD`, `{.,x}`, `--pathspec-from-file` each got past one). So a `git add` passes only
# when every option is one of -u -p -N -v (and their long forms) or `--`, and every pathspec is a plain relative path: no magic `:`
# prefix, no `**`, no `..` that reaches the root or above, a glob only in its LAST component and only with a letter or digit in it
# (`src/*.rb`, `*.md`). Shell expansion (`$`, a backtick, `{`, `}`, `~`) anywhere in a command that holds a `git add` refuses: the
# normaliser splits a substitution into its own segment, so the pathspec it produces is invisible here. Bash only, over the
# normalised segments. The degraded path (no normaliser) keeps the spelled rule below, and refusing more there is S9's (#1710).
_add_refused() {
  [ "$degraded" = 1 ] && return 1
  local line w opts p comp depth n last
  # Only the `git add` lines are walked: a bash loop over every line of a 10k-line command ran past the hook's deadline (#1783).
  local rest any=0
  if [ "$have_grep" = 1 ]; then rest="$(printf '%s\n' "$seg" | LC_ALL=C grep -E '^git[[:space:]]+add([[:space:]]|$)')"$'\n'; else rest="$seg"$'\n'; fi
  while [ -n "$rest" ]; do
    line="${rest%%$'\n'*}"; rest="${rest#*$'\n'}"
    [[ $line =~ ^git[[:space:]]+add([[:space:]]|$) ]] || continue
    any=1
    opts=1
    local specs=0 pathless=0
    set -f
    for w in ${line#git}; do
      [ "$w" = add ] && continue
      if [ "$opts" = 1 ]; then
        [ "$w" = -- ] && { opts=0; continue; }
        case "$w" in
          -u|-p|-N|--update|--patch|--intent-to-add) pathless=1; continue ;;
          -v|--verbose) continue ;;
          -*) set +f; return 0 ;;
        esac
      fi
      specs=$((specs + 1))
      p="$w"
      case "$p" in
        :*|*'**'*) set +f; return 0 ;;
      esac
      depth=0; n=0; last=""
      local IFS=/
      local comps=($p)
      unset IFS
      for comp in "${comps[@]}"; do
        n=$((n + 1))
        case "$comp" in
          ''|.) continue ;;
          ..) [ "$depth" -gt 0 ] || { set +f; return 0; }; depth=$((depth - 1)) ;;
          *) depth=$((depth + 1)) ;;
        esac
        # a glob in a directory component refuses; the last component is judged below
        if [ "$n" -lt "${#comps[@]}" ] && [[ $comp == *[\*\?\[\]]* ]]; then set +f; return 0; fi
        last="$comp"
      done
      [ "$depth" -gt 0 ] || { set +f; return 0; }
      if [[ $last == *[\*\?\[\]]* ]] && ! [[ $last =~ [[:alnum:]] ]]; then set +f; return 0; fi
    done
    set +f
    # The normaliser DELETES a word it cannot keep plain (a quoted `:(top)`, `' .'`, a path with a space), so a `git add` left with no
    # pathspec had its arguments taken away: refused, unless -u/-p/-N, which act without one.
    [ "$specs" = 0 ] && [ "$pathless" = 0 ] && return 0
  done
  # `$'...'` is ANSI-C QUOTING (decoded by the normaliser), not an expansion, so only a `$` that is not followed by `'` counts.
  [ "$any" = 1 ] && [[ $cmd =~ \$[^\']|\$$|\`|\{|\}|~ ]] && return 0
  return 1
}
if [[ "$seg" == *add* ]]; then
  _add_refused && deny "stage specific files by plain relative path, never 'git add -A' / 'git add .' or a pattern that may reach the whole tree (GUARDRAILS: no accidental secrets or stray files). Allowed: -u -p -N -v, a path, or a glob in the last component with a literal in it (src/*.rb)."
fi
# A LONG OPTION IS ANY UNIQUE PREFIX, and short flags bundle (#1783): git reads `--mirr`, `--disc`, `--prun` and `-fc` as the full
# option, so `push`, `switch` and `checkout` refuse any option word that is a prefix of a dangerous one, and a bundle holding `f`
# (switch/checkout). A wildcard refspec (`refs/*:refs/*`) pushes every ref, like --mirror.
_dangerous_option() {
  [ "$degraded" = 1 ] && return 1
  local line w o rest
  if [ "$have_grep" = 1 ]; then rest="$(printf '%s\n' "$seg" | LC_ALL=C grep -E '^git[[:space:]]+(push|switch|checkout)([[:space:]]|$)')"$'\n'; else rest="$seg"$'\n'; fi
  while [ -n "$rest" ]; do
    line="${rest%%$'\n'*}"; rest="${rest#*$'\n'}"
    [[ $line =~ ^git[[:space:]]+(push|switch|checkout)([[:space:]]|$) ]] || continue
    set -f
    for w in $line; do
      case "$w" in
        --force-with-lease*|--force-if-includes*) continue ;;
        --?*)
          o="${w%%=*}"
          for d in --force --discard-changes --mirror --prune; do
            [ "${#o}" -ge 3 ] && [ "${d#"$o"}" != "$d" ] && { set +f; return 0; }
          done ;;
        -[!-]*) [[ $w == *f* ]] && [[ $line =~ ^git[[:space:]]+(switch|checkout) ]] && { set +f; return 0; } ;;
        *'*'*:*) [[ $line =~ ^git[[:space:]]+push ]] && { set +f; return 0; } ;;
      esac
    done
    set +f
  done
  return 1
}
if [[ "$seg" == *git* ]]; then
  _dangerous_option && deny "a force, discard-changes, mirror or prune option (in any unique prefix or bundle, or a wildcard refspec) can overwrite or delete work; it requires explicit user approval."
fi
# `*` and `..` stage as much as `.` (#1783 review).
if hit '^git[[:space:]]+add([[:space:]]+-[a-zA-Z-]*)*[[:space:]]+(-[a-zA-Z]*A[a-zA-Z]*\b|--all\b|\.{1,2}/?($|[[:space:]])|:/($|[[:space:]])|\*($|[[:space:]]))'; then
  deny "stage specific files, never 'git add -A' / 'git add .' (GUARDRAILS: no accidental secrets or stray files)."
fi

# `--no-verify` as a flag of a git commit/push/merge segment — not the words in an echo or a doc edit.
if hit '^git[[:space:]]+(commit|push|merge|rebase|cherry-pick)\b.*[[:space:]]--no-verify\b'; then
  deny "--no-verify skips pre-commit checks and is prohibited."
fi

if hit '^git[[:space:]]+reset\b.*[[:space:]]--hard\b'; then   # #1706: `reset HEAD~1 --hard` too
  deny "git reset --hard requires explicit user approval (uncommitted work loss)."
fi

# #1342. The other ways git throws away work with no undo. Each keeps a safe twin allowed:
# `clean -n` (dry run), `branch -d` (refuses an unmerged branch), `checkout <branch>`,
# `restore --staged` (unstage only) and `restore -- <explicit path>` (one named file, on purpose).
if hit '^git[[:space:]]+clean\b.*([[:space:]]-[a-zA-Z]*f|[[:space:]]--force\b)' \
   && ! exempt '^git[[:space:]]+clean\b.*([[:space:]]-[a-zA-Z]*n|[[:space:]]--dry-run\b)'; then
  deny "git clean -f deletes untracked files with no undo. Run 'git clean -n' first and show the user what it would remove; delete named paths with approval."
fi
if hit '^git[[:space:]]+checkout\b.*[[:space:]]--([[:space:]]|$)' \
   || hit '^git[[:space:]]+checkout([[:space:]]+[^[:space:]]+)*[[:space:]]+(\./?|:/)($|[[:space:]])' \
   || hit '^git[[:space:]]+(checkout|switch)\b.*[[:space:]](-f|--force|--discard-changes)($|[[:space:]])'; then   # #1706: `checkout HEAD .`; review: `checkout -f` discards too
  deny "git checkout -- <path> / git checkout . overwrites uncommitted edits with no undo. To keep them: git stash push -m <why> -- <path>. To discard ONE file you own: git restore -- <that path>."
fi
if hit '^git[[:space:]]+restore\b.*[[:space:]](\./?|:/|\*)($|[[:space:]])' \
   && ! exempt '^git[[:space:]]+restore\b.*--staged\b' ; then
  deny "git restore . discards every uncommitted edit in the tree. Name the one file you mean: git restore -- <path>."
fi
# #1706: a delete flag and a force flag in any spelling (`-d -f`, `-df`, `--delete --force`) are `-D`.
if hit '^git[[:space:]]+branch\b.*[[:space:]](-[a-zA-Z]*D\b|--delete[[:space:]]+--force\b|--force[[:space:]]+--delete\b)' \
   || { hit '^git[[:space:]]+branch\b.*[[:space:]](-[a-zA-Z]*d[a-zA-Z]*|--delete)\b' && hit '^git[[:space:]]+branch\b.*[[:space:]](-[a-zA-Z]*f[a-zA-Z]*|--force)\b'; }; then
  deny "git branch -D deletes an unmerged branch. Use 'git branch -d' (refuses unmerged work), or ask the user."
fi
if hit '^git[[:space:]]+stash[[:space:]]+(drop|clear)\b'; then
  deny "git stash drop/clear is refused: the stash stack is shared by every session in this repository, so the top entry may not be yours. Ask the user."
fi

# An issue filed from the shell skips the templates that apply labels, so it is labelled HERE or
# never (#1311). The raw command goes to the helper, because a label value is usually quoted and the
# normalised `seg` strips quotes. FAIL CLOSED: a helper that cannot run blocks the command.
# Called whenever the text names a create ANYWHERE (#1423): a create in `sh -c`, `eval`, backticks
# or behind `/usr/bin/gh` never starts a normalised segment, so a segment match alone never saw it.
# The helper tells a command from a mention (`echo "gh issue create"` stays allowed).
# Quotes, backslashes, `$` and newlines are dropped for this TRIGGER only (#1462, #1495): `gh issue "create" -t X --body y`, `gh issue $'create'`,
# `gh issue \<newline>create` and `gh --repo o/r issue create` must reach the helper, which parses
# the raw command properly and tells a create from a mention. With no `tr` the pipeline failed and the check was skipped (#1545); it now fires
# unconditionally there.
# A shell reading a script by redirect (`bash < file`, #1489) names no create in its text at all, so it
# triggers the helper too; the helper reads the file and decides. Coarse on purpose -- `/bin/bash < f`,
# `bash --norc < f`, `bash -o errexit < f`, `sh<f`, `bash 0< f`, `bash 2>&1 < f`, `bash &>log < f` (a
# redirect's `&` is not a separator, #1495; glued: `bash>/dev/null<f`, #1513). And any `$'…'` holding an escape,
# which can spell `create`, `issue` or `gh` (#1513) -- because over-triggering costs one
# parse, and under-triggering skips the check.
# #1515: the helper also reads a script a shell runs (`bash f`, `source f`, `cat f | bash`), and refuses the INDIRECT creates (a gh word built at
# run time, an alias, the verb through `xargs gh`) and a `gh api` POST to an issues collection, none of which names `gh issue create` in a
# way the old trigger saw. So the trigger also fires on the words `issue create|new` anywhere (an alias leaves no `gh` beside them), on any
# shell or `source` word, and on `gh api` naming issues.
# With `tr` the quotes, backslashes and `$` are dropped before matching. With NO `tr` the trigger fires unconditionally (#1545): over-triggering costs one
# parse, under-triggering skips the check, and the in-bash alternative (`${cmd//[...]/}`) is quadratic -- 130 KB did not finish in two minutes, so the
# deadline below would refuse every long command on a machine without `tr`.
_fire=0
if command -v tr >/dev/null 2>&1; then
  _flat="$(printf '%s' "$cmd" | tr -d "\"'\\\\\$" | tr '\n' ' ')"
else
  _flat="$cmd"; _fire=1
fi
_re_verb='issue[[:space:]]+(create|new)'
_re_shell_word='(^|[[:space:];&|(/])(sh|bash|zsh|dash|ksh)([[:space:]<>&]|$)'
_re_source='(^|[[:space:];&|({!])(source|\.)[[:space:]]+[^[:space:]]'
# #1645 R2: more ways to run text or build a gh command from data -- `eval`, `xargs`, an `alias`, a function definition. Over-triggering costs one parse.
_re_runs_text='(^|[[:space:];&|({!])(eval|xargs|alias|function)([[:space:]]|$)|\([[:space:]]*\)[[:space:]]*\{'
_re_api='[[:space:]]api[[:space:]]([^;&|]*)issues'
_re_ansi="[\$]'[^']*[\\\\]"
if [ "$_fire" = 1 ] || rawhit "$_flat" "$_re_verb" || rawhit "$cmd" "$_re_shell_word" \
   || rawhit "$cmd" "$_re_source" || rawhit "$cmd" "$_re_runs_text" || rawhit "$_flat" "$_re_api" || rawhit "$cmd" "$_re_ansi"; then
  _root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
  _why="$(printf '%s' "$cmd" | python3 "$(dirname "${BASH_SOURCE[0]}")/lib/issue_labels.py" --root "$_root" 2>&1)"
  _rc=$?
  if [ "$_rc" -eq 1 ]; then
    deny "$_why"
  elif [ "$_rc" -ne 0 ]; then
    deny "the issue-label check could not run (exit $_rc), so this gh issue create is refused rather than let through unlabelled."
  fi
fi

if hit '^kamal[[:space:]]+deploy\b' && [ "${RAILS_FLOW_ALLOW_DEPLOY:-0}" != "1" ]; then
  # #1708: the override is read from the HOOK's environment, so an inline assignment in the command (an agent approving itself)
  # stays blocked; the message no longer tells anyone to write it inline.
  deny "production deploys require explicit user approval. Ask the user; on approval THEY set RAILS_FLOW_ALLOW_DEPLOY=1 in this session's environment (an assignment written into the command is not read), then rerun kamal deploy."
fi

exit 0
}

# THE DEADLINE (#1575). A hook that outlives its timeout blocks every Bash call and leaves awk children behind: one ran
# 23 hours, the load reached 348. Past the deadline the whole process group is killed and the command is DENIED --
# this is a fail-closed gate, so "took too long to read" refuses. The default is below the hook's own 10 s timeout
# (hooks.json); RAILS_FLOW_HOOK_DEADLINE shortens it (tests) and is clamped at 8. With the lib missing the rules
# still run and only the backstop is gone: lint_self_consistency's hook-lib-drift reports the missing copy.
_dl="$(dirname "${BASH_SOURCE[0]}")/lib/deadline.sh"
if [ -f "$_dl" ] && . "$_dl" 2>/dev/null && type deadline_run >/dev/null 2>&1; then
  deadline_seconds 6 8
  deadline_run "$_deadline_s" _guard_main; _rc=$?
  if [ "$_rc" -ge 128 ]; then
    echo "BLOCKED by rails-flow guardrails: this command took longer than ${_deadline_s}s to read, so it is refused rather than guessed at. Split it into smaller commands, or write the long text to a file first." >&2
    exit 2
  fi
  exit "$_rc"
fi
_guard_main
exit $?
