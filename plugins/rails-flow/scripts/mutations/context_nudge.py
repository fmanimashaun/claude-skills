"""Mutation guard: context_nudge. Declared here, run by scripts/mutation_check.py (#1547)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #1547. The mod adds one line to the person's prompt, so each way it goes wrong costs tokens or hides the
# advice: nagging every prompt, never nagging, riding on a peer's message, or moving the threshold.
# The selftest is the Node unit test (a hand-built host), run through a Python wrapper so the shared runner
# can stage it. The engine itself is not in the loop; `claude plugin test` is, locally only.
#
# One mutation is NOT listed because it is equivalent: dropping the explicit `percent === null` clause
# from the prompt hook changes nothing, since `null < 70` is already true in JavaScript.
GUARD = Guard(
    name="context_nudge",
    subject="hooks/context-nudge.mjs",
    selftest="scripts/check_mods.py",
    selftest_args=("context-nudge", "budget-guard"),
    needs=("tests/context-nudge.unit.mjs", "tests/budget-guard.unit.mjs", "hooks/budget-guard.mjs"),
    mutations=(
        Mutation(
            "the once-per-climb flag is never set, so every prompt past the threshold is nagged",
            "      nudged = true\n      lines.push(nudgeLine(percent))",
            "      lines.push(nudgeLine(percent))",
            "at the threshold one line is added, once",
        ),
        Mutation(
            "a compaction or a drop never resets the flag, so the next climb is never told",
            "    if (percent === null || percent < (await threshold($))) nudged = false\n",
            "    // never reset\n",
            "a compaction resets it",
        ),
        Mutation(
            "any prompt origin takes the line, so a peer's message uses it up",
            "  return origin === undefined || origin.kind === 'composer' || origin.kind === 'bridge'",
            "  return true",
            "never takes the line, and does not use it up",
        ),
        Mutation(
            "an SDK turn (claude -p) counts as the person, so the line is spent where nobody can /clear",
            " || origin.kind === 'bridge'",
            " || origin.kind === 'bridge' || origin.kind === 'sdk'",
            'a prompt from "sdk" never takes the line',
        ),
        Mutation(
            "a Remote Control prompt stops counting as the person",
            " || origin.kind === 'bridge'",
            "",
            "a Remote Control prompt counts as the person",
        ),
        Mutation(
            "the default threshold drops to 60",
            "const DEFAULT_THRESHOLD = 70",
            "const DEFAULT_THRESHOLD = 60",
            "below the threshold a prompt carries no added context",
        ),
        Mutation(
            "the fill is never pinned under the prompt",
            "    $.ui.status(parts.length ? parts.join(' · ') : undefined)\n",
            "    // no status\n",
            "the fill is pinned under the prompt",
        ),
        Mutation(
            "the environment override is ignored",
            "  return Number.isInteger(n) && n >= 1 && n <= 99 ? n : DEFAULT_THRESHOLD",
            "  return DEFAULT_THRESHOLD",
            "RAILS_FLOW_CONTEXT_NUDGE_PCT moves the threshold",
        ),
        Mutation(
            "a threshold above 99 is accepted",
            "n >= 1 && n <= 99 ?",
            "n >= 1 ?",
            'a threshold of "150" falls back to the default',
        ),
        Mutation(
            "a threshold below 1 is accepted",
            "n >= 1 && n <= 99 ?",
            "n <= 99 ?",
            'a threshold of "0" falls back to the default',
        ),
        Mutation(
            "a value that is not a whole number is read as zero",
            "  return Number.isInteger(n) && n >= 1 && n <= 99 ? n : DEFAULT_THRESHOLD",
            "  return Number.isInteger(n) && n >= 1 && n <= 99 ? n : raw ? 0 : DEFAULT_THRESHOLD",
            'a threshold of "lots" falls back to the default',
        ),
        Mutation(
            "the line grows past 400 characters",
            "'Say this once; do not repeat it.'",
            "'Say this once; do not repeat it. ' + 'x'.repeat(400)",
            "the line is short",
        ),
        Mutation(
            "#1677: the usage line is announced on every prompt, not once per level",
            "        announced[k] = lvl\n",
            "",
            "at the warn level one usage line rides on the next prompt, once",
        ),
        Mutation(
            "#1677: falling below warn never resets, so the next climb is never told",
            "      if (level(reading[k]?.pct, ...levels) === null) announced[k] = null\n",
            "",
            "falling below warn resets, so the next climb is told again",
        ),
        Mutation(
            "#1677: the usage windows never reach the status line",
            "    const limits = limitsLabel(e.rateLimits)\n",
            "    const limits = undefined\n",
            "the status line carries the weekly and 5-hour windows",
        ),
        Mutation(
            "#1677: block after warn is swallowed as already announced",
            "lvl !== announced[k] && ",
            "announced[k] === null && ",
            "reaching block after warn adds the block line, once",
        ),
        Mutation(
            "the auto-resume never fires: the timer is never set",
            "      if (ms !== null) resume = $.clock.after(",
            "      if (false) resume = $.clock.after(",
            "at the 5-hour hard level one resume is scheduled",
        ),
        Mutation(
            "the resume is scheduled on every measurement, not once",
            "    if (resume === null && level(five?.pct",
            "    if (level(five?.pct",
            "at the 5-hour hard level one resume is scheduled",
        ),
        Mutation(
            "RAILS_FLOW_AUTO_RESUME=0 is ignored",
            " && (await $.env.get('RAILS_FLOW_AUTO_RESUME')) !== '0'",
            "",
            "RAILS_FLOW_AUTO_RESUME=0 schedules nothing",
        ),
        Mutation(
            "only the weekly window is announced; the 5-hour window is never watched",
            "const WINDOWS = ['five_hour', 'seven_day']",
            "const WINDOWS = ['seven_day']",
            "the 5-hour warn line tells Claude to write the handoff",
        ),
    ),
)
