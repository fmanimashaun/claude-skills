# doctrine-verifier verdicts for #2058 (a worktree teardown that drops its databases), 2026-10-14

One read-only verifier run (the `doctrine-verifier` protocol, `WebFetch` of the pages below on 2026-10-14). The edits in
`skills/parallel-session-lane/SKILL.md` and `references/one-issue-at-a-time.md` state only what a CONFIRMED row supports; the
design of the teardown itself (which processes, which databases, what it refuses) is ours, decided by the owner rule recorded on
#2058 ("a worktree teardown must drop its databases and stop its processes; we should never have a leftover database",
relayed by claude-skills-72, 2026-10-14), not an external claim.

| id | claim | verdict | authority | what the doctrine does |
|---|---|---|---|---|
| P1 | `dropdb --if-exists`: "Do not throw an error if the database does not exist. A notice is issued in this case." | CONFIRMED (present in 18; the first major version is not shown on the page: INCONCLUSIVE for that point) | https://www.postgresql.org/docs/18/app-dropdb.html | the teardown uses it; the skill names it without a "since" claim |
| P2 | `dropdb -f` / `--force`: "Attempt to terminate all existing connections to the target database before dropping it." Caveats on DROP DATABASE: it does not terminate when prepared transactions, active logical replication slots or subscriptions exist; it terminates background workers and connections the current user may terminate with `pg_terminate_backend`; "If connections would remain, this command will fail." | CONFIRMED; first in PostgreSQL 13 (13.0 release notes: "Allow dropdb to disconnect sessions using the target database ... This is enabled with the `-f` option."). The 13 notes name `-f` only; the long form `--force` is listed on the 18 page | https://www.postgresql.org/docs/18/app-dropdb.html, https://www.postgresql.org/docs/18/sql-dropdatabase.html, https://www.postgresql.org/docs/release/13.0/ | the skill says "PostgreSQL 13 or later" and that the drop can still fail while a prepared transaction or an active logical replication slot holds the database; the script reports a failed `dropdb` and does not remove the worktree |
| P3 | `DROP DATABASE ... WITH (FORCE)` is the SQL equivalent | CONFIRMED; PostgreSQL 13 (13.0 release notes E.24.3.3) | https://www.postgresql.org/docs/18/sql-dropdatabase.html | not used by the script; recorded as the same boundary |
| G1 | `git worktree remove` refuses an unclean worktree unless `--force`: "Only clean worktrees (no untracked files and no modification in tracked files) can be removed. Unclean worktrees or ones with submodules can be removed with `--force`. The main worktree cannot be removed." | CONFIRMED | https://git-scm.com/docs/git-worktree | the script refuses a dirty tree itself, before it stops or drops anything, and never passes `--force` |
| G2 | a locked worktree needs `--force` twice | CONFIRMED: "To remove a locked worktree, specify `--force` twice." | https://git-scm.com/docs/git-worktree | the script refuses a locked worktree and says to unlock it deliberately |
| G3 | `git worktree list --porcelain` prints `locked` (with an optional reason) and lists the main worktree first | CONFIRMED | https://git-scm.com/docs/git-worktree | the script reads the porcelain list, refuses the first entry and a `locked` one |

Caveats the verifier asked us to record, and where they went: the privilege `--force` needs is not named on the page (the script's docstring says
"the running role may terminate with `pg_terminate_backend`", not "superuser", which is an inference); how
`--if-exists` and `--force` interact is not documented, so the script relies on neither interacting; a lock reason may be quoted in
the porcelain output, and the script treats `locked` as a bare label or a label with a value.
