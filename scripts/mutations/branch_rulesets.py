"""Mutation guard: branch_rulesets. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #895. A promotion squash-merged from the UI broke dev's ancestry with the content identical, so the
# check that guards the ruleset must itself be guarded: each mutation makes one hole in the ruleset
# read as covered, or makes a not-applicable state read as a pass.
GUARD = Guard(
    name="branch_rulesets",
    subject="plugins/rails-flow/scripts/branch_rulesets.py",
    selftest="plugins/rails-flow/scripts/branch_rulesets.py",   # --selftest lives in the module itself
    mutations=(
        Mutation(
            "a pull_request rule that still allows squash counts as merge-only",
            '                if methods is not None and sorted(methods) == sorted(ALLOWED_METHODS):',
            '                if methods is not None:',
            "still allows squash is not ok",
        ),
        Mutation(
            "a disabled ruleset counts as enforcement",
            '    if ruleset.get("target") != "branch" or ruleset.get("enforcement") != "active":',
            '    if ruleset.get("target") != "branch":',
            "a disabled ruleset does not count",
        ),
        Mutation(
            "a ruleset on any branch covers every branch",
            '    return hit(includes) and not hit(excludes)',
            '    return True',
            "a ruleset on another branch does not count",
        ),
        Mutation(
            "an excluded branch still counts as covered",
            '    return hit(includes) and not hit(excludes)',
            '    return hit(includes)',
            "an exclude beats an include",
        ),
        Mutation(
            "a missing deletion rule goes unreported, so the release branch can be deleted",
            '        if not present["deletion"]:\n            missing.append("deletion rule (the branch can be deleted)")',
            '        if False:\n            missing.append("deletion rule (the branch can be deleted)")',
            "a missing deletion rule is named",
        ),
        Mutation(
            "gh unauthenticated reads as a pass instead of n/a",
            '        code, out = gh(["auth", "status"])\n        if code != 0:\n            print("n/a: `gh` is not authenticated — `gh auth login`")\n            return 3',
            '        code, out = gh(["auth", "status"])\n        if False:\n            return 3',
            "gh unauthenticated is n/a",
        ),
        Mutation(
            "a non-GitHub origin reads as a pass instead of n/a",
            '        if slug is None:\n            print("n/a: `origin` is not a github.com remote (or there is none) — rulesets live on GitHub")\n            return 3',
            '        if False:\n            return 3',
            "a non-GitHub origin is n/a",
        ),
        Mutation(
            "--apply posts over a ruleset someone else owns instead of reporting it",
            '        if v["covering"]:\n            print(f"a ruleset already covers {branch} ({\', \'.join(v[\'covering\'])}) but lacks: " + "; ".join(v["missing"]))',
            '        if False:\n            print("")',
            "never edits someone else's ruleset",
        ),
        Mutation(
            "the ruleset --apply creates allows squash, so the tool installs the hole it exists to close",
            'ALLOWED_METHODS = ["merge"]',
            'ALLOWED_METHODS = ["merge", "squash"]',
            "posts exactly one ruleset with the three rules",
        ),
    ),
)
