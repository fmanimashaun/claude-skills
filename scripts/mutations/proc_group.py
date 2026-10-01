"""Mutation guard: proc_group. Declared here, run by scripts/mutation_check.py (#866).

#1459. The one runner every gate and every mutant goes through: its own process group, a group kill on
a timeout, and the partial output carried out. mutation_check's selftest drives it through run_mutation
with a mutant whose grandchild would outlive a plain kill.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="proc_group",
    subject="scripts/proc_group.py",
    selftest="scripts/mutation_check_selftest.py",
    deps=("scripts/mutation_check.py", "scripts/mutation_types.py", "scripts/hermetic_git.py"),
    mutations=(
        Mutation(
            'the child shares our process group',
            '    with subprocess.Popen(argv, start_new_session=True, **kw) as proc:',
            '    with subprocess.Popen(argv, start_new_session=False, **kw) as proc:',
            '#1459: a timed-out mutant left its grandchild running',
        ),
        Mutation(
            'a timeout kills only the direct child',
            '                os.killpg(proc.pid, signal.SIGKILL)',
            '                proc.kill()',
            '#1459: a timed-out mutant left its grandchild running',
        ),
        Mutation(
            'a timeout drops what the run printed',
            '            raise subprocess.TimeoutExpired(argv, timeout, output=out, stderr=err) from None',
            '            raise subprocess.TimeoutExpired(argv, timeout, output=None, stderr=None) from None',
            '#1459: a timed-out mutant must report guard, mutation, elapsed and its tail',
        ),
    ),
)
