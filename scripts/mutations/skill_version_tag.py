"""Mutation guard: skill_version_tag. Run by scripts/mutation_check.py.

The breaks that matter search the WRONG skill tree for a downstream report: the wrong tag makes a
rule the agent never had look present (a false lapse, #1386 review).
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="skill_version_tag",
    subject="scripts/skill_version_tag.py",
    selftest="scripts/skill_version_tag.py",
    mutations=(
        Mutation(
            "tags sort lexically, so v1.10.0 is read before v1.9.0",
            '    tags = _git(repo, "tag", "--list", "v*", "--sort=v:refname")',
            '    tags = _git(repo, "tag", "--list", "v*")',
            "version sort, not lexical",
        ),
        Mutation(
            "the plugin name is ignored, so another plugin at that version matches",
            '        isinstance(p, dict) and p.get("name") == plugin and p.get("version") == version',
            '        isinstance(p, dict) and p.get("version") == version',
            "carries: other plugin",
        ),
        Mutation(
            "the last carrying tag is returned instead of the first",
            "        if shown.returncode == 0 and carries(shown.stdout, plugin, version):\n            return tag",
            "        if shown.returncode == 0 and carries(shown.stdout, plugin, version):\n            found = tag",
            "first tag carrying a version",
        ),
        # #1411 review: the triager reads stdout; a tag printed anywhere else reads as "no release".
        Mutation(
            "the tag is printed to stderr, so the triager's $(...) captures nothing",
            "    print(tag)\n    return 0",
            "    print(tag, file=sys.stderr)\n    return 0",
            "main(): the tag is printed on stdout",
        ),
        Mutation(
            "a version matches by prefix",
            'p.get("version") == version\n',
            'str(p.get("version", "")).startswith(version)\n',
            "a near-miss version is not a match",
        ),
    ),
)
