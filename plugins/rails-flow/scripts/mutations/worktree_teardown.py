"""Mutation guard: worktree_teardown. Declared here, run by scripts/mutation_check.py (#866, #2058).

The teardown's whole value is what it REFUSES and what it leaves alone: a dirty tree, an unmerged head, a locked worktree
and the main checkout are never touched; only its own databases (exactly its names and `_p<digits>` shards) are dropped,
never one the main checkout shares; only a process whose working directory is inside the worktree is stopped; `dropdb` is
always `--if-exists --force`; `git worktree remove` is never forced; an unreachable PostgreSQL removes nothing. Each break
below loosens one of those, and the fixture whose label is in `expects` must notice it.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="worktree_teardown",
    subject="scripts/worktree_teardown.py",
    selftest="scripts/worktree_teardown.py",
    selftest_args=("--selftest",),
    needs=("scripts/fixture_git.py",),
    mutations=(
        Mutation("a dirty worktree is no longer refused", "if rc != 0 or status.strip():", "if rc != 0:",
                 "a refused worktree keeps its databases"),
        Mutation("an unmerged head is no longer refused",
                 'if integ is None or git(path, "merge-base", "--is-ancestor", row["head"], integ)[0] != 0:', "if False:",
                 "an unmerged head is refused"),
        Mutation("a locked worktree is no longer refused", 'if row["locked"]:', "if False:", "a locked worktree is refused"),
        Mutation("the main checkout is no longer refused", "if row is rows[0]:", "if False:", "the main checkout is refused"),
        Mutation("a shard matches by prefix, not exactly", "re.fullmatch(re.escape(n) + SHARD, d)", "d.startswith(n)",
                 "exactly its own databases"),
        Mutation("a database shared with the main checkout is dropped", "keep = [n for n in names if n not in shared]",
                 "keep = list(names)", "never dropped"),
        Mutation("dropdb loses --force", 'DROP_FLAGS = ("--if-exists", "--force")', 'DROP_FLAGS = ("--if-exists",)',
                 "every drop is"),
        Mutation("a process outside the worktree is signalled",
                 "if where is not None and (where == path or where.startswith(path + os.sep)) and pid not in found:",
                 "if pid not in found:", "never signals a process outside the worktree"),
        Mutation("its own server is no longer stopped", "        stop(pid)", "        pass", "it stops its own server"),
        Mutation("git worktree remove is forced", 'GIT_REMOVE = ("worktree", "remove")',
                 'GIT_REMOVE = ("worktree", "remove", "--force")', "never forced"),
        Mutation("an unreachable PostgreSQL no longer fails closed", "listed = existing_databases(psql) if psql and dropdb else None",
                 "listed = existing_databases(psql) if psql and dropdb else []", "fails closed"),
        Mutation("--dry-run acts", "    if dry_run:", "    if False:", "--dry-run changes nothing"),
        Mutation("--assume-merged is ignored", "    if not assume_merged:", "    if True:", "--assume-merged ends a branch"),
        Mutation("a path that is not a worktree of this repository is no longer refused", "    if row is None:", "    if False:",
                 "a subdirectory of a worktree is refused"),
        Mutation("an unreadable database config no longer fails closed", "    if config is None or any(c is None for c in shared_cfgs.values()):", "    if False:",
                 "an unreadable database config fails closed"),
        Mutation("production database names are no longer shared", 'shared = set(config["production"])', "shared = set()",
                 "a production database name is never dropped"),
        Mutation("another registered worktree's names are no longer shared", 'shared |= set(c["own"]) | set(c["production"])', "shared |= set()",
                 "another registered worktree"),
        Mutation("a process with no pid file is no longer noticed", "    if strays:", "    if False:", "a process with no pid file is noticed"),
        Mutation("every process on the machine counts as inside the worktree", 'if where == path or where.startswith(path + os.sep): found[pid] = ""',
                 'if True: found[pid] = ""', "a clean merged worktree ends with status 0"),
        Mutation("the script's own process and children count as strays", "known = set(pids) | own_tree()", "known = set(pids)",
                 "run with its working directory inside the worktree"),
        Mutation("a stage of its own pipeline counts as a stray", "return tree | below | same_group", "return tree | below",
                 "piped into cat"),
        Mutation("the wording check stops requiring the teardown's name", "elif token not in \" \".join(lines[at:at + span]):", "elif False:",
                 "the wording check names"),
        Mutation("the wording check stops noticing a missing file", "if not f.exists():", "if False:", ""),
    ),
)
