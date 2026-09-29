"""Mutation guard: check_component_passthrough. Declared here, run by scripts/mutation_check.py."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_component_passthrough",
    subject="scripts/check_component_passthrough.py",
    selftest="scripts/check_component_passthrough.py",   # --selftest lives in the module itself
    mutations=(
        Mutation(
            # THE HALF THAT WAS MISSING WHEN THIS CHECK WAS FIRST WRITTEN, and the reason it has
            # two. Widening 17 signatures made a signature-only check green while every one of
            # them still discarded the hash -- Ruby binds `**attrs` and drops it with no error,
            # so a caller's `data-controller` vanishes SILENTLY where a fixed keyword list would
            # at least have raised. The check would have certified a quieter defect than it fixed.
            "every component counts as storing the splat, so accept-and-drop passes",
            '        stored = bool(re.search(r"@attrs\\b\\s*=|=\\s*[^=\\n]*\\battrs\\b", blob))',
            "        stored = True",
            "a splat that is accepted and DROPPED reads as not stored",
        ),
        Mutation(
            # The first half: a fixed keyword list is the loud form of the same defect, and it is
            # what 17 of 23 shipped components had.
            "a fixed keyword list stops being reported",
            '            elif "**" not in sig:',
            "            elif False:",
            "one non-compliant component is reported, by name",
        ),
        Mutation(
            # A check that reports clean over a file it never opened is the vacuous pass this
            # repository is organised against -- "0 findings over 0 components" reads identically
            # to a healthy run.
            "a missing source file reads as a clean run",
            '            findings.append(f"{rel}: not found — this check examined none of its components")',
            "            continue",
            "a missing source file is a finding, not a clean run",
        ),
        Mutation(
            # A wrapped signature is where the first count of this defect went wrong: a one-line
            # regex reported 21 classes where there are 23, and it under-counted in the FLATTERING
            # direction -- a component read as compliant because its splat sat on the second line.
            "a wrapped signature is truncated at the first line, hiding its splat",
            "    depth, out = 0, []",
            '    return body[m.start():].split(chr(10))[0]',
            "a signature wrapped across lines is read whole",
        ),
        # #1434: the first `def initialize(` in the body, a nested class's included, is judged again.
        Mutation(
            "nested class bodies are read as the component's own",
            '        blob = "\\n".join(own_lines(body))',
            '        blob = "\\n".join(body)',
            "a nested class's initializer declared first is not the component's",
        ),
        Mutation(
            "a nested body never ends, so the component's own initializer after it vanishes",
            '            if line.strip() == "end" and len(line) - len(line.lstrip()) == skip_indent:\n                skip_indent = None',
            '            if line.strip() == "end" and len(line) - len(line.lstrip()) == skip_indent:\n                pass',
            "a nested class's initializer declared first is not the component's",
        ),
        Mutation(
            'any line starting `class` or `module` opens a nested body, `class:` included',
            'NESTED = re.compile(r"^([ \\t]*)(?:class[ \\t]+(?:[A-Z]|<<)|module[ \\t]+[A-Z])(?!.*\\bend\\s*$)")',
            'NESTED = re.compile(r"^([ \\t]*)(?:class|module)\\b(?!.*\\bend\\s*$)")',
            'a `class:` keyword line is not a nested class',
        ),
        Mutation(
            'the class regex spans blank lines above the class again',
            'CLASS = re.compile(r"^(?P<indent>[ \\t]*)class (?P<name>\\w+) < ViewComponent::Base[ \\t]*$", re.M)',
            'CLASS = re.compile(r"^(?P<indent>\\s*)class (?P<name>\\w+) < ViewComponent::Base[ \\t]*$", re.M)',
            'a `class:` keyword line is not a nested class',
        ),
    ),
)
