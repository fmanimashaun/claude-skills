"""Mutation guard: check_spec. Declared here, run by scripts/mutation_check.py (#1375).

Each mutation lets a spec through that cannot be built from, or that cites what it never read.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_spec",
    subject="scripts/check_spec.py",
    selftest="scripts/check_spec.py",   # --selftest lives in the module itself
    needs=("scripts/check_brief.py",),
    mutations=(
        Mutation(
            "a missing section is not reported",
            '    findings = [f"missing section `## {label}`" for label, sec in found.items() if sec is None]',
            "    findings = []",
            "a missing section is refused",
        ),
        Mutation(
            "citations are not resolved",
            "    cb.check_sources(sections, root, findings)\n",
            "",
            "a citation whose locator is not in the file is refused",
        ),
        Mutation(
            "a Sources section may cite nothing",
            "    if sources is not None and not any(cb.SOURCE_REF_RE.search(line) for _, line in prose(sources)):",
            "    if False:",
            "a Sources section citing nothing is refused",
        ),
        Mutation(
            "D-nnn ids are not checked",
            "    cb.check_decisions(sections, decisions, findings)\n",
            "",
            "an undefined D-nnn is refused",
        ),
        Mutation(
            "any bullet counts as a user story",
            "            if not STORY.match(text.strip()):",
            "            if False:",
            "a story not in As/I want/so that form is refused",
        ),
        Mutation(
            "file paths in Implementation decisions pass",
            "            for m in PATH.finditer(",
            "            for m in [] or PATH.finditer('' if True else ",
            "a file path in Implementation decisions is refused",
        ),
        # Its control: fenced prototype code is a decision, not a path list.
        Mutation(
            "fenced code in Implementation decisions is read as prose",
            "            if not (i < len(sec.fenced) and sec.fenced[i])]",
            "            if True]",
            "CONTROL: the fenced prototype snippet in Implementation decisions is exempt",
        ),
        Mutation(
            "a spec with no agreed test seam passes",
            "    if testing is not None and not any(SEAM.match(t.strip()) for _, t in testing.bullets()):",
            "    if False:",
            "Testing decisions with no Seam: line is refused",
        ),
        Mutation(
            "\"none\" is an acceptable Out of scope",
            "        cb.check_non_goals(out, findings)\n",
            "        pass\n",
            "an Out of scope of only \"none\" is refused",
        ),
        Mutation(
            "a file that is not a spec reads as a list of misses",
            "    if not any(found.values()):",
            "    if False:",
            "a file with none of the sections is unusable, not a list of misses",
        ),
    ),
)
