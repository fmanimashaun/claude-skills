"""Mutation guard: hook_worktree_guard. Declared here, run by scripts/mutation_check.py (#1581).

The judgement: the duplicate rule, the one-issue rule, the resume pointer and the zombie advisory (#1581).
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
            'the resume pointer is never printed',
            '        if wt:\n            lines.append(f"- resume in place:',
            '        if False:\n            lines.append(f"- resume in place:',
            'the session that holds a lane is told where to resume',
        ),
        Mutation(
            'every session is pointed at every lane',
            '    for lane_path, row in coordination.lanes_for(record, session_id) if record and session_id else []:',
            '    for lane_path, row in list(record["sessions"].items()) if record else []:',
            'ANOTHER session is not pointed at it',
        ),
        Mutation(
            'a merged worktree with uncommitted work is listed as finished',
            ' and not git(w["path"], "status", "--porcelain")[1].strip()]',
            ']',
            'a merged worktree with uncommitted work is NOT listed',
        ),
        Mutation(
            'an unmerged worktree is listed as finished',
            'finished = [w for w in existing[1:] if merged(cwd, w["head"], integ) and',
            'finished = [w for w in existing[1:] if True and',
            'the session that holds a lane is told where to resume',
        ),
        Mutation(
            'the zombie warning always fires',
            '    if count >= max(1, _env_int("RAILS_FLOW_ZOMBIE_WARN", ZOMBIE_WARN)):',
            '    if True:',
            'below the threshold the zombie warning is silent',
        ),
        Mutation(
            'the zombie warning never fires',
            '    if count >= max(1, _env_int("RAILS_FLOW_ZOMBIE_WARN", ZOMBIE_WARN)):',
            '    if False:',
            'a zombie count at the threshold is reported',
        ),
        Mutation(
            'a zombie is not recognised by its state',
            'parts[0].startswith("Z")',
            'parts[0].startswith("X")',
            'a zombie count at the threshold is reported',
        ),
        Mutation(
            'the zombie advisory prints a parent\'s whole command line, credentials included',
            '["ps", "-o", "comm=", "-p", str(ppid)]',
            '["ps", "-o", "command=", "-p", str(ppid)]',
            "never prints a parent's command-line arguments",
        ),
        Mutation(
            "an attached -b/-B value is not read (git accepts -Bname and -fbname)",
            '                if ch in "bB":',
            '                if ch in "xX":',
            "an ATTACHED -B<branch> (git accepts it) is read",
        ),
        Mutation(
            "a redirect before the commit-ish becomes the commit-ish and hides the branch",
            '        if re.search(r"[<>]", a):',
            '        if False:',
            "a redirect BEFORE the commit-ish does not hide the branch",
        ),
        Mutation(
            "a descriptor prefix (the 2 of 2>&1) is taken for an operand",
            '        if a.isdigit() and k + 1 < len(args) and REDIRECT_ALONE.match(args[k + 1]):',
            '        if False:',
            "nor a stderr redirect",
        ),
        Mutation(
            "--reason <text> as two words leaves its text as an operand",
            '        if a == "--reason":',
            '        if a == "--reasonx":',
            "--reason <text> as two words does not swallow the branch",
        ),
        Mutation(
            "a worktree add inside a quoted string (bash -c, eval) is never read again",
            '    if _depth < 2:',
            '    if False:',
            "may still run it inside `bash -c`",
        ),
        Mutation(
            "a number is read as an issue after any separator, so slug-20 is issue 20",
            'ISSUE_SEGMENT = re.compile(r"(?:^|/)(\\d{2,6})(?=[-_/]|$)")',
            'ISSUE_SEGMENT = re.compile(r"(?:^|[/_-])(\\d{2,6})(?=[-_/]|$)")',
            "`-b chore/ubuntu-20` is NOT issue 20",
        ),
        Mutation(
            "a mention that only matched with its quotes dropped is refused as unreadable",
            "        if raw_only:\n            return 0",
            "        if False:\n            return 0",
            "a mention is not a command, even while a lane is held",
        ),
        Mutation(
            "a command that moves into a repository from outside one is allowed",
            "        if MOVES.search(command):",
            "        if False:",
            "`cd <repo> && git worktree add` from a cwd outside any repository",
        ),
        Mutation(
            "a junk integer setting raises instead of using its default",
            "        return int(os.environ.get(name) or default)\n    except ValueError:\n        return default",
            "        return int(os.environ.get(name) or default)\n    except ValueError:\n        raise",
            "a junk RAILS_FLOW_ZOMBIE_WARN falls back to the default",
        ),
        Mutation(
            "every quoted string holding the words is read as a command, mentions included",
            '            if (prev == "eval" or re.fullmatch(r"-[A-Za-z]*c", prev)) and "worktree" in tok and "add" in tok:',
            '            if "worktree" in tok and "add" in tok:',
            "a mention is not a command, even while a lane is held",
        ),
        Mutation(
            "a git that did not answer reads as 'not a repository', so the guard goes dormant",
            "    if inside == UNAVAILABLE:",
            "    if False:",
            "with git missing a worktree add cannot be judged",
        ),
        Mutation(
            "a git worktree list that fails reads as 'no worktrees'",
            "    if existing is None:",
            "    if False:",
            "could not list the worktrees",
        ),
        Mutation(
            "git is given a fixed long timeout instead of what is left of the budget",
            "timeout=min(5, remaining))",
            "timeout=60)",
            "a slow git is cut off within the budget",
        ),
        Mutation(
            "a record that cannot be located is read as 'no lanes'",
            "        if rp is None:\n            return deny(",
            "        if False:\n            return deny(",
            "could not locate the coordination record",
        ),
        Mutation(
            "a backslash-newline continuation is not joined, so the operands on the next line are lost",
            r'    command = strip_heredocs(command.replace("\\\n", ""))',
            '    command = strip_heredocs(command)',
            "also between an option and its value",
        ),
        Mutation(
            "a heredoc body fed to a non-shell command is still read as commands",
            "        else:\n            out.append(lines[j])                       # data: drop the body, keep the terminator line",
            "        else:\n            out.extend(lines[i:j + 1])",
            "a heredoc body that merely mentions it is not a command",
        ),
        Mutation(
            "a heredoc fed to a shell is dropped, so a worktree add inside bash <<EOF is never judged",
            "        if SHELL_WORD.search(line[:m.start()]):",
            "        if False:",
            "a heredoc fed to a SHELL is still read as commands",
        ),
        Mutation(
            "a zero or negative RAILS_FLOW_ZOMBIE_WARN is not clamped",
            '    if count >= max(1, _env_int("RAILS_FLOW_ZOMBIE_WARN", ZOMBIE_WARN)):',
            '    if count >= _env_int("RAILS_FLOW_ZOMBIE_WARN", ZOMBIE_WARN):',
            "is clamped",
        ),
        Mutation(
            "the zombie scan's ps gets a fixed long timeout, longer than the hook's own",
            "timeout=min(3, left)).stdout",
            "timeout=15).stdout",
            "a hanging `ps` is cut off",
        ),
    ),
)
