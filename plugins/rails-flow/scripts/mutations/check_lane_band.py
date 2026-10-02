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
            "on('session.start', async ($, e, next) => {\n    $.clock.every(2000, () => tick($))",
            "on('session.start', async ($, e, next) => {\n    await refresh($)",
            "session.start runs no git before its timer",
        ),
        Mutation(
            "a write verb joins the refresh, so the band is no longer read-only",
            "const top = await git($, ['rev-parse', '--show-toplevel'])",
            "await git($, ['add', '-A'])\n  const top = await git($, ['rev-parse', '--show-toplevel'])",
            "read-only git calls",
        ),
        Mutation(
            "the busy guard is removed, so a slow refresh is overlapped by the next tick",
            "  if (busy) return\n",
            "",
            "overlapping tick",
        ),
        Mutation(
            "the timer callback stops catching, so a throwing redraw request reaches the host",
            "  } catch {\n    // Keep whatever the band last showed\n  } finally {",
            "  } finally {",
            "throwing redraw request",
        ),
        Mutation(
            "a detached HEAD stops being named, so the band shows an empty branch",
            "|| 'detached HEAD'",
            "|| ''",
            "a detached HEAD is named",
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
            "a second repeating timer is started, so every tick runs twice",
            "$.clock.every(2000, () => tick($))",
            "$.clock.every(2000, () => tick($))\n    $.clock.every(2000, () => tick($))",
            "starts one 2000 ms repeating timer",
        ),
        Mutation(
            "a turn.complete hook comes back, and with it a second event for the band to share",
            "  // Runs each time Claude Code draws the band above the prompt\n",
            "  on('turn.complete', async ($, e, next) => next(e))\n\n  // Runs each time Claude Code draws the band above the prompt\n",
            "no turn.complete hook is registered",
        ),
        Mutation(
            "the render hook loses its AbovePrompt matcher and draws at every site",
            "{ component: 'AbovePrompt' }",
            "{}",
            "limited to AbovePrompt",
        ),
    ),
)
