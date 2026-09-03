"""Mutation guard: setup_doctrine_crosscheck. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="setup_doctrine_crosscheck",
    subject="plugins/design-flow/scripts/setup_doctrine_crosscheck.py",
    selftest="plugins/design-flow/scripts/setup_doctrine_crosscheck.py",
    # It now IMPORTS the shared doctrine resolver (#617), so the staged mutant dies at import
    # without it. This guard had no `needs` at all, which is why adding one by searching for the
    # next `needs=(` landed in a neighbouring guard — a reminder that "the next occurrence" is
    # not the same as "this one's".
    needs=("plugins/design-flow/scripts/doctrine_path.py",),
    mutations=(
        Mutation(
            "the error direction is disabled — #104 instance 1 ships again",
            "        if key in provided:\n            continue",
            "        if True:\n            continue",
            "instance-1 regression fires",
        ),
        Mutation(
            "every config key is treated as ungenerated, so the fixed state fails too",
            "        if key in provided:\n            continue",
            "        if False:\n            continue",
            "fixed state is clean",
        ),
        Mutation(
            "generated-but-unreferenced is escalated from a warning to an error",
            '        report.warn(\n            f"setup.md sets',
            '        report.error(\n            f"setup.md sets',
            "unreferenced config warns without failing",
        ),
        # Guards the anti-false-positive control: without the `reads and` conjunct, a
        # doctrine that names an out-of-scope initializer (simple_form, owned by
        # /design-flow:component) and reads no config at all would error. That is the
        # exact false positive #150 would die of.
        Mutation(
            "the structural check fires with no config read at all (cries wolf)",
            "    if reads and not inits:",
            "    if not inits:",
            "out-of-scope initializer is not flagged",
        ),
        # A run that scanned nothing prints the same clean verdict as a run that scanned
        # the whole tree. Without this guard the check can be pointed anywhere and still
        # report a pass — the failure mode build_coverage.py --selftest had.
        Mutation(
            "a run that examined zero files reports clean again",
            "    if not scanned:",
            "    if False:",
            "empty doctrine tree is an error, not a pass",
        ),
        # `provided` reverts to a whole-file scan, so a key MENTIONED anywhere in setup.md
        # counts as generated. This was a real defect: the docstring claimed the key was
        # named "precisely at the step that generates the initializer" while the code did
        # set membership over the whole file — claims-vs-enforcement inside the guard
        # written to catch that class.
        Mutation(
            "a mention anywhere in setup.md counts as a generation again",
            "    for chunk in setup_steps(text):\n"
            "        provided |= set(CONFIG_KEY.findall(chunk)) & set(INITIALIZER.findall(chunk))",
            "    provided = set(mentioned)",
            "a stray key mention does not count as generated",
        ),
        # The 1/2 exit split collapses: an environment fault reports as doctrine drift and
        # sends a maintainer hunting a defect that does not exist.
        Mutation(
            "an unreadable input exits 1 (drift) instead of 2 (environment)",
            '        print(f"setup_doctrine_crosscheck: {exc}", file=sys.stderr)\n'
            "        return 2",
            '        print(f"setup_doctrine_crosscheck: {exc}", file=sys.stderr)\n'
            "        return 1",
            "an undecodable doctrine file exits 2, not 1",
        ),
        # The read guard degrades from abort to silent skip. A partial scan then produces a
        # confident verdict over doctrine it never read — the failure mode the whole
        # `scanned` counter exists to prevent, reintroduced one level down.
        Mutation(
            "an unreadable doctrine file is silently skipped instead of aborting",
            '                raise InputError(f"cannot read doctrine file {rel}: {exc}") from exc',
            "                continue",
            "an undecodable doctrine file exits 2, not 1",
        ),
        # Fence tracking is dropped, so a `# ` shell comment inside ``` becomes a step
        # boundary again — splitting a step between its initializer and its key read, and
        # reporting correct input as drift. setup.md's own snippet contains two such lines.
        Mutation(
            "fenced code splits a step again, so correct input reads as drift",
            '        if stripped[:3] in ("```", "~~~"):',
            "        if False:",
            "a fenced code example does not split a step",
        ),
    ),
)
