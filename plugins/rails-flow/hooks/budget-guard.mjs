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
// limit, and only after the first response; with no reading, nothing is refused for usage.
// A reading is the one the session's LAST API RESPONSE reported (the declared `SessionRateLimit` has `kind`, `percentUsed` and `resetsAt`, and no
// measurement time), so a session that has not had a response since the window reset still holds the OLD window's figure. #1854: on 2026-10-11 eight
// long-running sessions refused all new work on a weekly 90-96% that /usage showed as 6%, because the weekly window had reset at 02:00 UTC. The hook is
// advisory, so it fails OPEN: a window whose `resetsAt` has passed is no reading at all, and the refusal says what it knows (the reset time, how long
// THIS HOOK has seen the same figure, that the harness gives the reading no timestamp) and how to override it. A gateway's
// window is `spend_limit`, not the 7-day one, so the weekly refusal does not apply behind a gateway alone.
// A Workflow started by `name` or `scriptPath` carries no `script`, so the relay check cannot see it.

export const DEFAULT_WARN = 80
export const DEFAULT_BLOCK = 90
export const STARTUP_TOKENS = 60000
export const NOT_A_RELAY = '// budget-guard: not a relay'

// Has this window already reset? A reading whose `resetsAt` is at or before `now` describes a window that is over (#1854). With no usable `resetsAt`
// nothing proves it is stale, so it is not expired.
export function expired(resetsAt, now) {
  const t = resetsAt ? Date.parse(resetsAt) : Number.NaN
  return now !== undefined && !Number.isNaN(t) && t <= now
}

// The 7-day window's percent used, or null with no reading. With `now`, a window that has already reset is no reading.
export function weekly(rateLimits, now) {
  return windowOf(rateLimits, 'seven_day', now)?.pct ?? null
}

// "week 96% · 5h 40%", or undefined with no reading. Only the two subscription windows; with `now`, windows that have reset are left out.
export function limitsLabel(rateLimits, now) {
  const names = { seven_day: 'week', five_hour: '5h' }
  const parts = (rateLimits ?? [])
    .filter((r) => names[r.kind] && typeof r.percentUsed === 'number' && !expired(r.resetsAt, now))
    .map((r) => `${names[r.kind]} ${Math.round(r.percentUsed)}%`)
  return parts.length ? parts.join(' · ') : undefined
}

// One window's reading, `{ pct, resetsAt }`, or null. `resetsAt` is ISO 8601 in a mod (the status line's
// own JSON uses epoch seconds instead; the two are not mixed here).
// With `now`, a window that has already reset is null (#1854).
export function windowOf(rateLimits, kind, now) {
  const w = (rateLimits ?? []).find((r) => r.kind === kind)
  if (typeof w?.percentUsed !== 'number' || expired(w.resetsAt, now)) return null
  return { pct: w.percentUsed, resetsAt: w.resetsAt }
}

// "3 h 10 min", "25 min" or "under a minute".
export function ageText(ms) {
  const min = Math.floor(Math.max(0, ms) / 60000)
  if (min < 1) return 'under a minute'
  return min < 60 ? `${min} min` : `${Math.floor(min / 60)} h ${min % 60} min`
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

async function nowOf($) {
  try {
    return typeof $.clock?.now === 'function' ? await $.clock.now() : Date.now()
  } catch {
    return Date.now()
  }
}

// When THIS HOOK first saw each exact reading. The harness gives the reading no time, so "unchanged for hours" is the only age there is, and it is what
// a stale figure looks like (#1854). Keyed by figure and reset time; a new figure or a new window starts again.
const firstSeen = new Map()

// The weekly reading that blocks, `{ pct, resetsAt, ageMs }`, or null: no reading, a window that has reset, or below the hard level.
async function overBlock($) {
  if ((await $.env.get('RAILS_FLOW_BUDGET_ALLOW')) === '1') return null
  const now = await nowOf($)
  const w = windowOf((await $.session.usage()).rateLimits, 'seven_day', now)
  if (w === null) return null
  const key = `${w.pct}|${w.resetsAt ?? ''}`
  if (!firstSeen.has(key)) firstSeen.set(key, now)
  return w.pct >= (await blockAt($)) ? { ...w, ageMs: now - firstSeen.get(key), now } : null
}

// The refusal. Says what is known about the reading and how to override it (#1854): it is not a measurement the hook made.
function refusal(what, r, extra = '') {
  const t = r.resetsAt ? Date.parse(r.resetsAt) : Number.NaN
  const resets = Number.isNaN(t) ? '(no usable reset time)' : `(resets ${new Date(t).toISOString().slice(11, 16)} UTC, in ${ageText(t - r.now)})`
  return (
    `rails-flow budget-guard: the weekly limit reads ${Math.round(r.pct)}% used ${resets}; ${what} are refused${extra}. ` +
    `That figure is what the session's last API response reported: the harness gives it no timestamp, and this hook has seen the same reading for ` +
    `${ageText(r.ageMs)}. Run /usage; if it disagrees, say so and continue, or set RAILS_FLOW_BUDGET_ALLOW=1 to override.`
  )
}

export function register(on) {
  on('tool.call', { tool: 'Workflow' }, async ($, e, next) => {
    if (isRelay(e.script))
      return {
        deny:
          `rails-flow budget-guard: this workflow spawns agents to relay SendMessage, about ${STARTUP_TOKENS / 1000}k tokens of startup ` +
          `each. Call SendMessage directly, once per recipient, in one turn. If the agents do real work, add the line "${NOT_A_RELAY}".`,
      }
    const r = await overBlock($)
    if (r !== null) return { deny: refusal('new workflows', r) }
    return next(e)
  })

  on('tool.call', { tool: 'Agent' }, async ($, e, next) => {
    const r = await overBlock($)
    if (r !== null) return { deny: refusal('new agents', r, ` (about ${STARTUP_TOKENS / 1000}k tokens each)`) }
    return next(e)
  })
}
