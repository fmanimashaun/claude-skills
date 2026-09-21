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
    needs=(
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
        "plugins/rails-flow/hooks/scripts/session-start.sh",
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
    ),
)
