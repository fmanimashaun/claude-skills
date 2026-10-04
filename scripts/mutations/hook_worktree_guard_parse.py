"""Mutation guard: hook_worktree_guard_parse. Declared here, run by scripts/mutation_check.py (#1581).

The judgement: what the hook reads (quoted words, mentions, heredoc bodies). Split out of one guard that re-ran ALL four worktree fixture groups per mutant: this one runs only `guard_worktree_parse`.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="hook_worktree_guard_parse",
    subject="plugins/rails-flow/hooks/scripts/lib/worktree_guard.py",
    selftest="plugins/rails-flow/scripts/check_hook_gates.py",
    selftest_args=("--only", "guard_worktree_parse"),
    # Each mutant runs only the fixture its `expects` names (#1599); the ones marked `narrow=False` depend on state an
    # earlier fixture builds, cannot run alone, and run the whole sub-group (#1581, surveyed one by one).
    narrow_with="--match",
    needs=(
           'plugins/rails-flow/scripts/assign_lanes.py', 'plugins/rails-flow/scripts/brain_local_sync.py',  # session-start.sh runs both (#1581: the harness drives it)
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
           'plugins/rails-flow/scripts/ci_verdict_hint.py'),
    mutations=(
        Mutation(
            'a mention that only matched with its quotes dropped is refused as unreadable',
            '        if raw_only:\n            return 0',
            '        if False:\n            return 0',
            'a mention is not a command, even while a lane is held',
        ),
        Mutation(
            'every quoted string holding the words is read as a command, mentions included',
            '            if (prev == "eval" or re.fullmatch(r"-[A-Za-z]*c", prev)) and "worktree" in tok and "add" in tok:',
            '            if "worktree" in tok and "add" in tok:',
            'a mention is not a command, even while a lane is held',
        ),
        Mutation(
            'a heredoc body fed to a non-shell command is still read as commands',
            '        else:\n            out.append(lines[j])                       # data: drop the body, keep the terminator line',
            '        else:\n            out.extend(lines[i:j + 1])',
            'a heredoc body that merely mentions it is not a command',
            narrow=False,
        ),
        Mutation(
            'a heredoc fed to a shell is dropped, so a worktree add inside bash <<EOF is never judged',
            '        if SHELL_WORD.search(line[:m.start()]):',
            '        if False:',
            'a heredoc fed to a SHELL is still read as commands',
            narrow=False,
        ),
    ),
)
