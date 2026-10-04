"""Mutation guard: hook_release_gate_deadline. The deadline block at the bottom of release-gate.sh. Run by scripts/mutation_check.py (#1575)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="hook_release_gate_deadline",
    subject="plugins/qa-flow/hooks/scripts/release-gate.sh",
    selftest="plugins/rails-flow/scripts/check_hook_gates.py",
    # Only the deadline fixtures drive this subject; the whole harness per mutant is ~90 CPU-seconds.
    selftest_args=("--only", "deadline"),
    needs=("plugins/rails-flow/hooks/hooks.json", "plugins/qa-flow/hooks/hooks.json",
           "plugins/rails-flow/hooks/scripts", "plugins/qa-flow/hooks/scripts", "plugins/qa-flow/scripts",
           # release-gate.sh and guard-bash.sh run these; unstaged, the harness's other fixtures fail in the staged
           # tempdir and every mutation reads as caught for an environmental reason (#1109, #1173).
           "plugins/rails-flow/scripts/check_criteria.py", "plugins/rails-flow/scripts/check_handoff.py",
           "plugins/qa-flow/scripts/read_certification.py", "plugins/qa-flow/scripts/push_targets.py",
           "plugins/qa-flow/scripts/release_evidence.py", "plugins/rails-flow/scripts/self_consistency.py",
           "plugins/rails-flow/scripts/extract_claims.py", "plugins/rails-flow/scripts/ci_verdict_hint.py"),
    mutations=(
        # A blocking gate: a promotion it cannot read must be refused.
        Mutation(
            'a timeout never denies, so a promotion that cannot be read in time is allowed',
            '    if [ "$_looks_promotion" = "1" ]; then\n      [ "${QA_ALLOW_MAIN:-0}" = "1" ] && { echo "qa-flow: the gate hit',
            '    if false; then\n      [ "${QA_ALLOW_MAIN:-0}" = "1" ] && { echo "qa-flow: the gate hit',
            'refuses `git push origin main` when it cannot finish reading it',
        ),
        # Blocking every slow command would be the failure; the coarse detector decides.
        Mutation(
            'a timeout always denies, so every slow command is blocked, not only a promotion',
            '    if [ "$_looks_promotion" = "1" ]; then\n      [ "${QA_ALLOW_MAIN:-0}" = "1" ] && { echo "qa-flow: the gate hit',
            '    if true; then\n      [ "${QA_ALLOW_MAIN:-0}" = "1" ] && { echo "qa-flow: the gate hit',
            'ALLOWS a command that does not look like a promotion',
        ),
        # The audited override works in the missing-tool path and must work here.
        Mutation(
            'QA_ALLOW_MAIN=1 stops being honoured on a timeout',
            '[ "${QA_ALLOW_MAIN:-0}" = "1" ] && { echo "qa-flow: the gate hit',
            'false && { echo "qa-flow: the gate hit',
            'QA_ALLOW_MAIN=1 is honoured and audited on a timeout',
        ),
        # Past hooks.json's 15 s Claude Code stops waiting.
        Mutation(
            "the default and ceiling move above the hook's own timeout",
            'deadline_seconds 10 13',
            'deadline_seconds 20 30',
            "default and ceiling sit below the hook's configured timeout",
        ),
        # #1602 review F1: a LIST of mutation names let three promotions through on a timeout.
        Mutation(
            'a timeout stops denying `gh api graphql` mutations by the word, so a promotion with a new name gets through',
            '[[ $_in =~ ${_b}api${_e} ]] && [[ $_in =~ ${_b}graphql${_e} ]] && [[ $_in =~ mutation ]] && _looks_promotion=1',
            ':',
            'refuses `gh api graphql -f` enablePullRequestAutoMerge when it cannot finish reading it',
        ),
    ),
)
