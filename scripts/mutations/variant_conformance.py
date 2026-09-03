"""Mutation guard: variant_conformance. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# design-flow #160. THREE of these ten are caught by a fixture whose job is to stay SILENT, and
# those are the ones worth having: this check stands between an agent and a user's repo, and
# every rule it carries has an obvious over-broad form. `bg-primary` is a role token AND a
# string ending in a primitive's suffix; an ERB comment naming `--color-x:` is prose AND a
# custom-property declaration; `# do not remove` is a comment AND a line ending in `do`. Flag
# the wrong half of any pair and variant mode reports findings on every correct set it is
# given, which is how a checker gets switched off wholesale.
GUARD = Guard(
    name="variant_conformance",
    subject="plugins/design-flow/scripts/variant_conformance.py",
    selftest="plugins/design-flow/scripts/variant_conformance.py",
    # It RUNS the #157 detector rather than reimplementing it, and the detector in turn imports
    # `rendered_conformance` for the shared palette-step definition. Without both, every mutant
    # dies at import and reads as "caught" by a traceback instead of by the fixture named below.
    # TRANSITIVE, and that is the trap: this stages `llm_tell_detector`, which now imports
    # `doctrine_path` (#617). Adding an import to a module makes every guard that stages THAT
    # module need the new file too — so a `needs` list is the subject's imports plus theirs.
    needs=("plugins/design-flow/scripts/llm_tell_detector.py",
           "plugins/design-flow/scripts/doctrine_path.py",
           "plugins/design-flow/scripts/rendered_conformance.py",
           "plugins/design-flow/scripts/conformance_collector.js"),
    mutations=(
        Mutation(
            "the role layer is read as primitives, so every conformant variant is a finding",
            "        if opening.group(1):",
            "        if False:",
            "role tokens are NOT flagged as primitives",
        ),
        Mutation(
            "an ERB comment naming a custom property becomes a styling violation",
            "        if tells.COMMENT_LINE.match(line):\n            continue\n"
            "        for pattern, what in STYLING:",
            "        if False:\n            continue\n        for pattern, what in STYLING:",
            "a comment naming a custom property is NOT a finding",
        ),
        Mutation(
            "an unresolvable pack becomes a silent skip instead of a finding",
            "    if not theme:",
            "    if False:",
            "an unresolvable pack is a finding, not a skip",
        ),
        Mutation(
            "the distinctness rule stops noticing two variants with one arrangement",
            "        twin = signatures.get(signature)",
            "        twin = None",
            "two variants differing only in copy fire",
        ),
        Mutation(
            "a set of one passes, so variant mode degenerates to the yes/no it replaces",
            "    if len(entries) < 2:",
            "    if len(entries) < 1:",
            "a set of one fires",
        ),
        Mutation(
            "the rationale requirement is dropped and the choice becomes aesthetic again",
            '        if not str(entry.get("rationale") or "").strip():',
            "        if False:",
            "a blank rationale fires",
        ),
        Mutation(
            "the undeclared-partial direction is dropped, so discard misses a leftover",
            '        if entry == MANIFEST or entry in declared or not entry.endswith(".erb"):',
            "        if True:",
            "an undeclared partial in the set fires",
        ),
        Mutation(
            "the route tracker stops popping, so a CLOSED dev block launders a later route",
            "        if _CLOSES.match(line) and stack:",
            "        if False and stack:",
            "a closed development block does not launder a later route",
        ),
        Mutation(
            "an empty scaffolding directory reads as a clean pass",
            "    if not set_dirs:",
            "    if False:",
            "an empty variants directory is fatal too",
        ),
        Mutation(
            "comments re-enter the route tracker, so `# do` unbalances the stack",
            '        if line.lstrip().startswith("#"):\n            continue',
            "        if False:\n            continue",
            "a comment does not unbalance the block tracker",
        ),
    ),
)
