// context-nudge: shows how full this session's context window is, and once per climb past a
// threshold adds ONE line only Claude reads, asking it to offer a handoff (#1547). A session with an elected
// role is told it resets itself instead, and compacts mid-job at RAILS_FLOW_COMPACT_PCT or a usage warn level
// (#1723, #1724; hooks/session-reset.mjs).
// It blocks nothing and rewrites no prompt text: every hook returns next(e), the prompt hook with at
// most one added context line. Mods need Claude Code 2.1.287 or later.
//
// It also carries budget-guard's account-usage view (#1677), because a plugin registers each event once:
// the 7-day and 5-hour windows join the status line, and once per level reached (warn, then block) one
// usage line rides on a prompt, so Claude knows its budget without being told. budget-guard.mjs holds the
// pure helpers; this module passes them data only, never `$`.
//
// The figure is the engine's own. `percent` is `tokens` over `window` as a whole percentage, the status
// line's used_percentage; `tokens` is uncached, cache-written and cache-read input together. It is absent
// until the first response of a window, and after a compaction until the next response (types for 2.1.287).

// A starting value, not a measured one: nothing has been measured about where a handoff stops being
// cheap (#1547). RAILS_FLOW_CONTEXT_NUDGE_PCT overrides it, whole percent, 1 to 99.
const DEFAULT_THRESHOLD = 70

import { budgetLine, DEFAULT_BLOCK, DEFAULT_WARN, level, limitsLabel, msUntil, RESUME_TEXT, windowOf } from './budget-guard.mjs'
import { compactInstructions, compactReason, DEFAULT_COMPACT_PCT, DEFAULT_COORDINATOR_HANDOFF, job, jobDoneShape, state, wholePct } from './session-reset.mjs'

// Mid-job compaction (#1687): which sources have already compacted this climb, so each fires once.
const compacted = { context: false, five_hour: false, seven_day: false }
// The one role line (the elected role, or that none could be elected) has been added.
let askedRole = false
export const ROLE_LINE =
  'Role note: rails-flow could not elect a role for this session. Start it with RAILS_FLOW_ROLE=coordinator or ' +
  'RAILS_FLOW_ROLE=implementation; until then it will neither clear nor compact this session. Say this once.'

// Each window's last reading, and the highest level announced since it was last below warn.
const WINDOWS = ['five_hour', 'seven_day']
const reading = { five_hour: null, seven_day: null }
const announced = { five_hour: null, seven_day: null }
// The pending resume after the 5-hour window resets, so it is scheduled once.
let resume = null

// The last fill the engine measured, in whole percent, or null while the live window has no reading.
let percent = null
// The line has been added since the fill last fell below the threshold or lost its reading.
let nudged = false

// The line itself. It rides on a prompt, so its size is a cost: every character is billed again on
// each later request, which is why it is added once per climb and kept this short.
export function nudgeLine(fill, role = null) {
  const head = `Context note: this session's context window is ${fill}% full. Finish the current step, then `
  if (role === 'coordinator')
    return `${head}update the coordinator handoff. This session compacts itself at the compact threshold; do not ask the user to run /clear. Say this once; do not repeat it.`
  if (role === 'implementation')
    return (
      `${head}update the handoff (/rails-flow:handoff) and commit and push work in progress. This session compacts itself ` +
      'at the compact threshold and clears itself once its PR is merged into dev and its worktree is removed; do not ask the user to run /clear. Say this once; do not repeat it.'
    )
  return (
    `${head}offer to ` +
    'write a handoff with /rails-flow:handoff and tell the user to run /clear (not /compact: the handoff already holds it) before new work. ' +
    'Say this once; do not repeat it.'
  )
}

// The threshold in force: the environment's whole percent when it is one, else the default.
// A whole percent from 1 to 100, or the default.
function pct(raw, dflt) {
  const n = Number.parseInt(raw ?? '', 10)
  return Number.isInteger(n) && n >= 1 && n <= 100 ? n : dflt
}

async function budgetLevels($) {
  return [
    pct(await $.env.get('RAILS_FLOW_BUDGET_WARN_PCT'), DEFAULT_WARN),
    pct(await $.env.get('RAILS_FLOW_BUDGET_BLOCK_PCT'), DEFAULT_BLOCK),
  ]
}

async function threshold($) {
  const raw = await $.env.get('RAILS_FLOW_CONTEXT_NUDGE_PCT')
  const n = Number.parseInt(raw ?? '', 10)
  return Number.isInteger(n) && n >= 1 && n <= 99 ? n : DEFAULT_THRESHOLD
}

