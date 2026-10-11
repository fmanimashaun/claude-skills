"""Mutation guard: scaffold_teardown. Declared here, run by scripts/mutation_check.py (#866). The teardown's whole value is that it can fail: a leftover, or a docker that cannot be asked (#1836)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="scaffold_teardown",
    subject="scaffold/qa/e2e/support/teardown.ts",
    selftest="scripts/scaffold_ts_tests.py",
    needs=("scaffold/qa/e2e/support/teardown.test.ts",),
    mutations=(
        Mutation(
            'a failed docker query reads as nothing left (the Retask `|| true` defect)',
            '  if (r.error || r.status !== 0) {',
            '  if (false) {',
            'docker that cannot be asked FAILS CLOSED',
        ),
        Mutation(
            'leftover volumes are not counted',
            '  if (containers.length || volumes.length) {',
            '  if (containers.length) {',
            'a leftover container or volume of the stack FAILS',
        ),
        Mutation(
            "a prefix match without a separator counts another project's names",
            '  const ours = (name: string) => name === stack || name.startsWith(`${stack}-`) || name.startsWith(`${stack}_`);',
            '  const ours = (name: string) => name.includes(stack);',
            "another project's names do not count",
        ),
        Mutation(
            'any stack name is accepted, so `*` or `` match everything or nothing',
            '  if (!/^[a-z0-9][a-z0-9_-]*$/.test(stack)) throw',
            '  if (false) throw',
            'a stack name that is not a plain name is refused',
        ),
    ),
)
