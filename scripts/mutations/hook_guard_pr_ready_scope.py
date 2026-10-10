"""Mutation guard: hook_guard_pr_ready_scope. Declared here, run by scripts/mutation_check.py (#1565).

The wrapper, `guard-pr-ready.sh`: which commands are judged at all, and that a refusal is not swallowed.
"""
from mutation_types import Guard, Mutation  # noqa: F401

# The same staging as hook_guard_pr_ready (one copy per guard: each file is loaded on its own).
_NEEDS = ("plugins/rails-flow/scripts/fixture_git.py",
          'plugins/qa-flow/scripts/remote_evidence.py',
          'plugins/rails-flow/scripts/assign_lanes.py', 'plugins/rails-flow/scripts/brain_local_sync.py',
          "plugins/rails-flow/hooks/hooks.json",
          'plugins/rails-flow/hooks/scripts', 'plugins/qa-flow/hooks/scripts', 'plugins/qa-flow/scripts',
          'plugins/rails-flow/scripts/check_criteria.py',
          'plugins/rails-flow/scripts/check_handoff.py',
          'plugins/qa-flow/scripts/read_certification.py',
          'plugins/qa-flow/scripts/push_targets.py',
          'plugins/qa-flow/scripts/release_evidence.py',
          'plugins/rails-flow/scripts/self_consistency.py',
          'plugins/rails-flow/scripts/extract_claims.py',
          'plugins/rails-flow/scripts/ci_verdict_hint.py', 'plugins/rails-flow/scripts/session_reaper.py',
          'plugins/rails-flow/scripts/process_containment.py')

GUARD = Guard(
    name="hook_guard_pr_ready_scope",
    subject="plugins/rails-flow/hooks/scripts/guard-pr-ready.sh",
    selftest="plugins/rails-flow/scripts/check_hook_gates.py",
    selftest_args=("--only", "guard_pr_ready"),
    narrow_with="--match",
    needs=_NEEDS,
    mutations=(
        Mutation(
            "`--undo` after a bare `--` still exempts",
            'pre=" $a "; pre="${pre%% -- *} "',
            'pre=" $a "',
            "`--undo` after a bare `--` is a positional, not the flag",
        ),
        Mutation(
            "the match reverts to the anchored `^gh pr ready`, so a flag before `pr` slips through",
            're="^([^[:space:]]*/)?gh${_f}[[:space:]]+pr${_f}[[:space:]]+ready([[:space:]]|\\$)"',
            "re='^gh[[:space:]]+pr[[:space:]]+ready([[:space:]]|$)'",
            "a flag before `pr`, or gh by path, is still judged: gh -R o/r pr ready 5",
        ),
        Mutation(
            "`gh pr view` is matched too",
            're="^([^[:space:]]*/)?gh${_f}[[:space:]]+pr${_f}[[:space:]]+ready([[:space:]]|\\$)"',
            're="^([^[:space:]]*/)?gh${_f}[[:space:]]+pr${_f}[[:space:]]+(ready|view)([[:space:]]|\\$)"',
            "NOT a pr ready, left alone: gh pr view 12",
        ),
        Mutation(
            "`--undo` is judged like a ready",
            '    [[ $pre =~ [[:space:]]--undo[[:space:]] ]] && continue\n',
            "",
            "`gh pr ready --undo` is always allowed",
        ),
        Mutation(
            "the helper's refusal is swallowed",
            "  2) printf '%s\\n' \"$out\" >&2; exit 2 ;;",
            "  2) exit 0 ;;",
            "in force with NO record, `gh pr ready` is refused",
        ),
    ),
)
