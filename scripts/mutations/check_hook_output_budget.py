"""Mutation guard: check_hook_output_budget. Run by scripts/mutation_check.py (#1085)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_hook_output_budget",
    subject="scripts/check_hook_output_budget.py",
    selftest="scripts/check_hook_output_budget.py",   # --selftest lives in the module
    # The selftest READS these -- it discovers SessionStart hooks from each plugin's
    # hooks.json and runs the scripts they name. Staged mutants get no `plugins/` tree
    # otherwise, and the discovery assertions fail for an environmental reason the
    # `expects` check correctly refuses to count as a caught mutation.
    needs=("plugins/rails-flow/scripts/fixture_git.py", 
        # This repo's OWN SessionStart hook -- the selftest asserts it is discovered, and
        # a staged mutant has no `.claude/` tree without these two.
        ".claude/settings.json",
        ".claude/hooks/scripts/maintainer-status.sh",
        "plugins/design-flow/hooks/hooks.json",
        "plugins/pipeline/hooks/hooks.json",
        "plugins/pipeline/hooks/scripts/pipeline-status.sh",
        "plugins/qa-flow/hooks/hooks.json",
        "plugins/qa-flow/hooks/scripts/qa-status.sh",
        "plugins/rails-flow/hooks/hooks.json",
        "plugins/rails-flow/hooks/scripts",   # session-start.sh and lib/where_stopped.py, which the fixture's pointer line needs (#1886)
    ),
    mutations=(
        Mutation(
            # The ratchet itself. Without the comparison a hook can grow without limit while the
            # gate keeps reporting clean -- and the cost is paid on every compaction, silently.
            "growth stops being a finding, so a hook can expand unnoticed",
            "        elif size > recorded + TOLERANCE:",
            "        elif False:",
            "growth beyond the tolerance is reported",
        ),
        Mutation(
            # THE OTHER DIRECTION, and the one that makes a ratchet usable. A check firing on any
            # CHANGE punishes the fix as loudly as the regression, so nobody trims anything.
            "any change fires it, including a hook that got smaller",
            "        elif size > recorded + TOLERANCE:",
            "        elif size != recorded:",
            "shrinking is NOT reported",
        ),
        Mutation(
            # A new hook with no baseline must not read as fine -- that is how one ships
            # unmeasured, which is the state this whole check was written to end.
            "a missing baseline defaults to the measured size, so a new hook is never reported",
            "        recorded = baseline.get(plugin)",
            "        recorded = baseline.get(plugin, size)",
            "a hook with no baseline is reported, not skipped",
        ),
        Mutation(
            # DETERMINISM IS THE BASIS OF THE RATCHET. Measuring the live tree instead of the
            # fixture makes the baseline drift on an unrelated commit, and a gate that goes red
            # on its own is one somebody switches off.
            # `cwd` is what actually pins the measurement -- the hooks resolve
            # `docs/brain/MEMORY.md` relative to the working directory, not from
            # CLAUDE_PROJECT_DIR. A first draft mutated the env var and SURVIVED, which is how
            # we learned which lever the hook really reads.
            "the run leaves the fixture, so the live tree is measured instead",
            "            proc = subprocess.run([\"bash\", str(path)], cwd=project, env=env,",
            "            proc = subprocess.run([\"bash\", str(path)], cwd=REPO, env=env,",
            "the hook reads the FIXTURE, not this repo",
        ),
        Mutation(
            "a relative age is no longer a ticking value, so `last swept 14d ago` is injected unnoticed (#1886)",
            '("a relative age", re.compile(r"\\b\\d+',
            '("a relative age", re.compile(r"\\bNEVER\\d+',
            "a ticking value is reported: brain-review due: last swept 14d ago",
        ),
        Mutation(
            "an ISO timestamp is no longer a ticking value",
            '("an ISO timestamp", re.compile(r"\\b\\d{4}',
            '("an ISO timestamp", re.compile(r"\\bNEVER\\d{4}',
            "a ticking value is reported: stopped (last turn, 2026-10-11T22:48Z)",
        ),
        Mutation(
            "a time of day is no longer a ticking value",
            '("a time of day", re.compile(r"\\b\\d{1,2}',
            '("a time of day", re.compile(r"\\bNEVER\\d{1,2}',
            "a ticking value is reported: measured at 14:03",
        ),
        Mutation(
            "an epoch is no longer a ticking value",
            '("an epoch", re.compile(r"\\b1[5-9]',
            '("an epoch", re.compile(r"\\bNEVER1[5-9]',
            "a ticking value is reported: stamp 1700000000",
        ),
        Mutation(
            "a load reading is no longer a ticking value",
            '("a load or uptime reading", re.compile(r"\\b(?:load',
            '("a load or uptime reading", re.compile(r"\\bNEVER(?:load',
            "a ticking value is reported: load averages: 24.30 24.52",
        ),
        Mutation(
            "the scan matches every line, so a stable date reads as ticking",
            '            if pattern.search(line):',
            '            if True:',
            "a stable value is not reported: brain-review due since 2026-01-08 (cadence 7d)",
        ),
        Mutation(
            "the fixture drops the aged review stamp, so the line whose age ticked is never printed or scanned",
            '    (project / "docs/brain/.last-review").write_text("1700000000\\n", encoding="utf-8")',
            '    pass',
            "the fixture makes the aged review line and the where-stopped pointer print, so the scan reads them",
        ),
        Mutation(
            "the fixture leaves no unsaved work, so the where-stopped pointer is never printed or scanned",
            '        (project / "unsaved.txt").write_text("work in progress\\n", encoding="utf-8")   # so the pointer prints (#1886)',
            '        pass',
            "the fixture makes the aged review line and the where-stopped pointer print, so the scan reads them",
        ),
    ),
)
