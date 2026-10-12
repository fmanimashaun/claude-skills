"""Mutation guard: budget_guard. Declared here, run by scripts/mutation_check.py (#1676, #1677)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #1676 refuses a Workflow whose agents only relay SendMessage (measured ~680k tokens per 11-way broadcast);
# #1677 refuses agent fan-out at the weekly hard limit. Each break below would let that spend through, or
# block work it must not. The selftest is the Node unit test under a hand-built host; the engine is not in
# the loop (`claude plugin test` is, locally).
GUARD = Guard(
    name="budget_guard",
    subject="hooks/budget-guard.mjs",
    selftest="scripts/check_mods.py",
    selftest_args=("budget-guard",),
    needs=("tests/budget-guard.unit.mjs", "hooks/context-nudge.mjs", "hooks/session-reset.mjs"),
    mutations=(
        Mutation(
            "a relay workflow is no longer refused",
            "    if (isRelay(e.script))\n",
            "    if (false)\n",
            "a relay workflow is refused at any usage",
        ),
        Mutation(
            "the not-a-relay marker is ignored, so a working script cannot opt out",
            "!script.includes(NOT_A_RELAY) && ",
            "",
            "the not-a-relay marker opts a working script out",
        ),
        Mutation(
            "any script naming SendMessage counts as a relay, agent or not",
            " && /\\bagent\\s*\\(/.test(script)",
            "",
            "isRelay needs both an agent and SendMessage",
        ),
        Mutation(
            "the override lets a relay through",
            "    if (isRelay(e.script))\n",
            "    if (isRelay(e.script) && (await $.env.get('RAILS_FLOW_BUDGET_ALLOW')) !== '1')\n",
            "the override does not let a relay through",
        ),
        Mutation(
            "the hard limit is checked with >, so exactly 90% passes",
            "return w.pct >= (await blockAt($)) ? { ...w, ageMs: now - firstSeen.get(key), now } : null",
            "return w.pct > (await blockAt($)) ? { ...w, ageMs: now - firstSeen.get(key), now } : null",
            "a working workflow is refused at the hard limit",
        ),
        Mutation(
            "the override is ignored",
            "  if ((await $.env.get('RAILS_FLOW_BUDGET_ALLOW')) === '1') return null\n",
            "",
            "RAILS_FLOW_BUDGET_ALLOW=1 lets fan-out through",
        ),
        Mutation(
            "the threshold variable is ignored",
            "  return Number.isInteger(n) && n >= 1 && n <= 100 ? n : DEFAULT_BLOCK",
            "  return DEFAULT_BLOCK",
            "RAILS_FLOW_BUDGET_BLOCK_PCT moves the hard limit",
        ),
        Mutation(
            "an Agent is never refused for usage",
            "    const r = await overBlock($)\n    if (r !== null) return { deny: refusal('new agents'",
            "    const r = null\n    if (r !== null) return { deny: refusal('new agents'",
            "an agent is refused at the hard limit",
        ),
        Mutation(
            "no reading counts as 0%... or as full: a missing window refuses",
            "  if (typeof w?.percentUsed !== 'number' || expired(w.resetsAt, now)) return null",
            "  if (typeof w?.percentUsed !== 'number') return { pct: 100 }\n  if (expired(w.resetsAt, now)) return null",
            "no usage reading refuses nothing for usage",
        ),
        Mutation(
            "the warn line stops asking for the handoff",
            "Update the handoff now (/rails-flow:handoff) and commit and push work in progress",
            "Be careful",
            "the 5-hour warn line tells Claude to write the handoff",
        ),
        Mutation(
            "the reset time is dropped from the line",
            "? ` (resets ${t.toISOString().slice(11, 16)} UTC)` : ''",
            "? '' : ''",
            "names the reset time",
        ),
        Mutation(
            "the resume waits for the wrong time (from the epoch, not from now)",
            "Math.max(0, t - now)",
            "Math.max(0, t)",
            "at the 5-hour hard level one resume is scheduled",
        ),
        # #1854: a reading from a window that has already reset is no reading; the refusal names what it knows and the override.
        Mutation(
            'a window that has reset is still a reading',
            '  return now !== undefined && !Number.isNaN(t) && t <= now',
            '  return false',
            'a weekly reading whose resetsAt has passed is no reading',
        ),
        Mutation(
            'a window is expired only after resetsAt, not at it',
            '!Number.isNaN(t) && t <= now',
            '!Number.isNaN(t) && t < now',
            'a weekly reading is expired at exactly resetsAt',
        ),
        Mutation(
            'a window is expired a millisecond early',
            '!Number.isNaN(t) && t <= now',
            '!Number.isNaN(t) && t <= now + 1',
            'one millisecond before resetsAt',
        ),
        Mutation(
            'the guard reads the weekly window without the clock',
            "windowOf((await $.session.usage()).rateLimits, 'seven_day', now)",
            "windowOf((await $.session.usage()).rateLimits, 'seven_day')",
            'a weekly reading whose resetsAt has passed is no reading',
        ),
        Mutation(
            'the refusal names no override',
            'Run /usage; if it disagrees, say so and continue, or set RAILS_FLOW_BUDGET_ALLOW=1 to override.',
            'Set RAILS_FLOW_BUDGET_ALLOW=1 to override.',
            'names the reset time, says the harness gives the reading no timestamp, and names the override',
        ),
        Mutation(
            'the refusal does not say how long the reading has been seen',
            '${ageText(r.ageMs)}. Run /usage',
            'an unknown time. Run /usage',
            'names how long this hook has seen the same reading',
        ),
        Mutation(
            'a new figure does not restart the age',
            "const key = `${w.pct}|${w.resetsAt ?? ''}`",
            "const key = `${w.resetsAt ?? ''}`",
            'a new figure restarts the age',
        ),
        Mutation(
            'the usage label keeps a window that has reset',
            "    .filter((r) => names[r.kind] && typeof r.percentUsed === 'number' && !expired(r.resetsAt, now))",
            "    .filter((r) => names[r.kind] && typeof r.percentUsed === 'number')",
            'the usage view leaves out a window that has already reset',
        ),
        Mutation(
            'windowOf keeps a window that has reset',
            "  if (typeof w?.percentUsed !== 'number' || expired(w.resetsAt, now)) return null",
            "  if (typeof w?.percentUsed !== 'number') return null",
            'a 5-hour reading that has already reset schedules no resume prompt',
        ),
        Mutation(
            'the host clock is ignored',
            "    return await $.clock.now()",
            '    return Date.now()',
            'a working workflow is refused at the hard limit',
        ),
    ),
)
