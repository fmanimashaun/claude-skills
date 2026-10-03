"""Mutation guard: pid_record. Declared here, run by scripts/mutation_check.py (#866).

#1556. The hand-off by which a process-group fixture learns the pids its gate started: an atomic
write, so a reader -- or a kill -- never meets the empty file `open(path, 'w')` leaves before its
content lands (CI read it as `int('')`), and a bounded wait for a record that comes late. Every
fixture injects its delay deterministically rather than waiting for a loaded runner to line it up.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="pid_record",
    subject="scripts/pid_record.py",
    selftest="scripts/pid_record_selftest.py",
    mutations=(
        Mutation(
            'the record is written in place, so a reader meets the truncated file',
            '    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")',
            '    tmp = path',
            '#1556: a reader during a slow write saw a torn pid record',
        ),
        Mutation(
            'a late record is read as missing',
            '    while not path.exists() and time.monotonic() < deadline:',
            '    while False:',
            'was not waited for',
        ),
        Mutation(
            'an empty record passes as no record',
            '        raise ValueError(f"{path}: the pid record exists but is empty -- a torn write (#1556)")',
            '        return []',
            '#1556: an empty pid record must raise',
        ),
    ),
)
