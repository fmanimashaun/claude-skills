"""Mutation guard: hook_worktree_guard_pointer. Declared here, run by scripts/mutation_check.py (#1581).

The judgement: the SessionStart resume pointer. Split out of one guard that re-ran ALL four worktree fixture groups per mutant: this one runs only `guard_worktree_pointer`.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="hook_worktree_guard_pointer",
    subject="plugins/rails-flow/hooks/scripts/lib/worktree_guard.py",
    selftest="plugins/rails-flow/scripts/check_hook_gates.py",
    selftest_args=("--only", "guard_worktree_pointer"),
    # Each mutant runs only the fixture its `expects` names (#1599); the ones marked `narrow=False` depend on state an
    # earlier fixture builds, cannot run alone, and run the whole sub-group (#1581, surveyed one by one).
    narrow_with="--match",
    needs=("plugins/rails-flow/scripts/fixture_git.py", 
           'plugins/qa-flow/scripts/remote_evidence.py',  # #1581 merge: run by release-gate.sh
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
           'plugins/rails-flow/scripts/ci_verdict_hint.py', 'plugins/rails-flow/scripts/test_preflight.py', 'plugins/rails-flow/scripts/session_reaper.py', 'plugins/rails-flow/scripts/process_containment.py'),
    mutations=(
        Mutation(
            'the resume pointer is never printed',
            '        if wt:\n            lines.append(f"- resume in place:',
            '        if False:\n            lines.append(f"- resume in place:',
            'the session that holds a lane is told where to resume',
            narrow=False,
        ),
        Mutation(
            'every session is pointed at every lane',
            '    for lane_path, row in coordination.lanes_for(record, session_id) if record and session_id else []:',
            '    for lane_path, row in list(record["sessions"].items()) if record else []:',
            'ANOTHER session is not pointed at it',
            narrow=False,
        ),
        Mutation(
            'a merged worktree with uncommitted work is listed as finished',
            ' and not git(w["path"], "status", "--porcelain")[1].strip()]',
            ']',
            'a merged worktree with uncommitted work is NOT listed',
            narrow=False,
        ),
        Mutation(
            'an unmerged worktree is listed as finished',
            'finished = [w for w in existing[1:] if merged(cwd, w["head"], integ) and',
            'finished = [w for w in existing[1:] if True and',
            'the session that holds a lane is told where to resume',
            narrow=False,
        ),
        Mutation(
            'the zombie warning always fires',
            '    if count >= max(1, _env_int("RAILS_FLOW_ZOMBIE_WARN", ZOMBIE_WARN)):',
            '    if True:',
            'below the threshold the zombie warning is silent',
            narrow=False,
        ),
        Mutation(
            'the zombie warning never fires',
            '    if count >= max(1, _env_int("RAILS_FLOW_ZOMBIE_WARN", ZOMBIE_WARN)):',
            '    if False:',
            'a zombie count at the threshold is reported',
            narrow=False,
        ),
        Mutation(
            'a zombie is not recognised by its state',
            'parts[0].startswith("Z")',
            'parts[0].startswith("X")',
            'a zombie count at the threshold is reported',
            narrow=False,
        ),
        Mutation(
            "the zombie advisory prints a parent's whole command line, credentials included",
            '["ps", "-o", "comm=", "-p", str(ppid)]',
            '["ps", "-o", "command=", "-p", str(ppid)]',
            "never prints a parent's command-line arguments",
            narrow=False,
        ),
        Mutation(
            'a junk integer setting raises instead of using its default',
            '        return int(os.environ.get(name) or default)\n    except ValueError:\n        return default',
            '        return int(os.environ.get(name) or default)\n    except ValueError:\n        raise',
            'a junk RAILS_FLOW_ZOMBIE_WARN falls back to the default',
            narrow=False,
        ),
        Mutation(
            'a zero or negative RAILS_FLOW_ZOMBIE_WARN is not clamped',
            '    if count >= max(1, _env_int("RAILS_FLOW_ZOMBIE_WARN", ZOMBIE_WARN)):',
            '    if count >= _env_int("RAILS_FLOW_ZOMBIE_WARN", ZOMBIE_WARN):',
            'is clamped',
            narrow=False,
        ),
        Mutation(
            "the zombie scan's ps gets a fixed long timeout, longer than the hook's own",
            'timeout=min(3, left)).stdout',
            'timeout=15).stdout',
            'a hanging `ps` is cut off',
            narrow=False,
        ),
        Mutation(
            'the stopped-orphan advisory always fires',
            '    if orphans >= max(1, _env_int("RAILS_FLOW_STOPPED_ORPHAN_WARN", STOPPED_ORPHAN_WARN)):',
            '    if True:',
            'below the threshold the advisory is silent',
            narrow=False,
        ),
        Mutation(
            'a RUNNING orphan is counted as stopped',
            'parts[1].startswith("T") and parts[2] == "1"',
            'parts[2] == "1"',
            'four stopped orphans (ppid 1) are counted',
            narrow=False,
        ),
        Mutation(
            'a stopped process that still has a parent is counted as an orphan',
            'parts[1].startswith("T") and parts[2] == "1"',
            'parts[1].startswith("T")',
            'four stopped orphans (ppid 1) are counted',
            narrow=False,
        ),
        Mutation(
            "the advisory never names the owning session",
            'owners = [(pid, known.get(str(pid), "?")) for pid in shown]',
            'owners = [(pid, "?") for pid in shown]',
            'the owning session is named from the environment',
            narrow=False,
        ),
    ),
)
