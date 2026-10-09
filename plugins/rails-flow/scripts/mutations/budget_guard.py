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
    needs=("tests/budget-guard.unit.mjs", "hooks/context-nudge.mjs"),
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
            "return pct !== null && pct >= (await blockAt($)) ? pct : null",
            "return pct !== null && pct > (await blockAt($)) ? pct : null",
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
            "    const pct = await overBlock($)\n    if (pct !== null)\n      return { deny: `rails-flow budget-guard: the weekly limit is ${Math.round(pct)}% used; new agents",
            "    const pct = null\n    if (pct !== null)\n      return { deny: `rails-flow budget-guard: the weekly limit is ${Math.round(pct)}% used; new agents",
            "an agent is refused at the hard limit",
        ),
        Mutation(
            "no reading counts as 0%... or as full: a missing window refuses",
            "  return typeof w?.percentUsed === 'number' ? w.percentUsed : null",
            "  return typeof w?.percentUsed === 'number' ? w.percentUsed : 100",
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
    ),
)
