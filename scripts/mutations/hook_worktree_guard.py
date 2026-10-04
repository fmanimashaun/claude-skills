"""Mutation guard: hook_worktree_guard. Declared here, run by scripts/mutation_check.py (#1581).

The judgement: the rules (one issue at a time; no duplicate for a branch or an issue). Split out of one guard that re-ran ALL four worktree fixture groups per mutant: this one runs only `guard_worktree`.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="hook_worktree_guard",
    subject="plugins/rails-flow/hooks/scripts/lib/worktree_guard.py",
    selftest="plugins/rails-flow/scripts/check_hook_gates.py",
    selftest_args=("--only", "guard_worktree"),
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
            'a second worktree for the same branch is no longer a duplicate',
            'same_branch = bool(branch) and w["branch"] == branch',
            'same_branch = False',
            'is denied by the branch alone',
        ),
        Mutation(
            'the same issue under another branch name is no longer a duplicate',
            ')) and not merged(cwd, w["head"], integ)',
            ')) and False',
            'for the same ISSUE under another branch name is denied',
        ),
        Mutation(
            'a merged worktree still blocks a new one for its issue',
            ')) and not merged(cwd, w["head"], integ)',
            '))',
            'once the same-issue worktree is MERGED',
        ),
        Mutation(
            "the new worktree's directory name is not read for an issue",
            'new_keys = keys(branch, os.path.basename(path or ""))',
            'new_keys = keys(branch)',
            "by the new worktree's DIRECTORY name",
        ),
        Mutation(
            "a date's year is read as an issue number",
            '    name = DATE.sub("", name or "")',
            '    name = name or ""',
            'a DATE in a branch name is not issue 2026',
        ),
        Mutation(
            'a session that owns an unmerged worktree may add another',
            '            if not merged(cwd, sha, integ):\n                return deny(f"this session already owns',
            '            if False:\n                return deny(f"this session already owns',
            'a session that owns an UNMERGED worktree may not add another',
        ),
        Mutation(
            'a merged lane still blocks',
            '            if not merged(cwd, sha, integ):\n                return deny(f"this session already owns',
            '            if True:\n                return deny(f"this session already owns',
            "after the owned worktree's branch MERGES",
        ),
        Mutation(
            'a lane whose worktree is gone still blocks',
            '            if wt is None:\n                continue                          # the worktree is gone: that lane is finished\n            sha = branch_sha(cwd, row.get("branch", "")) or wt["head"]',
            '            wt = wt or {"path": lane_path, "head": ""}\n            sha = branch_sha(cwd, row.get("branch", "")) or wt["head"]',
            'a lane whose worktree no longer exists does not block',
        ),
        Mutation(
            "another session's lane blocks this one",
            '        for lane_path, row in coordination.lanes_for(record, sid) if record else []:',
            '        for lane_path, row in list(record["sessions"].items()) if record else []:',
            'ANOTHER session, owning nothing, is not held back',
        ),
        Mutation(
            'an unreadable record lets the command run',
            '            return deny(f"the coordination record is unreadable ({e}). Fix or delete {rp}, then retry; a lane that "',
            '            return 0; _ = (f"the coordination record is unreadable ({e}). Fix or delete {rp}, then retry; a lane that "',
            'an unreadable coordination record fails closed',
        ),
        Mutation(
            'the guard is not dormant outside a git repository',
            '        return 0                                  # dormant outside a git repository',
            '        return deny("not a repository")',
            'outside a git repository the guard is dormant',
        ),
        Mutation(
            'an attached -b/-B value is not read (git accepts -Bname and -fbname)',
            '                if ch in "bB":',
            '                if ch in "xX":',
            'an ATTACHED -B<branch> (git accepts it) is read',
        ),
        Mutation(
            'a redirect before the commit-ish becomes the commit-ish and hides the branch',
            '        if re.search(r"[<>]", a):',
            '        if False:',
            'a redirect BEFORE the commit-ish does not hide the branch',
        ),
        Mutation(
            'a descriptor prefix (the 2 of 2>&1) is taken for an operand',
            '        if a.isdigit() and k + 1 < len(args) and REDIRECT_ALONE.match(args[k + 1]):',
            '        if False:',
            'nor a stderr redirect',
        ),
        Mutation(
            '--reason <text> as two words leaves its text as an operand',
            '        if a == "--reason":',
            '        if a == "--reasonx":',
            '--reason <text> as two words does not swallow the branch',
        ),
        Mutation(
            'a worktree add inside a quoted string (bash -c, eval) is never read again',
            '    if _depth < 2:',
            '    if False:',
            'may still run it inside `bash -c`',
        ),
        Mutation(
            'a number is read as an issue after any separator, so slug-20 is issue 20',
            'ISSUE_SEGMENT = re.compile(r"(?:^|/)(\\d{2,6})(?=[-_/]|$)")',
            'ISSUE_SEGMENT = re.compile(r"(?:^|[/_-])(\\d{2,6})(?=[-_/]|$)")',
            '`-b chore/ubuntu-20` is NOT issue 20',
        ),
        Mutation(
            'a backslash-newline continuation is not joined, so the operands on the next line are lost',
            '    command = strip_heredocs(command.replace("\\\\\\n", ""))',
            '    command = strip_heredocs(command)',
            'also between an option and its value',
        ),
    ),
)
