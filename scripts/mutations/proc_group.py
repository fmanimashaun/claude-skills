"""Mutation guard: proc_group. Declared here, run by scripts/mutation_check.py (#866).

#1459. The one runner every gate and every mutant goes through: its own session, a kill of every
descendant and every group they lead on a timeout OR an interrupt, a pool that kills its live children
on Ctrl-C, a bounded wait for an escapee, and the partial output carried out. mutation_check's selftest
drives it through run_mutation (1e) and directly (`_proc_group_fixtures`: nested sessions, Ctrl-C on a
run and on main's pool, an orphan in the group, a double-forked escapee).
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="proc_group",
    subject="scripts/proc_group.py",
    selftest="scripts/mutation_check_selftest.py",
    deps=("scripts/mutation_check.py", "scripts/mutation_incremental.py", "scripts/mutation_types.py", "scripts/hermetic_git.py", "plugins/rails-flow/scripts/process_containment.py",),
    mutations=(
        # #1635: a backgrounded process inherits SIGINT ignored; the reset is only for that case.
        Mutation(
            "a backgrounded run keeps an ignored SIGINT, so the Ctrl-C selftests never fire",
            "    if signal.getsignal(signal.SIGINT) == signal.SIG_IGN:",
            "    if False:",
            "restore_sigint must reset an inherited-ignored SIGINT",
        ),
        Mutation(
            "restore_sigint overrides a handler someone installed",
            "    if signal.getsignal(signal.SIGINT) == signal.SIG_IGN:",
            "    if True:",
            "restore_sigint must leave a normal SIGINT alone",
        ),
        # #1635: the cost is CPU seconds of the run and everything it waited for.
        Mutation(
            "the cost wrapper reports nothing, so every run bills wall time",
            "ru.ru_utime + ru.ru_stime",
            "0.0",
            "a run that burns 1 s of CPU must be billed about 1 s",
        ),
        Mutation(
            "the cost wrapper reads its own CPU, not its children's, so a descendant is never billed",
            "resource.getrusage(resource.RUSAGE_CHILDREN)",
            "resource.getrusage(resource.RUSAGE_SELF)",
            "a run that burns 1 s of CPU must be billed about 1 s",
        ),
        Mutation(
            "the cost wrapper swallows the command's exit code",
            "sys.exit(rc if rc >= 0 else 128 - rc)",
            "sys.exit(0)",
            "pass the command's own exit code through",
        ),
        Mutation(
            'the child shares our process group',
            '        proc = subprocess.Popen(argv, start_new_session=True, **kw)',
            '        proc = subprocess.Popen(argv, start_new_session=False, **kw)',
            '#1459: a timed-out run left an orphan in its group running',
        ),
        Mutation(
            'a timeout kills only the direct child',
            '            kill_tree(proc.pid)\n            out, err = _drain(proc)',
            '            _signal(proc.pid, signal.SIGKILL)\n            out, err = _drain(proc)',
            '#1459: a timed-out mutant left its grandchild running',
        ),
        Mutation(
            'a timeout drops what the run printed',
            '            raise subprocess.TimeoutExpired(argv, timeout, output=out, stderr=err) from None',
            '            raise subprocess.TimeoutExpired(argv, timeout, output=None, stderr=None) from None',
            '#1459: a timed-out mutant must report guard, mutation, elapsed and its tail',
        ),
        Mutation(
            # review of #1525, blocker 1: each inner proc_group.run is a session the outer killpg never reached
            "a timeout kills the child's group but not the sessions nested under it",
            '            kill_tree(proc.pid)\n            out, err = _drain(proc)',
            '            _signal(proc.pid, signal.SIGKILL, group=True)\n            out, err = _drain(proc)',
            '#1459: a timed-out run left a nested child running',
        ),
        Mutation(
            # review of #1525, blocker 2
            'Ctrl-C leaves the child running',
            '            # Ctrl-C or SystemExit: the child is in a session of its own and never saw the signal.\n            kill_tree(proc.pid)\n',
            '            # Ctrl-C or SystemExit: the child is in a session of its own and never saw the signal.\n',
            "#1459: Ctrl-C left a run's child running",
        ),
        Mutation(
            'an interrupted pool joins without killing its live children',
            '    except BaseException:\n        kill_all()\n',
            '    except BaseException:\n',
            "#1459: Ctrl-C under mutation_check's pool left work running",
        ),
        Mutation(
            'an interrupted run still starts new children',
            '        if _closing.is_set():',
            '        if False:',
            '#1459: after an interrupt a new child still started',
        ),
        Mutation(
            # review of #1525, suggestions 3 and 4
            'the wait for an escapee holding the pipe is unbounded',
            '        out, err = proc.communicate(timeout=ESCAPEE_WAIT)',
            '        out, err = proc.communicate()',
            '#1459: an escapee holding the pipe must cost at most ESCAPEE_WAIT',
        ),
        Mutation(
            "an escapee's timeout drops what the child printed",
            '        out, err = again.output, again.stderr',
            '        out, err = None, None',
            "#1459: an escapee's timeout dropped what the child printed",
        ),
        Mutation(
            # #1548
            'an exception mid-walk skips the kill, leaving the tree SIGSTOPped',
            '    finally:\n        _kill_frozen(groups, frozen, own)',
            '    except BaseException:\n        raise\n    _kill_frozen(groups, frozen, own)',
            '#1548: an exception mid-walk left the tree stopped or running',
        ),
        Mutation(
            # #1548
            "a new pool inherits the last pool's _closing, so it starts nothing",
            '    _closing.clear()\n    executor = ThreadPoolExecutor(max_workers=max_workers)',
            '    executor = ThreadPoolExecutor(max_workers=max_workers)',
            '#1548: a pool started after an interrupted one refused every child',
        ),
    ),
)
