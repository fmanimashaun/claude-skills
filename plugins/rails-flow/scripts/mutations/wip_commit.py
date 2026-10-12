"""Mutation guard: wip_commit (#1564). Declared here, run by scripts/mutation_check.py.

Each mutation lets a repository- or environment-chosen program run under the Stop hook's git, commits somewhere it must not, takes
files it must not, or rewrites what was pushed. The named fixture in `wip_commit.py --selftest` must go red for each.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="wip_commit",
    subject="scripts/wip_commit.py",
    selftest="scripts/wip_commit.py",   # --selftest lives in the module itself
    needs=("scripts/test_preflight.py",),   # it imports the one trusted_which resolver
    mutations=(
        Mutation(
            "submodules are ignored entirely, so a moved gitlink (a submodule bump) is neither saved nor reported",
            '    names = g("diff", "--name-only", "-z", "--no-renames", "--ignore-submodules=dirty", "HEAD")',
            '    names = g("diff", "--name-only", "-z", "--no-renames", "--ignore-submodules=all", "HEAD")',
            "a moved gitlink (a submodule bump) is committed",
        ),
        Mutation(
            "the size limit is inclusive, so a file of exactly 10 MB is refused",
            '        if size > MAX_BYTES:',
            '        if size >= MAX_BYTES:',
            "CONTROL: exactly 10 MB is still committed",
        ),
        Mutation(
            "a file over the size limit is committed anyway",
            '        if size > MAX_BYTES:',
            '        if False:',
            "a changed tracked file over 10 MB skips",
        ),
        Mutation(
            "status recurses into submodules, so a submodule's own clean filter runs",
            '    status = g("status", "--porcelain", "--untracked-files=no", "--ignore-submodules=dirty")',
            '    status = g("status", "--porcelain", "--untracked-files=no")',
            "a submodule's own clean filter never runs",
        ),
        Mutation(
            "diff recurses into submodules, so a submodule's own clean filter runs",
            '    names = g("diff", "--name-only", "-z", "--no-renames", "--ignore-submodules=dirty", "HEAD")',
            '    names = g("diff", "--name-only", "-z", "--no-renames", "HEAD")',
            "a submodule's own clean filter never runs",
        ),
        Mutation(
            "a merge --squash in progress is committed over",
            'IN_PROGRESS = ("SQUASH_MSG", "MERGE_HEAD",',
            'IN_PROGRESS = ("MERGE_HEAD",',
            "SQUASH_MSG",
        ),
        Mutation(
            "a rename across the lane edge is half-committed",
            '                if bool(lane_paths([old], lane)) != bool(lane_paths([new], lane)):',
            '                if False:',
            "a rename across the lane edge is skipped",
        ),
        Mutation(
            "a secret-looking changed file no longer stops the commit, so a tracked .env or master.key is auto-committed",
            '    if secrets:\n',
            '    if False:\n',
            "a changed secret-looking",
        ),
        Mutation(
            "the lane is ignored, so another lane's tracked change goes into the WIP commit",
            '    paths = lane_paths(changed, lane)',
            '    paths = changed',
            "only the lane's subtree is committed",
        ),
        Mutation(
            "commit takes every staged file again (-a, no path list)",
            '    args = ["--literal-pathspecs", "commit", "--no-verify", "-q", "-m", message, "--", *paths]',
            '    args = ["--literal-pathspecs", "commit", "-a", "--no-verify", "-q", "-m", message]',
            "only the lane's subtree is committed",
        ),
        Mutation(
            "lane matching is a string prefix, so app/model claims app/models",
            '    return [p for p in paths if p == lane or p.startswith(lane + "/")]',
            '    return [p for p in paths if p.startswith(lane)]',
            "lane matching is by path component",
        ),
        Mutation(
            "the parent's environment reaches git, so GIT_CONFIG_* and GIT_EXTERNAL_DIFF run what the repository chose",
            '    out = {"PATH": os.path.dirname(git), "LC_ALL": "C", "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0"}',
            '    out = dict(env); out.update({"PATH": os.path.dirname(git), "LC_ALL": "C"})',
            "a clean filter defined through GIT_CONFIG_COUNT",
        ),
        Mutation(
            "git is found by the bare name, so a relative or in-repository PATH entry is used",
            '    git = trusted_which("git", parent_env, project_root(root.resolve() if root.exists() else root))',
            '    git = __import__("shutil").which("git", path=parent_env.get("PATH"))',
            "hostile: a relative `./bin` first on PATH",
        ),
        Mutation(
            "core.hooksPath is not forced off, so a repository's pre-commit hook runs",
            'HARD_CONFIG = ["-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false",',
            'HARD_CONFIG = ["-c", "core.fsmonitor=false",',
            "hostile: a repository-local hook",
        ),
        Mutation(
            "the hook is skipped for nothing: every branch is a lane, so main and dev get WIP commits",
            '    if not LANE.match(name):',
            '    if False:',
            "is not a lane: nothing committed",
        ),
        Mutation(
            "untracked files are staged too (git add -A in spirit)",
            '    args = ["--literal-pathspecs", "commit", "--no-verify", "-q", "-m", message, "--", *paths]',
            '    g("add", "-A")\n    args = ["--literal-pathspecs", "commit", "-a", "--no-verify", "-q", "-m", message]',
            "an UNTRACKED file is never committed",
        ),
        Mutation(
            "a pushed WIP commit is amended, rewriting what the remote has",
            '        pushed = contained is None or contained.returncode != 0 or bool(contained.stdout.strip())',
            '        pushed = False',
            "the pushed commit was not rewritten",
        ),
        Mutation(
            "a WIP commit is never amended, so every turn stacks another commit",
            '    if head_is_wip and not pushed:',
            '    if False:',
            "AMENDS the unpushed WIP commit",
        ),
        Mutation(
            "a merge in progress is committed over",
            '    if any((gitdir / marker).exists() for marker in IN_PROGRESS):',
            '    if False:',
            "a merge in progress is never committed over",
        ),
        Mutation(
            "a repository with no identity gets one invented (through the environment, which the scrub otherwise drops)",
            '    out = {"PATH": os.path.dirname(git), "LC_ALL": "C", "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0"}',
            '    out = {"PATH": os.path.dirname(git), "LC_ALL": "C", "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0",\n           "GIT_AUTHOR_NAME": "wip", "GIT_AUTHOR_EMAIL": "wip@wip", "GIT_COMMITTER_NAME": "wip", "GIT_COMMITTER_EMAIL": "wip@wip"}',  # fixture-git: exempt (a mutation's replacement text: it is patched into wip_commit.py, never run as a fixture git)
            "invents none",
        ),
        Mutation(
            "the commit message carries a closing keyword",
            '    message = f"{MARK}{name} {stamp}"',
            '    message = f"{MARK}{name} {stamp} Fixes #1"',
            "no closing keyword",
        ),
        Mutation(
            "a repository whose own config names a program is committed to anyway",
            "    if risky:",
            "    if False:",
            "repo-local config: a clean filter: nothing is committed",
        ),
        Mutation(
            "the user's own global config is read as the repository's, so a credential helper of theirs skips every lane",
            '        if scope not in ("local", "worktree"):',
            "        if False:",
            "a dirty tracked change on a feature lane is committed",
        ),
        Mutation(
            "filter drivers are not on the list of keys that run a program",
            r'    r"^(?:filter\..+\.(?:clean|smudge|process)|diff\..+\.(?:textconv|command)|',
            r'    r"^(?:NEVER\..+\.(?:clean|smudge|process)|diff\..+\.(?:textconv|command)|',
            "repo-local config: a clean filter: nothing is committed",
        ),
        Mutation(
            "a repository that contains HOME is committed to, so its .gitconfig runs as the user's global config",
            "            if contains(top, home):",
            "            if False:",
            "HOME in the repository: a clean filter in the repository's .gitconfig: nothing is committed",
        ),
        Mutation(
            "containment is a string prefix test again, so a symlink or a case-insensitive spelling of HOME escapes it",
            "            if os.path.samefile(here, str(root)):",
            "            if here == str(root):",
            "contains() compares by file identity",
        ),
        Mutation(
            "a nested repository is judged only against itself, not the project around it",
            "        for top in (toplevel, outermost_root(toplevel)):",
            "        for top in (toplevel,):",
            "a nested repository is refused when HOME is inside the PROJECT",
        ),
        Mutation(
            "diff.external is not on the list of keys that run a program",
            "diff\\.external|difftool",
            "NEVER\\.external|difftool",
            "repo-local config: diff.external: nothing is committed",
        ),
        Mutation(
            "the trusted-git resolver is given the hook's working directory, not the project root, so a fake git in repo/bin is trusted from repo/app",
            '    git = trusted_which("git", parent_env, project_root(root.resolve() if root.exists() else root))',
            '    git = trusted_which("git", parent_env, root)',
            "a fake git at an ABSOLUTE PATH entry inside the project",
        ),
    ),
)
