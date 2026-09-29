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
        # The wrong-fixture report's tail (#1493): present, 12 lines, 300 characters wide, decoded.
        Mutation(
            "a wrong-fixture report drops the mutant's output",
            '                    + "\\n".join(f"      {line[:300]}" for line in output.strip().splitlines()[-12:])]',
            '                    + ""]',
            "a wrong-fixture report does not carry the mutant's exit and output",
        ),
        Mutation(
            'the tail is no longer bounded to 12 lines',
            '                    + "\\n".join(f"      {line[:300]}" for line in output.strip().splitlines()[-12:])]',
            '                    + "\\n".join(f"      {line[:300]}" for line in output.strip().splitlines()[-1200:])]',
            'a wrong-fixture report does not carry exactly the last 12 lines of output',
        ),
        Mutation(
            "the tail's lines are no longer cut to 300 characters",
            '                    + "\\n".join(f"      {line[:300]}" for line in output.strip().splitlines()[-12:])]',
            '                    + "\\n".join(f"      {line}" for line in output.strip().splitlines()[-12:])]',
            'a wrong-fixture report does not cut each output line to 300 characters',
        ),
        Mutation(
            'a non-UTF-8 byte raises before the report prints',
            '        result = subprocess.run(argv, cwd=workdir, capture_output=True, text=True, errors="replace",',
            '        result = subprocess.run(argv, cwd=workdir, capture_output=True, text=True,',
            "a non-UTF-8 byte in a mutant's output raised before the report printed",
        ),
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
        Mutation(
            # #1444: main's pool must keep run_guard's rule -- an INERT baseline scores nothing.
            "the pool runs mutations of a guard whose baseline failed",
            "zip(guards, baselines) if not b for m",
            "zip(guards, baselines) for m",
            "an INERT baseline must end its guard",
        ),
        Mutation(
            # #1444: the transitive scan. check_slices went INERT through an import made by a need.
            "the import scan stops at one level again",
            "            pending.append(str(sibling.relative_to(base)))",
            "            pass",
            "an unstaged import's own imports must be reported too",
        ),
        Mutation(
            # #1444: THE check_slices case -- a need's own imports went unread.
            "needs files are no longer scanned for imports",
            "    pending = sorted(staged | {n for n in guard.needs if (base / n).is_file()})",
            "    pending = sorted(staged)",
            "a need no staged file imports must still be scanned",
        ),
    ),
)
