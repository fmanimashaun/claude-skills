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
            "    return found[0] if found else None",
            "    return found[-1] if found else None",
            "first tag carrying a version",
        ),
        # #1411 review: the triager reads stdout; a tag printed anywhere else reads as "no release".
        Mutation(
            "the tag is printed to stderr, so the triager's $(...) captures nothing",
            "    print(tags[0])\n    return 0",
            "    print(tags[0], file=sys.stderr)\n    return 0",
            "main(): the tag is printed on stdout",
        ),
        Mutation(
            "a version matches by prefix",
            'p.get("version") == version\n',
            'str(p.get("version", "")).startswith(version)\n',
            "a near-miss version is not a match",
        ),
        # #1427: one version, two skills trees. Without the warning the triager searches one tree
        # and reads a rule the reporter's tag may not have had as present or absent.
        Mutation(
            "a version shipped with differing skills trees is reported silently",
            "    if len(tags) < 2:\n        return []",
            "    if True:\n        return []",
            "a later tag with a different skills tree is named on stderr",
        ),
        # #1474 review: every later tag of a tree is named, so 1.42.2 lists three tags for one tree.
        Mutation(
            "a later tag sharing an already-named tree is named again",
            "            seen.add(tid)\n",
            "            pass\n",
            "one tag per distinct tree",
        ),
        # A missing tree echoed by rev-parse compares as different: every multi-tag version warns.
        Mutation(
            "rev-parse without --verify echoes an unresolvable tree, so absent trees differ",
            '        return got.stdout.strip() if got.returncode == 0 else ""',
            "        return got.stdout.strip() or tag",
            "tags that agree on the skills tree warn about nothing",
        ),
        # #1427 item 6: an unreadable repo must not read as "no release carries it".
        Mutation(
            "cannot-read-the-repo exits 1, which the triager reads as a real no-release",
            '        print(f"skill_version_tag: {exc}", file=sys.stderr)\n        return 2',
            '        print(f"skill_version_tag: {exc}", file=sys.stderr)\n        return 1',
            "outside a repository exits 2, not 1",
        ),
    ),
)
