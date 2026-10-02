"""Mutation guard: the lane-band mod. Declared here, run by scripts/mutation_check.py (#866, #1109)."""
from mutation_types import Guard, Mutation  # noqa: F401

# rails-flow #1537. The gate (scripts/check_lane_band.py) is the only thing in CI that exercises the
# mod, because `claude plugin test` needs the `claude` binary. Each break below is one way the band
# stops being what its CHANGELOG entry says: read-only, non-blocking, and correct about what it shows.
GUARD = Guard(
    name="check_lane_band",
    subject="hooks/lane-band.js",
    selftest="scripts/check_lane_band.py",
    # Read, not imported: the checker parses the hooks file and runs the host test against the subject.
    needs=(
        "hooks/hooks.json",
        "tests/lane-band.host.test.mjs",
    ),
    mutations=(
        Mutation(
            "git status loses --no-optional-locks, so a read-only band can rewrite .git/index",
            "['--no-optional-locks', 'status', '--porcelain']",
            "['status', '--porcelain']",
            "takes no optional locks",
        ),
        Mutation(
            "session.start awaits the git calls again, so the first prompt waits on them",
            "on('session.start', async ($, e, next) => {\n    $.clock.after(0, () => refresh($))",
            "on('session.start', async ($, e, next) => {\n    await refresh($)",
            "session.start runs no git before its timer",
        ),
        Mutation(
            "turn.complete awaits the git calls again, so every turn end waits on them",
            "on('turn.complete', async ($, e, next) => {\n    $.clock.after(0, () => refresh($))",
            "on('turn.complete', async ($, e, next) => {\n    await refresh($)",
            "turn.complete runs no git before its timer",
        ),
        Mutation(
            "a write verb joins the refresh, so the band is no longer read-only",
            "const top = await git($, ['rev-parse', '--show-toplevel'])",
            "await git($, ['add', '-A'])\n  const top = await git($, ['rev-parse', '--show-toplevel'])",
            "read-only git calls",
        ),
        Mutation(
            "the newest-refresh guard is removed, so a slow older refresh overwrites a newer one",
            "  if (mine !== latest) return\n",
            "",
            "late, older refresh",
        ),
        Mutation(
            "the lane segment is dropped from the band line",
            "if (info.lane) parts.push('lane ' + info.lane)",
            "// lane dropped",
            "band shows branch, worktree, lane and dirty count",
        ),
        Mutation(
            "the band stops keeping what the mods after it draw",
            "...(theirs ? [theirs] : [])",
            "",
            "keeps what the mods after it draw",
        ),
        Mutation(
            "the render hook loses its AbovePrompt matcher and draws at every site",
            "{ component: 'AbovePrompt' }",
            "{}",
            "limited to AbovePrompt",
        ),
    ),
)
