"""Mutation guard: build_coverage_artifact. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# rails-flow #126. Two of these break a POSITIVE rule; two break a fixture whose job is to
# stay SILENT, which is the direction that decides whether a mermaid linter survives contact
# with real diagrams. Both directions are declared on purpose: a guard proven only to fire is
# half-proven, and the half nobody checks is the half that gets the tool switched off.
GUARD = Guard(
    name="build_coverage_artifact",
    subject="scripts/build_coverage_artifact.py",
    selftest="scripts/build_coverage_artifact_selftest.py",
    # The builder imports build_coverage rather than parsing it, and the --check fixtures build a
    # real page, so the matrix source has to exist in the workdir. Without these the selftest dies
    # at import and EVERY mutation reports as "caught" — by a traceback, not by a fixture.
    deps=("scripts/build_coverage.py",),
    needs=("skills/design-system/references/coverage.md",),
    mutations=(
        Mutation(
            "the drift comparison stops comparing, so a stale artifact passes",
            '        if committed.replace("\\r\\n", "\\n") != doc.replace("\\r\\n", "\\n"):',
            '        if False:',
            "--check FAILS on a stale artifact",
        ),
        # The gate must read git, not the working copy. An `is_file()` + `read_text` version
        # passed a freshly built, never-added page — the exact "invisible deliverable" this
        # whole change exists to close, waved through by the gate built to close it.
        Mutation(
            "the gate goes back to trusting the working copy instead of the commit",
            "        committed = committed_blob(rel_out)",
            '        committed = args.out.read_text(encoding="utf-8") if args.out.is_file() else None',
            "a built-but-untracked page is DRIFT, not a pass",
        ),
        Mutation(
            "an absent artifact is reported as OK instead of drift",
            '            print(f"DRIFT: {rel_out} is not committed — the artifact is a deliverable other machines "\n                  f"must be able to see, not a local build.\\n{remedy}", file=sys.stderr)\n            return 1',
            '            print(f"DRIFT: {rel_out} is not committed — the artifact is a deliverable other machines "\n                  f"must be able to see, not a local build.\\n{remedy}", file=sys.stderr)\n            return 0',
            "--check FAILS when the artifact is nowhere at all",
        ),
        Mutation(
            "git state leaks back into the embedded stamp",
            '        "label": f"Coverage as of v{release}",',
            '        "label": f"Coverage as of v{release}",\n        "state": "dirty" if prov["dirty"] else "clean",',
            "the embedded stamp carries no git state whatsoever",
        ),
        Mutation(
            "the upstream totals go back to walking the licensed corpora",
            '    tw_count, fb_count = committed_totals.get("tw"), committed_totals.get("fb")',
            '    tw_count, fb_count = len(bc.discover_tw()), len(bc.discover_fb())',
            "collect() requires the licensed corpora",
        ),
    ),
)
