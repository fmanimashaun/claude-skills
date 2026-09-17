"""Mutation guard: rebuild_generated. Declared here, run by scripts/mutation_check.py (#866).

`rebuild_generated.py` shipped with no selftest and no gate, and its list of builders fell behind
twice before anyone noticed: `build_maintainer_skills.py` (#1004) and `derive_mandated_gems.py`
were both gated by the doctor and absent from BUILDERS, so the one command that exists so nobody
rebuilds from memory rebuilt four of six. The first mutation below is that exact regression.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="rebuild_generated",
    subject="scripts/rebuild_generated.py",
    selftest="scripts/rebuild_generated.py",
    # The selftest READS the doctor's gate table, asserts every registered script exists, and
    # asserts every declared output exists. All three are real reads, so all three are staged —
    # without them the baseline fails and every mutation passes for free.
    needs=(
        "scripts/maintainer_doctor.py",
        "scripts/build_coverage.py",
        "scripts/build_coverage_artifact.py",
        "scripts/build_wiki.py",
        "scripts/doctrine_map.py",
        "scripts/package_core.py",
        "scripts/build_maintainer_skills.py",
        "scripts/derive_mandated_gems.py",
        "scripts/extract_release_notes.py",
        "docs/evidence/coverage.html",
        "docs/wiki/",
        "docs/architecture/doctrine-map.html",
        "dist/",
        ".claude/skills/",
        "plugins/rails-flow/mandated_gems.json",
    ),
    mutations=(
        Mutation(
            "a gated generator is dropped from BUILDERS — the #1004 regression, exactly",
            '    ("maintainer skill mirrors", "build_maintainer_skills.py", (".claude/skills/",)),\n',
            "",
            "neither BUILDERS nor NOT_REBUILT",
        ),
        Mutation(
            "the doctor's gate table stops being read, so every gate looks classified",
            'return set(re.findall(r\'"python3",\\s*"scripts/([A-Za-z0-9_]+\\.py)",\\s*"--check"\', text))',
            "return set()",
            "read no --check gates",
        ),
        Mutation(
            "a builder's declared output path goes stale, so the `git add` line lies",
            '("wiki reference", "build_wiki.py", ("docs/wiki/",)),',
            '("wiki reference", "build_wiki.py", ("docs/wiki-renamed/",)),',
            "declared output docs/wiki-renamed/ does not exist",
        ),
    ),
)
