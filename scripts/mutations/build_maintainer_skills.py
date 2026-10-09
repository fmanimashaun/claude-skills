"""Mutation guard: build_maintainer_skills. Declared here, run by scripts/mutation_check.py (#866).

#1004 shipped the generator and its `--selftest` with no guard, so nothing yet proved that selftest
can fail. Two arms were paid for by a live defect: the stray arm after a hand-copied
`skills/code-review/SKILL.md` passed a full green sweep (#1006), and the unstaged arm after `--check`
was found reading the working tree while every sibling gate read HEAD (#1008).
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="build_maintainer_skills",
    subject="scripts/build_maintainer_skills.py",
    selftest="scripts/build_maintainer_skills.py",
    # The selftest READS the source and the derived copy, and globs `skills/*/SKILL.md` for a
    # shipped skill with no derived directory. `code-review` is that skill; without it staged, the
    # stray arm has nothing to copy and the baseline is inert rather than passing.
    needs=("plugins/rails-flow/scripts/fixture_git.py", 
        "skills/parallel-session-lane/SKILL.md",
        "skills/code-review/SKILL.md",
        ".claude/skills/parallel-session-lane/SKILL.md",
        # #1481: the references are mirrored too, so the builder reads both sides of them.
        "skills/parallel-session-lane/references",
        ".claude/skills/parallel-session-lane/references",
    ),
    mutations=(
        Mutation(
            "an unregistered copy of a shipped skill is accepted, so one rule gets two homes",
            '            if relative not in registered:\n                strays.append(relative)',
            '            pass',
            "unregistered copy",
        ),
        Mutation(
            "the derived copy is never compared, so an edited mirror passes --check",
            "            if committed_blob(derived.as_posix()) != want:",
            "            if False:",
            "committed copy that had been edited",
        ),
        Mutation(
            # #1008 restored. The three mutations above all mutate COMMITTED content, so every one
            # of them is caught under either reading of the tree -- none can tell the fix from the
            # bug. This is the only arm that can.
            "--check reads the working tree again, so a rebuilt-but-unstaged mirror passes locally "
            "and fails in CI",
            "            if committed_blob(derived.as_posix()) != want:",
            '            if (target.read_text(encoding="utf-8") if target.exists() else None) != want:',
            "never staged",
        ),
        Mutation(
            # `git show :path` is the index. It would make `git add` alone clear the gate -- the
            # same fail-open one step along, and invisible to every arm that stubs the read.
            "the HEAD read becomes an INDEX read, so staging without committing looks clean",
            '        result = subprocess.run(["git", "show", f"HEAD:{relative}"], cwd=cwd,',
            '        result = subprocess.run(["git", "show", f":{relative}"], cwd=cwd,',
            "not the blob at HEAD",
        ),
        Mutation(
            "the banner moves above the frontmatter, and the derived file stops being a skill",
            '    return text[:end] + "\\n" + BANNER.format(source=source.as_posix()) + text[end:]',
            "    return BANNER.format(source=source.as_posix()) + text",
            "does not open with the frontmatter block",
        ),
        Mutation(
            # #1481
            'a reference the mirrored SKILL.md links is no longer mirrored',
            '    Path("skills/parallel-session-lane/references/session-identity.md"):\n        Path(".claude/skills/parallel-session-lane/references/session-identity.md"),\n',
            '',
            'which no MIRRORED entry copies',
        ),
        Mutation(
            # #1481
            'a mirrored reference loses its banner',
            '        return BANNER.format(source=source.as_posix()) + "\\n" + text',
            '        return text',
            'a mirrored reference must open with the banner',
        ),
        Mutation(
            # #1536 review
            'stray detection reads only SKILL.md again, so a hand-copied reference passes',
            '        for derived in sorted(f for f in skill_dir.rglob("*") if f.is_file()):',
            '        for derived in sorted(f for f in skill_dir.glob("SKILL.md") if f.is_file()):',
            'unregistered reference beside a mirror',
        ),
        Mutation(
            # #1536 review
            '--check skips the mirrored references, so an edited reference ships unnoticed',
            '    for source, derived in MIRRORED.items():\n        want = render(source)',
            '    for source, derived in ((s, d) for s, d in MIRRORED.items() if s.name == "SKILL.md"):\n        want = render(source)',
            'edited committed',
        ),
    ),
)
