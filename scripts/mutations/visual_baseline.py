"""Mutation guard: visual_baseline. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #112. The first is the acceptance criterion in one line: a missing baseline must be neither a
# pass nor a failure. Mutating it to a pass makes a brand-new screen 'visually correct' the day
# it is written, which is exactly backwards -- nothing has ever been reviewed.
GUARD = Guard(
    name="visual_baseline",
    subject="plugins/qa-flow/scripts/visual_baseline.py",
    selftest="plugins/qa-flow/scripts/visual_baseline.py",
    needs=("plugins/qa-flow/scripts/crawl_collector.js",),
    mutations=(
        Mutation(
            "a missing baseline is treated as a pass",
            '        if not shot.get("baselinePresent"):',
            '        if False:',
            "a missing baseline is `new`",
        ),
        Mutation(
            "an undeterministic run is judged instead of refused",
            "    missing = [k for k in DETERMINISM_KEYS if not d.get(k)]",
            "    missing = []",
            "motion not frozen",
        ),
        Mutation(
            "the first matching prefix wins instead of the longest",
            '        if route.startswith(pattern) and len(pattern) > best:',
            '        if route.startswith(pattern) :',
            "the longest matching prefix wins",
        ),
        # The ignore-region half of #112. `ignored` shipped in the schema, emitted as a
        # hardcoded `[]` and read by nobody, so the field existed and the feature did not.
        # These three break the parts that make it real rather than declared.
        Mutation(
            "the mask a config demands is trusted instead of verified against the run",
            "        if want != got:",
            "        if False:",
            "a mask the config demands but the run never applied is refused",
        ),
        Mutation(
            "a per-route mask REPLACES the global list instead of adding to it",
            '    out = list(visual.get("ignore") or [])',
            "    out = []",
            "a per-route mask ADDS to the global list",
        ),
        Mutation(
            "an unreadable line in the visual block is skipped and silently defaulted",
            "        raise Unusable(_unreadable(path, lineno, raw))",
            "        continue",
            "an unreadable tolerance is refused, not silently defaulted",
        ),
        Mutation(
            "a regression reports its ratio without the diff image",
            '            picture = shot.get("diff") or "(none written: the collector produced '
            'no diff image)"',
            '            picture = "(none)"',
            "a regression names its diff image",
        ),
    ),
)
