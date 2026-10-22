"""Mutation guard: gh_shim_judge. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #1839. The judgement the gh shim asks of lib/pr_ready_guard.py (`--shim`), the same record and rules as the hook. Each mutation breaks one rule; the gh shim selftest notices it.
GUARD = Guard(
    name='gh_shim_judge',
    subject='hooks/scripts/lib/pr_ready_guard.py',
    selftest="scripts/gh_shim_selftest.py",
    needs=("scripts/fixture_git.py", "git-shim/gh", "hooks/scripts/guard-pr-ready.sh", "hooks/scripts/lib",
           # #2268: the same selftest runs its cases under contained(), and its "claim bodies" case runs the shim through guard-claims.sh, which reads extract_claims.py
           "scripts/process_containment.py", "hooks/scripts/guard-claims.sh", "scripts/extract_claims.py"),
    narrow_with="--match",
    mutations=(
        Mutation('--undo is no longer allowed', '        if "--undo" in after[:cut_at] and all(plain_word(w) for w in after if w not in ("--undo", "--")):', '        if False:', 'no record'),
        Mutation('--undo=false counts as --undo', '        if w == "--undo" and not cut:', '        if w.startswith("--undo") and not cut:', 'no record'),
        Mutation('an explicit repository target is not refused', '    if any(w in SHIM_FLAGS or w.startswith(("--repo=", "-R")) or "/pull/" in w for w in words):', '    if False:', 'explicit target'),
        Mutation('GH_REPO, GH_HOST or another GIT_*/GH_* variable in the environment is ignored', '    if redirect or gh_repo:', '    if False:', 'redirecting variable'),
        Mutation('an argument that is not a plain PR number or branch is allowed', '        if not plain_word(w):\n            return refuse(f"argument {w}', '        if False:\n            return refuse(f"argument {w}', 'allowlist'),
        Mutation('a repository that does not run project_gates is judged', '    if not (root and in_force(root)):\n        return 0\n    first = _next_word(argv)', '    if not root:\n        return 0\n    first = _next_word(argv)', 'not in force'),
        Mutation('the sweep record is not read', '    return judge_record(root, shown)\n\n\ndef shim_unreadable_alias', '    return 0\n\n\ndef shim_unreadable_alias', 'no record'),
        Mutation('git failing for another reason is read as outside any repository', '    if status == "error":\n        return refuse(f"git could not say whether {cwd} is a repository, so this `gh pr ready` cannot be judged."', '    if False:\n        return refuse(f"git could not say whether {cwd} is a repository, so this `gh pr ready` cannot be judged."', 'git cannot answer'),
        Mutation('git is asked WITH the variables that locate a repository, so GIT_DIR=/nonexistent hides a repository', '    clean = {k: v for k, v in os.environ.items() if not k.startswith("GIT_") or k in HARMLESS_ENV or k.startswith(("GIT_AUTHOR_", "GIT_COMMITTER_"))}', '    clean = dict(os.environ)', 'redirecting variable'),
        Mutation('a gh api that marks a PR ready is not held to the record', '            return judge_record(root, "gh api (marks a PR ready)")', '            return 0', 'gh api'),
        Mutation('a gh api body read from a file is allowed', '        if any(w == "--input" or w.startswith("--input=") or "=@" in w for w in argv):', '        if False:', 'gh api'),
        Mutation('a gh api naming a repository or host is not refused', '        if any(w in SHIM_FLAGS or w.startswith(("--repo=", "-R", "--hostname")) or w == "--hostname" for w in argv):', '        if False:', 'gh api'),
        Mutation('only a list of the dangerous variables is refused, so one nobody thought of passes', '    names = {k for k in os.environ if k.startswith(("GIT_", "GH_")) and k not in HARMLESS_ENV and not k.startswith(("GIT_AUTHOR_", "GIT_COMMITTER_", "GIT_TRACE"))}', '    names = {k for k in os.environ if k in ("GIT_DIR", "GIT_WORK_TREE", "GH_HOST") or k.startswith("GIT_CONFIG")}', 'redirecting variable'),
        Mutation("a HOME that is not the account's is not noticed", '        names.add("HOME")', '        pass', 'redirecting variable'),
        Mutation('an XDG_CONFIG_HOME that is not the default is not noticed', '        names.add("XDG_CONFIG_HOME")', '        pass', 'redirecting variable'),
        Mutation('a git that does not answer in time is allowed by the shim entry', '            sys.exit(_timed_out(exc, " ".join(sys.argv[2:])))', '            sys.exit(0)', 'a git that does not answer in time is a NAMED refusal'),
        Mutation('an alias expansion that is not plain words is not refused where in force', '    return refuse("this gh alias expands to something that is not plain words', '    return 0\n    return refuse("this gh alias expands to something that is not plain words', 'alias flags'),
    ),
)
