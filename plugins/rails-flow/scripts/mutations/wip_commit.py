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
            "the parent's environment reaches git, so GIT_CONFIG_* and GIT_EXTERNAL_DIFF run what the repository chose",
            '    out = {"PATH": os.path.dirname(git), "LC_ALL": "C", "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0"}',
            '    out = dict(env); out.update({"PATH": os.path.dirname(git), "LC_ALL": "C"})',
            "a clean filter defined through GIT_CONFIG_COUNT",
        ),
        Mutation(
            "git is found by the bare name, so a relative or in-repository PATH entry is used",
            '    git = trusted_which("git", parent_env, root)',
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
            '    args = ["commit", "-a", "--no-verify", "-q", "-m", message]',
            '    g("add", "-A")\n    args = ["commit", "-a", "--no-verify", "-q", "-m", message]',
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
    ),
)
