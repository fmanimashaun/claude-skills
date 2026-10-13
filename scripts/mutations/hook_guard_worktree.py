"""Mutation guard: hook_guard_worktree. Declared here, run by scripts/mutation_check.py (#1581).

The wrapper: the rules (one issue at a time; no duplicate for a branch or an issue). Split out of one guard that re-ran ALL four worktree fixture groups per mutant: this one runs only `guard_worktree`.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="hook_guard_worktree",
    subject="plugins/rails-flow/hooks/scripts/guard-worktree.sh",
    selftest="plugins/rails-flow/scripts/check_hook_gates.py",
    selftest_args=("--only", "guard_worktree"),
    # Each mutant runs only the fixture its `expects` names (#1599); the ones marked `narrow=False` depend on state an
    # earlier fixture builds, cannot run alone, and run the whole sub-group (#1581, surveyed one by one).
    narrow_with="--match",
    needs=("plugins/rails-flow/scripts/fixture_git.py", 
           'plugins/qa-flow/scripts/remote_evidence.py',  # #1581 merge: run by session-start.sh / release-gate.sh
           'plugins/rails-flow/scripts/assign_lanes.py', 'plugins/rails-flow/scripts/brain_local_sync.py', 'plugins/rails-flow/scripts/check_memory_index.py',  # session-start.sh runs all three (#1581, #1828: the harness drives it)
           "plugins/rails-flow/hooks/hooks.json",  # read by check_hook_gates since #1362
           'plugins/rails-flow/hooks/scripts', 'plugins/qa-flow/hooks/scripts', 'plugins/qa-flow/scripts',
           # guard-claims.sh runs extract_claims.py; without it the harness's two claim
           # fixtures fail in the staged tempdir and every mutation reads as caught (#1109).
           'plugins/rails-flow/scripts/check_criteria.py',
           'plugins/rails-flow/scripts/check_handoff.py',
           'plugins/qa-flow/scripts/read_certification.py',
           'plugins/qa-flow/scripts/push_targets.py',  # release-gate.sh runs it (#1410)
           'plugins/qa-flow/scripts/release_evidence.py',
           'plugins/rails-flow/scripts/self_consistency.py',
           'plugins/rails-flow/scripts/extract_claims.py',
           'plugins/rails-flow/scripts/ci_verdict_hint.py', 'plugins/rails-flow/scripts/test_preflight.py', 'plugins/rails-flow/scripts/wip_commit.py', 'plugins/rails-flow/scripts/session_reaper.py', 'plugins/rails-flow/scripts/process_containment.py'),
    mutations=(
        Mutation(
            "the line walk slices the string again, so 150 KB of plain lines is quadratic and runs past the hook's timeout (#1978, #1980)",
            'while IFS= read -r line || [ -n "$line" ]; do\n  if [[ $line =~ $re ]]; then hit=1; break; fi\ndone <<< "$seg"',
            'rest="$seg"$\'\\n\'\nwhile [ -n "$rest" ]; do\n  line="${rest%%$\'\\n\'*}"; rest="${rest#*$\'\\n\'}"\n  if [[ $line =~ $re ]]; then hit=1; break; fi\ndone',
            'a 170 KB command of plain lines is let through',
        ),
        Mutation(
            'no size cap: a command past it that mentions worktree is read, runs into the 15 s timeout and is denied without a reason (#1980)',
            'if [ "${#cmd}" -gt "$_large_chars" ] && [[ $plain == *worktree* ]]; then\n',
            'if false; then\n',
            'mentions `worktree` is refused at once',
        ),
        Mutation(
            'the size cap is not gated on a mention, so every large command is refused, an unrelated heredoc included (#1980)',
            ' && [[ $plain == *worktree* ]]; then\n',
            '; then\n',
            'does NOT mention `worktree` is let through',
        ),
        Mutation(
            "the quotes are dropped with bash's global substitution again, which is quadratic in the number of quotes: 50,000 quoted words took over 100 s (#1980)",
            'plain="$(printf \'%s\' "$cmd" | tr -d "\\047\\"\\\\\\\\" 2>/dev/null)" || plain="$cmd"',
            'plain="${cmd//[\\\'\\"\\\\]/}"',
            'ONE 200 KB line of quoted words is let through',
        ),
        Mutation(
            'every command is taken for a worktree add, so a plain git status is judged and refused',
            '  if [[ $line =~ $re ]]; then hit=1; break; fi',
            '  if true; then hit=1; break; fi',
            'NOT a worktree add, left alone',
        ),
        Mutation(
            "the helper's refusal is swallowed and the command runs",
            '  2) printf \'%s\\n\' "$out" >&2; exit 2 ;;',
            '  2) exit 0 ;;',
            'a session that owns an UNMERGED worktree may not add another',
        ),
    ),
)
