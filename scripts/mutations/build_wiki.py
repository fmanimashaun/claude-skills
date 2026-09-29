"""Mutation guard: build_wiki. Declared here, run by scripts/mutation_check.py (#866).

#1404. `Agents-And-Gates.md` stamped a gate total and a per-plugin gate column, so any two open PRs
that each added a gate made each other's committed page stale with no textual conflict. Both counts
were dropped; these mutations put each back and prove the selftest refuses it.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="build_wiki",
    subject="scripts/build_wiki.py",
    selftest="scripts/build_wiki.py",
    deps=("scripts/inventory_data.py", "scripts/maintainer_doctor.py"),
    # The selftest builds every page from the live tree (inventory_data.collect_data reads the
    # plugins, the manifests, the maintainer agents and commands, and the doctor's gate table), so
    # the tree it reads is staged whole.
    needs=(
        ".claude-plugin/",
        ".claude/",
        "plugins/",
        "scripts/",
        "skills/",
        "evals/",
        "docs/wiki/",
        "CHANGELOG.md",
        "CLAUDE.md",
    ),
    mutations=(
        Mutation(
            "the gate total comes back on the totals line",
            "{t['commands']} shipped commands · {t['tierTables']} tier tables**",
            "{t['commands']} shipped commands · {t['gates']} gates · {t['tierTables']} tier tables**",
            "no gate count is stamped",
        ),
        Mutation(
            "the per-plugin gates column comes back",
            "{p['tierRows'] or '—'} |\\n\")",
            "{p['tierRows'] or '—'} | {p['gates'] or '—'} | gates |\\n\")",
            "no gate count is stamped",
        ),
    ),
)
