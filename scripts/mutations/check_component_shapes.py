"""Mutation guard: check_component_shapes. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #874. The checker reconciles the design-system catalogue (every `## ` row across components.md and
# components-commerce.md) against the pen shapes sidecar in both directions and validates each
# drawable entry. Its selftest had 17 fixtures and nothing proving any of them could fail: a
# selftest without a guard is a claim. Every mutation here disables one branch the fixtures
# were written for, and each names the fixture that must catch it. Deliberately absent: a
# mutation on CATALOGUE_FILES -- main() reads the corpus, the selftest hands check() its own
# markdown, so a mutation there is unobservable here; build_coverage's guard holds that side.
GUARD = Guard(
    name="check_component_shapes",
    subject="scripts/check_component_shapes.py",
    selftest="scripts/check_component_shapes.py",   # --selftest lives in the module itself
    mutations=(
        Mutation(
            "a catalogue row with no shape entry goes unreported, so a component vanishes from pen",
            "    missing = [row for row in rows if row not in entries]",
            "    missing = []",
            "a row with no shape is reported",
        ),
        Mutation(
            "a shape with no catalogue row goes unreported, so pen offers what rails-ui-composer cannot build",
            "    orphans = [name for name in entries if name not in rows]",
            "    orphans = []",
            "a shape with no row is reported",
        ),
        Mutation(
            "the one-cause collapse for an empty sidecar is dropped, so N identical findings bury the diagnosis",
            "    if rows and len(missing) == len(rows):",
            "    if False:",
            "an empty sidecar is ONE finding",
        ),
        Mutation(
            "the one-cause collapse for a mis-keyed sidecar is dropped, so one mistake reports 2N times",
            "    if entries and len(orphans) == len(entries):",
            "    if False:",
            "a wrongly-keyed file is 2 findings",
        ),
        Mutation(
            "doctrine sections are counted as components, so every `## The ...` section wants a shape",
            '    return [r for r in rows if not r.startswith("The ")]',
            "    return rows",
            "a reconciled pair has no findings",
        ),
        Mutation(
            "a non-drawable entry without a reason is accepted, so a decision is indistinguishable from a gap",
            '            if not str(entry.get("why", "")).strip():',
            "            if False:",
            "non-drawable without a reason is reported",
        ),
        Mutation(
            "an unknown shape kind is accepted",
            "        if shape not in SHAPE_KINDS:",
            "        if False:",
            "an unknown shape kind is reported",
        ),
        Mutation(
            "a drawable entry with no parts is accepted, so an empty box wears a component's name",
            "        if not parts:",
            "        if False:",
            "a drawable entry with no parts is reported",
        ),
        Mutation(
            "an unknown part kind is accepted, so the generator is handed something it cannot draw",
            '            if part.get("kind") not in PART_KINDS:',
            "            if False:",
            "an unknown part kind is reported",
        ),
        Mutation(
            "an undeclared role is accepted, so it is silently left out of the library",
            '                if role and f"--{role}" not in roles:',
            "                if False:",
            "an undeclared role is reported",
        ),
        # The nested walk: flattening only the top level would pass every fixture but the nested one.
        Mutation(
            "nested parts are not walked, so a column's children escape every check",
            "def walk_parts(parts: list) -> list[dict]:",
            "def walk_parts(parts: list) -> list[dict]:\n    return [p for p in parts if isinstance(p, dict)]",
            "a nested part is checked",
        ),
        Mutation(
            '#2272: an entry that declares no `variants` goes unreported',
            '        if axis not in entry:',
            '        if False:',
            'an entry with no `variants` is reported',
        ),
        Mutation(
            '#2272: an empty or duplicated list is accepted',
            '            if not value or not all(isinstance(n, str) and n.strip() for n in value) or len(set(value)) != len(value):',
            '            if False:',
            'an empty list is reported',
        ),
        Mutation(
            '#2272: the old `"enum"` placeholder, or any non-list non-none value, is accepted',
            '        elif not (isinstance(value, dict) and set(value) == {"none"} and isinstance(value["none"], str) and value["none"].strip()):',
            '        elif False:',
            'the old `"enum"` placeholder is reported',
        ),
        Mutation(
            '#2272: a section with no generated line, or a hand-edited one, goes unreported',
            '    elif want is not None and marked != [want]:',
            '    elif False:',
            'a missing generated line is reported',
        ),
        Mutation(
            '#2272: a stale generated line, for an entry that states no list, goes unreported',
            '    if want is None and marked:',
            '    if False:',
            'a generated line for an entry that states no list is reported',
        ),
        Mutation(
            '#2272: a declared name the prose never mentions goes unreported',
            '            if not re.search(rf"(?<![\\w-]){re.escape(word)}(?![\\w-])", prose, re.I):',
            '            if False:',
            'a name the prose never mentions is reported',
        ),
        Mutation(
            '#2272: the generated line counts as prose, so it vouches for its own names',
            '    prose = "\\n".join(line for line in section.split("\\n") if not line.rstrip().endswith(AXES_MARK))',
            '    prose = section',
            'a name the prose never mentions is reported (the generated line does not count)',
        ),
        Mutation(
            "#2272: a section that names a `Ui::` component may exempt itself with `drawable: false`",
            '    named = sorted(set(re.findall(r"Ui::\\w+", section)))',
            "    named = []",
            "a non-drawable entry whose section names a `Ui::` component is refused",
        ),
        Mutation(
            "#2272: a section that states a Variants or Sizes line may exempt itself with `drawable: false`",
            '    states = re.search(r"\\*\\*(?:variants?|sizes?)\\b", section, re.I)',
            "    states = None",
            "a non-drawable entry whose section carries a Variants line is refused",
        ),
        Mutation(
            "#2272: the hidden-component rule is not applied to any non-drawable entry",
            "            problems += hidden_component(name, by_heading.get(name))",
            "            problems += []",
            "a non-drawable entry whose section names a `Ui::` component is refused",
        ),
    ),
)
