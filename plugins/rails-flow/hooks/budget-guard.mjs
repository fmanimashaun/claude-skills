// budget-guard: keeps agent fan-out from spending an account's usage limit (#1676, #1677).
// Two refusals on the tool.call event, and pure helpers that context-nudge.mjs uses to show the limits.
// Mods need Claude Code 2.1.287 or later; the declarations cited are in
// docs/evidence/audits/2026-10-07-mods-tool-call-ratelimits-2.1.292.md.
//
// 1. A Workflow whose agents only relay SendMessage is refused at any usage. Each agent pays its whole
//    startup context (measured: ~62k tokens) to send a message a direct SendMessage call sends for a few
//    hundred. A script that really does work and also messages can say so with the marker below.
// 2. At or past the hard threshold of the 7-day window, a new Workflow or Agent is refused unless
//    RAILS_FLOW_BUDGET_ALLOW=1 is set. Direct tool use is never touched.
// The rate-limit windows appear only on a claude.ai Pro or Max subscription or behind a gateway spend
// limit, and only after the first response; with no reading, nothing is refused for usage.

export const DEFAULT_WARN = 80
export const DEFAULT_BLOCK = 90
export const STARTUP_TOKENS = 60000
export const NOT_A_RELAY = '// budget-guard: not a relay'

// The 7-day window's percent used, or null with no reading.
export function weekly(rateLimits) {
  const w = (rateLimits ?? []).find((r) => r.kind === 'seven_day')
  return typeof w?.percentUsed === 'number' ? w.percentUsed : null
}

// "week 96% · 5h 40%", or undefined with no reading. Only the two subscription windows.
export function limitsLabel(rateLimits) {
  const names = { seven_day: 'week', five_hour: '5h' }
  const parts = (rateLimits ?? [])
    .filter((r) => names[r.kind] && typeof r.percentUsed === 'number')
    .map((r) => `${names[r.kind]} ${Math.round(r.percentUsed)}%`)
  return parts.length ? parts.join(' · ') : undefined
}

// The level a reading is at: 'block', 'warn' or null.
export function level(pct, warn = DEFAULT_WARN, block = DEFAULT_BLOCK) {
  if (pct === null) return null
  return pct >= block ? 'block' : pct >= warn ? 'warn' : null
}

// The one line Claude reads when the weekly window first reaches a level. Kept short: it is billed again on
// every later request.
export function budgetLine(pct, lvl) {
  const head = `Usage note: this account's weekly limit is ${Math.round(pct)}% used.`
  return lvl === 'block'
    ? `${head} New Workflow and Agent calls are refused; do essential work with direct tool calls and keep output short.`
    : `${head} Avoid Workflow and Agent fan-out (about 60k tokens of startup per agent); message sessions with direct SendMessage calls.`
}

// A workflow that spawns agents to relay SendMessage. The marker opts out a script that really does work.
export function isRelay(script) {
  return typeof script === 'string' && !script.includes(NOT_A_RELAY) && /\bSendMessage\b/.test(script) && /\bagent\s*\(/.test(script)
}

async function blockAt($) {
  const n = Number.parseInt((await $.env.get('RAILS_FLOW_BUDGET_BLOCK_PCT')) ?? '', 10)
  return Number.isInteger(n) && n >= 1 && n <= 100 ? n : DEFAULT_BLOCK
}

async function overBlock($) {
  if ((await $.env.get('RAILS_FLOW_BUDGET_ALLOW')) === '1') return null
  const pct = weekly((await $.session.usage()).rateLimits)
  return pct !== null && pct >= (await blockAt($)) ? pct : null
}

export function register(on) {
  on('tool.call', { tool: 'Workflow' }, async ($, e, next) => {
    if (isRelay(e.script))
      return {
        deny:
          `rails-flow budget-guard: this workflow spawns agents to relay SendMessage, about ${STARTUP_TOKENS / 1000}k tokens of startup ` +
          `each. Call SendMessage directly, once per recipient, in one turn. If the agents do real work, add the line "${NOT_A_RELAY}".`,
      }
    const pct = await overBlock($)
    if (pct !== null)
      return { deny: `rails-flow budget-guard: the weekly limit is ${Math.round(pct)}% used; new workflows are refused. Set RAILS_FLOW_BUDGET_ALLOW=1 to override.` }
    return next(e)
  })

  on('tool.call', { tool: 'Agent' }, async ($, e, next) => {
    const pct = await overBlock($)
    if (pct !== null)
      return { deny: `rails-flow budget-guard: the weekly limit is ${Math.round(pct)}% used; new agents are refused (about ${STARTUP_TOKENS / 1000}k tokens each). Set RAILS_FLOW_BUDGET_ALLOW=1 to override.` }
    return next(e)
  })
}
