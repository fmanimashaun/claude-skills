"""Mutation guard: lane_band. Declared here, run by scripts/mutation_check.py (#1537)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #1537. The band is READ-ONLY and must never make a prompt or a turn's end wait, so each break below is a
# way it stops being that: a write or a lock-taking git call, an awaited refresh, an overlapping or throwing
# tick, or a band that shows the wrong thing. The selftest is the Node unit test (a hand-built host), run
# through the shared wrapper scripts/check_mods.py. The engine is not in the loop; `claude plugin test` is,
# locally only. register.js's wiring is checked by the same unit test and by register.unit.mjs.
GUARD = Guard(
    name="lane_band",
    subject="hooks/lane-band.js",
    selftest="scripts/check_mods.py",
    selftest_args=("lane-band",),
    # Read, not imported: the unit test checks that hooks.json names register.js and that it calls the mod.
    needs=(
        "tests/lane-band.unit.mjs",
        "hooks/hooks.json",
        "hooks/register.js",
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
