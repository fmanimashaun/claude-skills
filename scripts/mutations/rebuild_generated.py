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
        "scripts/hermetic_git.py",                # imported by the doctor (#1510)
        "scripts/proc_group.py",                  # imported by the doctor (#1459)
        "scripts/build_coverage.py",
        "scripts/build_coverage_artifact.py",
        "scripts/build_wiki.py",
        "scripts/doctrine_map.py",
        "scripts/package_core.py",
        "scripts/build_maintainer_skills.py",
        "scripts/derive_mandated_gems.py",
        "scripts/derive_tenancy_cop.py",          # registered in BUILDERS by #1403
        "scripts/extract_release_notes.py",
        "scripts/rails_assumptions.py",           # registered in BUILDERS by #2164
        "scripts/component_classes.py",           # registered in BUILDERS by #2192
        "scripts/build_component_axes.py",        # registered in BUILDERS by #2272
        "scripts/check_component_shapes.py",      # imported by build_component_axes.py
        "plugins/rails-stack/skills/design-system/references/components.md",          # build_component_axes.py's declared outputs
        "plugins/rails-stack/skills/design-system/references/components-commerce.md",
        "scripts/prove_neutral.py",              # excluded from rebuilding by #2205
        "scripts/changelog_fragments.py",         # registered as not-a-generator by #1825; the selftest asserts it exists (#1893)
        "docs/evidence/coverage.html",
        "docs/wiki/",
        "docs/architecture/doctrine-map.html",
        "docs/architecture/rails-assumptions.md",
        "docs/architecture/rails-assumptions.json",
        "docs/architecture/rails-assumptions.policy.json",   # read by both generators
        "docs/architecture/component-classes.html",
        "docs/architecture/component-classes.json",
        "dist/",
        ".claude/skills/",
        "plugins/rails-flow/mandated_gems.json",
        "plugins/rails-stack/scaffold/",          # derive_tenancy_cop.py's declared output
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
