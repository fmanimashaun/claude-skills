#!/usr/bin/env bash
# Stop gate — mechanical form of "prove the NEW behavior":
#  1. Uncommitted app code without an accompanying spec change → block once.
#  2. Uncommitted spec changes → run just those specs; red suite → block.
set -uo pipefail

# Portable timeout: prefer `timeout`, fall back to macOS `gtimeout`, else run bare.
# A MISSING timeout must never be misread as a failing suite (the exit-127 trap).
_rf_timeout() {
  local secs="$1"; shift
  if type -P timeout >/dev/null 2>&1; then timeout "$secs" "$@"
  elif type -P gtimeout >/dev/null 2>&1; then gtimeout "$secs" "$@"
  else "$@"; fi
}

input="$(cat)"

# Never loop: if we already blocked once, let the stop proceed.
printf '%s' "$input" | grep -q '"stop_hook_active"[[:space:]]*:[[:space:]]*true' && exit 0

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0
[ -d spec ] || exit 0

# `-uall` is load-bearing: plain --porcelain COLLAPSES a new untracked directory to "?? app/",
# so `app/models/invoice.rb` in a brand-new folder was invisible here and behavioural code
# could finish with no spec at all. `cut -c4-` takes the path (cols 1-2 are status, 3 a space)
# so paths containing spaces survive, and the sed strips the "old -> new" of a rename to the
# new path, which is the one that needs proving. Found by behaviour-testing #125's gate.
changed="$(git status --porcelain -uall 2>/dev/null | cut -c4- | sed 's/^.* -> //')"
app_changed="$(printf '%s\n' "$changed" | grep -E '^(app|lib)/.*\.rb$' || true)"
spec_changed="$(printf '%s\n' "$changed" | grep -E '^spec/.*_spec\.rb$' || true)"

