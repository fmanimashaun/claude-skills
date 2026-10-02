// hooks.json names ONE module (hooks/register.js) and it registers every mod rails-flow ships. Claude Code
// refuses two hooks on the same event with no matcher, and two on one event and the same matcher, so this
// checks that register.js, with every mod it calls, registers each (event, matcher) at most once (#1547).
// It runs hooks/register.js with a recording `on`; it does not start the engine.
//
// Run: node plugins/rails-flow/tests/register.unit.mjs

import { register } from '../hooks/register.js'

const seen = new Map()
const dup = []
let hooks = 0

register((event, ...rest) => {
  const hook = rest[rest.length - 1]
  const matcher = rest.length > 1 ? JSON.stringify(rest[0]) : ''
  const key = `${event} ${matcher}`.trim()
  hooks += 1
  if (typeof hook !== 'function') dup.push(`${key}: the last argument is not a function`)
  if (seen.has(key)) dup.push(`${key}: registered twice`)
  seen.set(key, true)
})

if (hooks === 0) dup.push('register.js registered no hook at all')

if (dup.length > 0) {
  console.error(`register unit FAILED -- ${dup.length} problem(s):`)
  for (const d of dup) console.error(`  - ${d}`)
  process.exit(1)
}
console.log(`register unit: ${hooks} hooks, each event and matcher once`)
