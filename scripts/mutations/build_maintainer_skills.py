"""Mutation guard: build_maintainer_skills. Declared here, run by scripts/mutation_check.py (#866).

#1004 shipped the generator and its `--selftest` with no guard, so nothing yet proved that selftest
can fail. The third mutation below is the one that mattered: the stray arm was added after a
hand-copied `skills/code-review/SKILL.md` passed a full green sweep.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="build_maintainer_skills",
    subject="scripts/build_maintainer_skills.py",
    selftest="scripts/build_maintainer_skills.py",
    # The selftest READS the source and the derived copy, and globs `skills/*/SKILL.md` for a
    # shipped skill with no derived directory. `code-review` is that skill; without it staged, the
    # stray arm has nothing to copy and the baseline is inert rather than passing.
    needs=(
        "skills/parallel-session-lane/SKILL.md",
        "skills/code-review/SKILL.md",
        ".claude/skills/parallel-session-lane/SKILL.md",
    ),
    mutations=(
        Mutation(
            "an unregistered copy of a shipped skill is accepted, so one rule gets two homes",
            '        if (ROOT / "skills" / derived.parent.name / "SKILL.md").exists():',
            "        if False:",
            "unregistered copy",
        ),
        Mutation(
            "the derived copy is never compared, so an edited mirror passes --check",
            "        if check:\n            if have != want:\n                drifted.append(derived.as_posix())",
            "        if check:\n            if False:\n                drifted.append(derived.as_posix())",
            "had been edited",
        ),
        Mutation(
            "the banner moves above the frontmatter, and the derived file stops being a skill",
            '    return text[:end] + "\\n" + BANNER.format(source=source.as_posix()) + text[end:]',
            "    return BANNER.format(source=source.as_posix()) + text",
            "does not open with the frontmatter block",
        ),
    ),
)
