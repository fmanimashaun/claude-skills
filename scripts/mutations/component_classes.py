"""Mutation guard: component_classes. Declared here, run by scripts/mutation_check.py (#2192)."""
from mutation_types import Guard, Mutation  # noqa: F401

# Every mutation here lets an UNCLASSIFIED or WRONGLY-NEUTRAL component read as classified, which is what the page exists to refuse.
GUARD = Guard(
    name="component_classes",
    subject="scripts/component_classes.py",
    selftest="scripts/component_classes.py",   # --selftest lives in the module itself
    needs=("scripts/rails_assumptions.py", "scripts/hermetic_git.py", "plugins/rails-flow/scripts/fixture_git.py"),   # rails_assumptions imports both at load
    mutations=(
        Mutation(
            "a proof entry for a component that is not neutral passes",
            "        if match is None or not match[\"proven\"]:",
            "        if False:",
            "a proof entry for a component that is not there is a finding",
        ),
        Mutation(
            "a component not recorded in the proof file is shown proven",
            '        comp["proven"] = comp["path"] in proven and bool(comp["info"]) and comp["info"]["class"] == "neutral"',
            '        comp["proven"] = bool(comp["info"]) and comp["info"]["class"] == "neutral"',
            "a component not in the proof file is not shown proven",
        ),
        Mutation(
            "a committed page that differs from a clean build passes --check",
            "            elif blob != built:",
            "            elif False:",
            "--check on a stale committed page is a finding",
        ),
        Mutation(
            "a page that was never committed passes --check",
            "            if blob is None:",
            "            if False:",
            "--check on a page that was built but never committed is a finding",
        ),
        Mutation(
            "a component nothing declares is accepted",
            "        if info is None:\n            findings.append(",
            "        if info is None:\n            continue\n            findings.append(",
            "a component nothing declares is a finding",
        ),
        Mutation(
            "a neutral component that names Rails is accepted",
            "            if (comp[\"rails\"] or comp[\"next\"]) and not incidental:",
            "            if False:",
            "a neutral component naming Rails is a finding",
        ),
        Mutation(
            "a mixed component with no seam or issue is accepted",
            '        if info["class"] == "mixed" and (not info["seam"] or not isinstance(info["issue"], int)):',
            "        if False:",
            "a mixed component with no seam or issue is a finding",
        ),
        Mutation(
            "a declaration that matches nothing is accepted",
            "        if not used_declared[index]:",
            "        if False:",
            "a declaration that matches nothing is a finding",
        ),
        Mutation(
            "a class outside the four is accepted",
            "        if info[\"class\"] not in CLASSES:",
            "        if False:",
            "a class outside the four is a finding",
        ),
        Mutation(
            "a gate row stops taking its script's class",
            '        if script is not None and script["info"] is not None:',
            "        if False:",
            "a gate row takes the class of the script it runs",
        ),
        Mutation(
            "a Next.js reference is no longer a hit",
            '    next_hits = ra.scan(root, files, NEXT_PATTERNS)',
            "    next_hits = {}",
            "a neutral component naming Next.js is a finding",
        ),
    ),
)