// Only a prompt from a person at an interactive surface carries the line: `composer` (Enter at the prompt),
// `bridge` (Remote Control from a phone or the web), or no origin at all, which the engine defines as the
// user's own. Every other kind is refused on purpose, so the line is not used up on a message the person
// never reads: a peer session, a scheduled task, a background notification, another plugin, a channel
// relay. `sdk` is refused too: `claude -p` and the Agent SDK have nobody to run /clear, so asking Claude to
// tell the user to would only waste the line (mod hooks do run there; the docs say so). The kinds are a
// closed set in the engine's types for 2.1.287; docs/evidence/audits/2026-10-02-mods-api-2.1.287.md.
function isTheirs(origin) {
  return origin === undefined || origin.kind === 'composer' || origin.kind === 'bridge'
}

// Compact this session, never clear it, when the context fill or a usage window reaches its level while the
// session has a declared role (#1687). Runs from a timer: compact rejects inside a hook the turn waits on, and
// a rejection (a turn is running) re-arms the source so the next measure tries again. A role-less session, a
// `claude -p` run (no surface) and a session whose job is done (it clears instead) are left alone.
async function maybeCompact($, levels) {
  try {
    const role = state.role
    const compactPct = wholePct(await $.env.get('RAILS_FLOW_COMPACT_PCT'), DEFAULT_COMPACT_PCT)
    const sources = {
      context: { fill: percent, windows: [] },
      five_hour: { fill: null, windows: [{ lvl: level(reading.five_hour?.pct, ...levels), announced: announced.five_hour }] },
      seven_day: { fill: null, windows: [{ lvl: level(reading.seven_day?.pct, ...levels), announced: announced.seven_day }] },
    }
    for (const [key, src] of Object.entries(sources)) {
      const live = key === 'context' ? percent !== null && percent >= compactPct : src.windows[0].lvl !== null
      if (!live) compacted[key] = false
    }
    if (role === null || (role === 'implementation' && (jobDoneShape() || job.pending))) return
    for (const [key, src] of Object.entries(sources)) {
      if (compacted[key] || compactReason({ role, compactPct, nudged, ...src }) === null) continue
      if ((await $.session.surfaces()).length === 0) return
      compacted[key] = true
      const text = compactInstructions(role, job, (await $.env.get('RAILS_FLOW_COORDINATOR_HANDOFF')) || DEFAULT_COORDINATOR_HANDOFF)
      $.clock.after(0, () => {
        void (async () => {
          try {
            await $.session.compact({ instructions: text })
          } catch {
            compacted[key] = false
          }
        })()
      })
      return
    }
  } catch {
    // Advisory: a failed check leaves the session as it was
  }
}

export function register(on) {
  // Runs after each turn, and whenever the fill moved: the figure is pushed, not polled
  on('session.measure', async ($, e, next) => {
    percent = e.context.percent ?? null
    const levels = await budgetLevels($)
    for (const k of WINDOWS) {
      reading[k] = windowOf(e.rateLimits, k)
      if (level(reading[k]?.pct, ...levels) === null) announced[k] = null
    }
    const limits = limitsLabel(e.rateLimits)
    const parts = [percent === null ? null : `context ${percent}%`, limits ?? null].filter(Boolean)
    $.ui.status(parts.length ? parts.join(' · ') : undefined)
    // At the 5-hour hard level, schedule one prompt for just after the reset, so the work resumes by itself.
    const five = reading.five_hour
    if (resume === null && level(five?.pct, ...levels) === 'block' && (await $.env.get('RAILS_FLOW_AUTO_RESUME')) !== '0') {
      const ms = msUntil(five.resetsAt, await $.clock.now())
      if (ms !== null) resume = $.clock.after(ms + 120000, () => { resume = null; void $.prompt.submit({ text: RESUME_TEXT }) })
    }
    if (percent === null || percent < (await threshold($))) nudged = false
    await maybeCompact($, levels)
    return next(e)
  })

  // Runs when a prompt is submitted
  on('prompt.submit', async ($, e, next) => {
    const lines = []
    const levels = await budgetLevels($)
    for (const k of WINDOWS) {
      const lvl = level(reading[k]?.pct, ...levels)
      if (lvl !== null && lvl !== announced[k] && !(announced[k] === 'block' && lvl === 'warn')) {
        announced[k] = lvl
        lines.push(budgetLine(k, reading[k].pct, lvl, reading[k].resetsAt, k === 'five_hour' && resume !== null))
      }
    }
    const role = state.role
    if (!askedRole && isTheirs(e.origin)) {
      askedRole = true
      lines.push(state.line ?? ROLE_LINE)
    }
    if (percent !== null && !nudged && isTheirs(e.origin) && percent >= (await threshold($))) {
      nudged = true
      lines.push(nudgeLine(percent, role))
    }
    return lines.length ? next({ ...e, context: [...(e.context ?? []), ...lines] }) : next(e)
  })
}