# ---------------------------------------------------------------------------------------
# 0. Acceptance criteria must exist BEFORE the code they grade (#125).
#
# The checks below prove "the new behaviour has a spec". They fire after code exists, so
# they cannot tell whether the spec asserts what was REQUIRED or merely what the code
# happens to do. A goal written after the result is unfalsifiable — the same defect class as
# a gate that cannot fail, moved from the gate to the goal.
#
# Scoped to the flow's own branches on purpose: blocking every branch would break ad-hoc
# work that never entered the flow, and "criteria before implementation" is a promise the
# flow made, not a rule about all Ruby edits.
# ---------------------------------------------------------------------------------------
# `symbolic-ref` first: it reports the branch even on an unborn HEAD (a fresh repo with no
# commits), where `rev-parse --abbrev-ref` answers the literal "HEAD" and the case below would
# silently never match. Fall back for a detached HEAD, where there is no branch to scope to.
branch="$(git symbolic-ref --short HEAD 2>/dev/null || git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
# `feat/*` is here because it was NOT, and the gap was silent (#720). git's own shorthand is a
# very common convention, and a `feat/` branch matched neither arm -- so the acceptance-criteria
# and work-order layers never ran, while the generic "code changed without a proving spec" gate
# below still fired. That is the worst shape: the Stop gate LOOKED like it was working, and a
# feature finished green with its criteria unenforced. Reported from a live repo mixing both
# spellings, on a branch named `feat/branded-error-surfaces`.
#
# The `*/*` arm is the part that generalises. Enumerating prefixes is a treadmill -- `bugfix/`,
# `hotfix/`, `chore/`, whatever a team picks next -- and the prefix nobody added is exactly the
# one that goes unenforced in silence. So any other slashed branch that CHANGED APP CODE gets a
# one-line notice naming what did not run. It never blocks: scoping enforcement to the flow's own
# branches is deliberate (see above), and ad-hoc work must stay unblocked. Making the skip
# VISIBLE is the fix; making it fatal would be a different, worse bug.
case "$branch" in
  feature/*|feat/*|fix/*)
    # Flatten nested branch names: `feature/team/foo` -> `team-foo`, not `team/foo`, which
    # would demand a nested docs/acceptance/team/ directory nobody would think to create and
    # block them with a path they never chose.
    slug="${branch#*/}"
    slug="${slug//\//-}"
    criteria="docs/acceptance/${slug}.md"
    if [ -n "$app_changed" ] && [ ! -f "$criteria" ]; then
      {
        echo "rails-flow stop gate: app code changed with no acceptance criteria."
        echo "Expected: $criteria"
        echo ""
        echo "Write the criteria FIRST — one per unit, each in the shape:"
        echo "  - **AC-1** Given <state>, when <action>, then <observable>"
        echo "Every unit needs at least one error-path criterion. A criterion written after the"
        echo "code cannot grade it: it asserts what the code does, not what was required."
      } >&2
      exit 2
    fi
    # Validate the criteria and the spec mapping. A guard decides whether to RUN a check; it
    # must never soften the verdict, so a missing python3 skips (fails open) while a real
    # finding blocks (fails closed).
    if [ -f "$criteria" ] && command -v python3 >/dev/null 2>&1; then
      # `:-` matters: this script runs under `set -u`, so a bare ${CLAUDE_PLUGIN_ROOT} would
      # abort the whole gate with "unbound variable" whenever it is run outside the hook
      # runtime. A guard must not crash; the `-f` test below then skips cleanly.
      checker="${CLAUDE_PLUGIN_ROOT:-}/scripts/check_criteria.py"
      if [ -f "$checker" ]; then
        # --specs only once specs exist, so the mapping check does not fire before the first
        # spec is written (the criteria step legitimately precedes it).
        if [ -n "$spec_changed" ] || [ -n "$(ls -A spec 2>/dev/null)" ]; then
          set -- "$criteria" --specs spec
        else
          set -- "$criteria"
        fi
        if ! cout="$(python3 "$checker" "$@" 2>&1)"; then
          {
            echo "rails-flow stop gate: acceptance criteria do not hold."
            printf '%s\n' "$cout"
          } >&2
          exit 2
        fi
      fi
    fi
    # ---------------------------------------------------------------------------------
    # The work order (#127), validated ONLY when one exists.
    #
    # Deliberately not required: a work order is new, and demanding one would block every
    # branch already in flight, plus every ad-hoc fix that never entered the flow. But an
    # EXISTING work order that no longer holds is worse than none -- it is a contract the
    # executor is reading and the file has stopped meaning. So: absent is silence, present
    # is enforced. `command -v python3` decides whether the check RUNS; it never softens
    # the verdict.
    # ---------------------------------------------------------------------------------
    handoff="docs/handoff/${slug}.md"
    if [ -f "$handoff" ] && command -v python3 >/dev/null 2>&1; then
      hchecker="${CLAUDE_PLUGIN_ROOT:-}/scripts/check_handoff.py"
      if [ -f "$hchecker" ]; then
        set -- "$handoff"
        [ -f "$criteria" ] && set -- "$@" --criteria "$criteria"
        if ! hout="$(python3 "$hchecker" "$@" 2>&1)"; then
          {
            echo "rails-flow stop gate: the work order does not hold."
            printf '%s\n' "$hout"
          } >&2
          exit 2
        else
          # #708. Surface advisory NOTEs on the PASSING path, so base drift stays visible instead of
          # being swallowed by a clean exit. Visibility was the whole reason the note exists.
          #
          # The verdict still comes from the EXIT CODE alone, deliberately. The issue suggested this
          # gate filter `NOTE:` lines out of a failing count itself -- do not. This hook fails CLOSED
          # by design, and a gate that decided pass/fail by parsing output would call a crash that
          # printed nothing a pass. The contract belongs where the findings are produced, and that is
          # where it now lives: `check_handoff.py` exits 0 when only notes remain.
          notes="$(printf '%s\n' "$hout" | grep '^  - NOTE: ' || true)"
          if [ -n "$notes" ]; then
            {
              echo "rails-flow stop gate: the work order holds. Advisory:"
              printf '%s\n' "$notes"
            } >&2
          fi
        fi
      fi
    fi
    ;;
  */*)
    # #720. Not one of the flow's branches, but app code changed -- so say what did not run.
    # Advisory by design: this arm must never exit non-zero.
    if [ -n "$app_changed" ]; then
      {
        echo "rails-flow stop gate: branch '$branch' is outside the flow's enforced set"
        echo "(feature/*, feat/*, fix/*), so acceptance criteria and the work order were NOT"
        echo "checked for this change. The proving-spec gate below still applies."
        echo "Rename the branch, or accept that those two are unenforced here."
      } >&2
    fi
    ;;
esac

if [ -n "$app_changed" ] && [ -z "$spec_changed" ]; then
  {
    echo "rails-flow stop gate: behavioral code changed with no new/updated spec."
    echo "Changed: $(printf '%s\n' "$app_changed" | head -5 | tr '\n' ' ')"
    echo "Write the spec that PROVES the new behavior (wrong-role rejection, concern behavior, etc.),"
    echo "or explain to the user why none is needed, then finish."
  } >&2
  exit 2
fi

# RUN THROUGH THE PROJECT'S RUBY, not whatever `bundle` is on PATH (#683).
#
# Under mise/rbenv/asdf the shims are often NOT on PATH, so a bare `bundle` is the GLOBAL Ruby's.
# Bundler then aborts on the Ruby/lockfile mismatch, the abort is a non-zero exit like any other,
# and the gate reported "changed specs are RED" on a green suite — blocking every turn-stop.
#
# That is the worst failure a gate can have. `art-direction.md` states the consequence plainly: a
# gate that fires on correct input gets switched off, and then nothing is checked at all.
#
# The runner is chosen by what the PROJECT pins, not by what is installed: a `.tool-versions` or
# `.ruby-version` is the project saying "this Ruby", and the manager that owns that file is the one
# that can honour it.
_rf_bundle() {
  if [ -f .tool-versions ] || [ -f .ruby-version ]; then
    if command -v mise >/dev/null 2>&1 && mise current ruby >/dev/null 2>&1; then
      mise exec -- bundle "$@"; return $?
    fi
    if command -v rbenv >/dev/null 2>&1; then rbenv exec bundle "$@"; return $?; fi
    if command -v asdf >/dev/null 2>&1; then asdf exec bundle "$@"; return $?; fi
  fi
  bundle "$@"
}

if [ -n "$spec_changed" ] && command -v bundle >/dev/null 2>&1; then
  files="$(printf '%s\n' "$spec_changed" | tr '\n' ' ')"
  if ! out="$(_rf_timeout 120 _rf_bundle exec rspec $files --fail-fast --no-color 2>&1 | tail -15)"; then
    # BOTH BRANCHES EXIT 2, and that is what makes a crude pattern match safe here: a
    # misclassification changes the WORDING, never whether the finish is blocked. Getting it wrong
    # in the cautious direction says "nothing is known about your specs" when they did fail — still
    # blocking, still sending you to look. Getting it wrong the other way is the reported bug.
    #
    # A BUNDLER ABORT IS NOT A RED SUITE. Bundler exits non-zero for "your Ruby does not match the
    # lockfile" exactly as it does for a failing example, and calling that RED sends the reader to
    # look at specs that are fine. Name the environment when the output says environment.
    case "$out" in
      # `Could not locate` is here because it was NOT, and the miss reported a red suite for a
      # suite that never ran (#724). Bundler says "Could not locate Gemfile" when it cannot start
      # at all -- a hook firing from a subdirectory, a monorepo whose app is not at the root, a
      # half-initialised project -- and `Could not find` (a missing GEM) does not cover it.
      #
      # This is the second member this denylist has been missing. If it needs a third, the shape is
      # wrong: key on a positive signal instead, the way the release-notes detail line had to after
      # its own banner denylist was beaten (#715).
      *"Your Ruby version"*|*"was resolved to"*|*"Could not find"*|*"Could not locate"*|\
      *"command not found"*|*"Bundler::"*)
        {
          echo "rails-flow stop gate: could not RUN the changed specs — this is an environment"
          echo "problem, not a failing suite. Nothing about your specs is known either way."
          echo "The gate tried the project's Ruby via mise/rbenv/asdf and fell back to PATH."
          printf '%s\n' "$out"
        } >&2
        exit 2
        ;;
    esac
    {
      echo "rails-flow stop gate: changed specs are RED — fix before finishing."
      printf '%s\n' "$out"
    } >&2
    exit 2
  fi
fi
exit 0
