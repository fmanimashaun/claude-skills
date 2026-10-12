"""Mutation guard: gh_shim_judge. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #1839. The judgement the gh shim asks of lib/pr_ready_guard.py (`--shim`), the same record and rules as the hook. Each mutation breaks one rule; the gh shim selftest notices it.
GUARD = Guard(
    name='gh_shim_judge',
    subject='hooks/scripts/lib/pr_ready_guard.py',
    selftest="scripts/gh_shim_selftest.py",
    needs=("scripts/fixture_git.py", "git-shim/gh", "hooks/scripts/guard-pr-ready.sh", "hooks/scripts/lib"),
    narrow_with="--match",
    mutations=(
        Mutation('--undo is no longer allowed', '    if undo:\n        return 0', '    if False:\n        return 0', 'no record'),
        Mutation('--undo=false counts as --undo', '        if w == "--undo" and not cut:', '        if w.startswith("--undo") and not cut:', 'no record'),
        Mutation('an explicit repository target is not refused', '    if any(w in SHIM_FLAGS or w.startswith(("--repo=", "-R")) or "/pull/" in w for w in words):', '    if False:', 'explicit target'),
        Mutation('GH_REPO, GH_HOST or a GIT_* locator in the environment is ignored', '    if redirect or gh_repo:', '    if False:', 'redirecting variable'),
        Mutation('an argument that is not a plain PR number or branch is allowed', '        if not plain_word(w):\n            return refuse(f"argument {w}', '        if False:\n            return refuse(f"argument {w}', 'allowlist'),
        Mutation('a repository that does not run project_gates is judged', '    if not (root and in_force(root)):', '    if not root:', 'not in force'),
        Mutation('the sweep record is not read', '    return judge_record(root, shown)', '    return 0', 'no record'),
        Mutation('git failing for another reason is read as outside any repository', '    if status == "error":', '    if False:', 'git cannot answer'),
        Mutation('git is asked WITH the variables that locate a repository, so GIT_DIR=/nonexistent hides a repository', '    clean = {k: v for k, v in os.environ.items() if k not in GIT_LOCATORS and not k.startswith("GIT_CONFIG")}', '    clean = dict(os.environ)', 'redirecting variable'),
        Mutation('a gh api that marks a PR ready is not held to the record', '            return judge_record(root, "gh api (marks a PR ready)")', '            return 0', 'gh api'),
        Mutation('a gh api body read from a file is allowed', '        if any(w == "--input" or w.startswith("--input=") or "=@" in w for w in argv):', '        if False:', 'gh api'),
    ),
)
