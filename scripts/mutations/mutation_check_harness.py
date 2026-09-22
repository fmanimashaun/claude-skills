"""Mutation guard: mutation_check itself. Run by scripts/mutation_check.py (#1129).

THE HARNESS HAD NO GUARD. Every other checker here must prove it can fail; the tool that enforces
that did not, because no guard named it as a subject. Its own selftest is the fixture, and the
invariants that read the REAL repo's guards still do so from the staged tempdir -- so mutating the
staged `mutation_check.py` flips them exactly as it would in production.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="mutation_check_harness",
    subject="scripts/mutation_check.py",
    selftest="scripts/mutation_check_selftest.py",
    deps=("scripts/mutation_types.py",),
    mutations=(
        Mutation(
            # #1129: the import-completeness invariant. Adding an import to a shipped module orphans
            # every neighbouring guard that stages it without the new dependency -- the mutant dies
            # on ModuleNotFoundError, which is an ENVIRONMENTAL failure, not a caught mutation.
            # Three occurrences (#1113, #1114, #1133) and all three surfaced only in the sweep.
            "a module-scope import is no longer seen, so an unstaged dependency passes",
            "            if isinstance(node, ast.Import):",
            "            if False:",
            "",
        ),
        Mutation(
            # THE CARVE-OUT, and it is what keeps the rule usable: a `def`-scope import is optional
            # at load time. Counting those flagged SIX correct guards on the first run -- every
            # shipped script that imports its own selftest inside `if args.selftest:`.
            "function-scope imports count again, so correct guards are reported",
            "    scan(tree.body)",
            "    scan([n for n in ast.walk(tree)])",
            "",
        ),
    ),
)
