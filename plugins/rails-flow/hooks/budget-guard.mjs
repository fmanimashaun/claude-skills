// budget-guard: keeps agent fan-out from spending an account's usage limit (#1676, #1677).
// Two refusals on the tool.call event, and pure helpers that context-nudge.mjs uses to show the limits.
// Mods need Claude Code 2.1.287 or later; the declarations cited are in
// docs/evidence/audits/2026-10-07-mods-tool-call-ratelimits-2.1.292.md.
//
// 1. A Workflow whose script has agents only relay SendMessage is refused at any usage. Each agent pays its whole
//    startup context (measured: ~62k tokens) to send a message a direct SendMessage call sends for a few
//    hundred. A script that really does work and also messages can say so with the marker below.
// 2. At or past the hard threshold of the 7-day window, a new Workflow or Agent is refused unless
//    RAILS_FLOW_BUDGET_ALLOW=1 is set. Direct tool use is never touched.
// The rate-limit windows appear only on a claude.ai Pro or Max subscription or behind a gateway spend
// limit, and only after the first response; with no reading, nothing is refused for usage. A gateway's
// window is `spend_limit`, not the 7-day one, so the weekly refusal does not apply behind a gateway alone.
// A Workflow started by `name` or `scriptPath` carries no `script`, so the relay check cannot see it.

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

// One window's reading, `{ pct, resetsAt }`, or null. `resetsAt` is ISO 8601 in a mod (the status line's
// own JSON uses epoch seconds instead; the two are not mixed here).
export function windowOf(rateLimits, kind) {
  const w = (rateLimits ?? []).find((r) => r.kind === kind)
  return typeof w?.percentUsed === 'number' ? { pct: w.percentUsed, resetsAt: w.resetsAt } : null
}

// The level a reading is at: 'block', 'warn' or null.
export function level(pct, warn = DEFAULT_WARN, block = DEFAULT_BLOCK) {
  if (pct === null || pct === undefined) return null
  return pct >= block ? 'block' : pct >= warn ? 'warn' : null
}

// " (resets 14:05 UTC)" from an ISO time, or "" without one.
export function resetText(resetsAt) {
  const t = resetsAt ? new Date(resetsAt) : null
  return t && !Number.isNaN(t.getTime()) ? ` (resets ${t.toISOString().slice(11, 16)} UTC)` : ''
}

// Milliseconds from `now` until `resetsAt`, or null.
export function msUntil(resetsAt, now) {
  const t = resetsAt ? Date.parse(resetsAt) : Number.NaN
  return Number.isNaN(t) ? null : Math.max(0, t - now)
}

// The one line Claude reads when a window first reaches a level. The point of the warn line is to write
// things down while there is still budget to do it. Kept short: it is billed again on every later request.
export function budgetLine(kind, pct, lvl, resetsAt, willResume = false) {
  const name = kind === 'five_hour' ? '5-hour' : 'weekly'
  const head = `Usage note: the ${name} limit is ${Math.round(pct)}% used${resetText(resetsAt)}.`
  if (lvl === 'warn')
    return `${head} Update the handoff now (/rails-flow:handoff) and commit and push work in progress; avoid Workflow and Agent fan-out.`
  const wait = kind === 'five_hour' && willResume ? ' rails-flow will resume this session after the reset.' : ''
  const refuse = kind === 'seven_day' ? ' New Workflow and Agent calls are refused.' : ''
  return `${head} Stop starting new work: finish this step, update the handoff, commit and push, then stop.${refuse}${wait}`
}

// What the resume prompt says once the 5-hour window has reset.
export const RESUME_TEXT =
  'The 5-hour usage limit has reset. Resume: read the handoff (HANDOFF.md, or the latest PR or issue comment you wrote), check the branch and its pushed SHA, then continue from the recorded next step.'

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
