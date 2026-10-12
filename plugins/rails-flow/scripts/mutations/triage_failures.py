"""Mutation guard: triage_failures. Declared here, run by scripts/mutation_check.py (#1567)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="triage_failures",
    subject="scripts/triage_failures.py",
    selftest="scripts/triage_failures.py",   # --selftest lives in the module
    # The parser and the freshness rule it imports, and the git helper that module imports.
    deps=("scripts/dev_baseline.py", "scripts/fixture_git.py"),
    mutations=(
        Mutation(
            # A stale baseline hiding a regression is the failure this exists to refuse.
            "a stale baseline still marks a known id PREEXISTING",
            "        if fresh and example_id in known and touched is not None and db.file_of(example_id) not in touched:",
            "        if example_id in known and touched is not None and db.file_of(example_id) not in touched:",
            "with a STALE baseline nothing is PREEXISTING",
        ),
        Mutation(
            "ids are matched as substrings, so a baseline line 1 covers line 12",
            "        if fresh and example_id in known and touched is not None and db.file_of(example_id) not in touched:",
            "        if fresh and any(example_id in k or k in example_id for k in known) and touched is not None "
            "and db.file_of(example_id) not in touched:",
            "an id that is only a substring-prefix of a baseline id is NEW, not PREEXISTING",
        ),
        Mutation(
            # One pass in two is not stable. Calling it FLAKY hides a real, intermittent regression.
            "one passing rerun in two is called PASSED ALONE",
            "        if reruns and passed == reruns:",
            "        if reruns and passed >= 1:",
            "a failure that fails one of two reruns is NEW, with 1/2 shown",
        ),
        Mutation(
            "zero reruns marks everything PASSED ALONE",
            "        if reruns and passed == reruns:",
            "        if passed == reruns:",
            "zero reruns never calls anything PASSED ALONE",
        ),
        Mutation(
            "a NEW failure no longer fails the run",
            '    return render(rows, baseline, fresh, why), (1 if any(r["klass"] in BLOCKING for r in rows) else 0)',
            "    return render(rows, baseline, fresh, why), 0",
            "the exit code is 1 when a NEW failure exists",
        ),
        Mutation(
            # #1567 review (2): an example that passes alone is also what an order-dependent regression looks like.
            "a PASSED ALONE failure no longer fails the run",
            "BLOCKING = (NEW, PASSED_ALONE)",
            "BLOCKING = (NEW,)",
            "a PASSED ALONE-only run exits 1, not 0",
        ),
        Mutation(
            # #1567 review (3): dev's red in a spec this branch edited is not evidence about the branch.
            "a baseline id in a spec the branch changed is still PREEXISTING",
            "        if fresh and example_id in known and touched is not None and db.file_of(example_id) not in touched:",
            "        if fresh and example_id in known:",
            "a baseline id in a spec file the branch changed is NOT PREEXISTING",
        ),
        Mutation(
            "an unknown changed-file set still allows PREEXISTING",
            "        if fresh and example_id in known and touched is not None and db.file_of(example_id) not in touched:",
            "        if fresh and example_id in known and (touched is None or db.file_of(example_id) not in touched):",
            "when the branch's changed files are unknown nothing is PREEXISTING",
        ),
        Mutation(
            # #1567 review (4): `0 examples, 0 failures` exits 0 too, and proves nothing about the example.
            "a rerun that matched no example counts as a pass",
            '    return done.returncode == 0 and bool(PASS_LINE.search(db.ANSI.sub("", done.stdout + "\\n" + done.stderr)))',
            "    return done.returncode == 0",
            "a rerun that exits 0 but matched no example does NOT pass",
        ),
        Mutation(
            "a rerun that printed 1 example, 0 failures passes whatever it exited",
            '    return done.returncode == 0 and bool(PASS_LINE.search(db.ANSI.sub("", done.stdout + "\\n" + done.stderr)))',
            '    return bool(PASS_LINE.search(db.ANSI.sub("", done.stdout + "\\n" + done.stderr)))',
            "a rerun that exits 1 fails whatever it printed",
        ),
        Mutation(
            # #1830: the pass line must be the WHOLE summary, or a pending example reads as a pass.
            "a rerun whose only example is pending counts as a pass",
            'PASS_LINE = re.compile(r"\\b1 example, 0 failures?(?![\\w,])")',
            'PASS_LINE = re.compile(r"\\b1 example, 0 failures?\\b")',
            "a rerun whose only example is pending does NOT pass",
        ),
        Mutation(
            "a run with errors outside of examples is triaged from its failed rows",
            "        if db.has_outside_errors(output):",
            "        if False:",
            "a run with errors outside of examples is refused, not triaged as clean",
        ),
        Mutation(
            "unreadable output is triaged as a clean run",
            "    if failures is None:\n        if db.has_outside_errors(output):",
            "    if False:\n        if db.has_outside_errors(output):",
            "unreadable output is refused, not triaged as clean",
        ),
    ),
)
