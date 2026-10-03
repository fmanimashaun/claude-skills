// context-nudge: shows how full this session's context window is, and once per climb past a
// threshold adds ONE line only Claude reads, asking it to offer a handoff and a /clear (#1547).
// It blocks nothing and rewrites no prompt text: every hook returns next(e), the prompt hook with at
// most one added context line. Mods need Claude Code 2.1.287 or later.
//
// The figure is the engine's own. `percent` is `tokens` over `window` as a whole percentage, the status
// line's used_percentage; `tokens` is uncached, cache-written and cache-read input together. It is absent
// until the first response of a window, and after a compaction until the next response (types for 2.1.287).

// A starting value, not a measured one: nothing has been measured about where a handoff stops being
// cheap (#1547). RAILS_FLOW_CONTEXT_NUDGE_PCT overrides it, whole percent, 1 to 99.
const DEFAULT_THRESHOLD = 70

// The last fill the engine measured, in whole percent, or null while the live window has no reading.
let percent = null
// The line has been added since the fill last fell below the threshold or lost its reading.
let nudged = false

// The line itself. It rides on a prompt, so its size is a cost: every character is billed again on
// each later request, which is why it is added once per climb and kept this short.
export function nudgeLine(fill) {
  return (
    `Context note: this session's context window is ${fill}% full. Finish the current step, then offer to ` +
    'write a handoff with /rails-flow:handoff and tell the user to run /clear or /compact before new work. ' +
    'Say this once; do not repeat it.'
  )
}

// The threshold in force: the environment's whole percent when it is one, else the default.
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

export function register(on) {
  // Runs after each turn, and whenever the fill moved: the figure is pushed, not polled
  on('session.measure', async ($, e, next) => {
    percent = e.context.percent ?? null
    $.ui.status(percent === null ? undefined : `context ${percent}%`)
    if (percent === null || percent < (await threshold($))) nudged = false
    return next(e)
  })

  // Runs when a prompt is submitted
  on('prompt.submit', async ($, e, next) => {
    if (percent === null || nudged || !isTheirs(e.origin) || percent < (await threshold($))) return next(e)
    nudged = true
    return next({ ...e, context: [...(e.context ?? []), nudgeLine(percent)] })
  })
}
