// hooks.json names ONE module (hooks/register.js) and it registers every mod rails-flow ships. Two things
// can go wrong there while every mod's own test stays green, and this checks both (#1547, #1557):
//
//   1. A hook registered twice. Claude Code refuses two hooks on the same event with no matcher, and two on
//      one event and the same matcher, so register.js, with every mod it calls, must register each
//      (event, matcher) at most once.
//   2. A mod that is never registered. Each mod's own unit test imports its module directly, so deleting a
//      mod's call from register.js leaves that test passing and the mod dead. So this finds every mod in
//      hooks/ by what it EXPORTS, not by name (a new mod needs no change here), runs each alone, and asserts
//      every hook it registers is also registered when register.js runs.
//
// It runs the modules with a recording `on`; it does not start the engine.
//
// Run: node plugins/rails-flow/tests/register.unit.mjs

import { readdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { register } from '../hooks/register.js'

const HOOKS = fileURLToPath(new URL('../hooks/', import.meta.url))
const problems = []
let fresh = 0

// What a register(on, options) function registers: one entry per hook, keyed `event` or `event {matcher}`.
function record(fn) {
  const keys = []
  fn((event, ...rest) => {
    const hook = rest[rest.length - 1]
    const matcher = rest.length > 1 ? JSON.stringify(rest[0]) : ''
    keys.push({ key: `${event} ${matcher}`.trim(), isFunction: typeof hook === 'function' })
  })
  return keys
}

// 1. register.js: every hook is a function, none is registered twice, and there is at least one.
const viaRegister = record((on) => register(on))
const seen = new Set()
for (const { key, isFunction } of viaRegister) {
  if (!isFunction) problems.push(`${key}: the last argument is not a function`)
  if (seen.has(key)) problems.push(`${key}: registered twice`)
  seen.add(key)
}
if (viaRegister.length === 0) problems.push('register.js registered no hook at all')

// 2. every mod in hooks/ reaches register.js. A mod is a file there, other than register.js, that exports a
// `register` function. Each is imported with a ?fresh=N query: a mod keeps its state in module variables
// (context-nudge.mjs: percent, nudged; lane-band.js: info, busy), so a shared import would leak it.
const files = readdirSync(HOOKS).filter((f) => /\.(mjs|js)$/.test(f) && f !== 'register.js').sort()
let mods = 0
for (const file of files) {
  let mod
  try {
    mod = await import(`../hooks/${file}?fresh=${++fresh}`)
  } catch (err) {
    problems.push(`${file}: could not be imported (${String(err.message).split('\n')[0]})`)
    continue
  }
  if (typeof mod.register !== 'function') continue // a helper module, not a mod
  mods += 1
  for (const { key } of record((on) => mod.register(on))) {
    if (!seen.has(key)) problems.push(`${file}: its hook "${key}" is not registered by register.js, so the mod never runs`)
  }
}
if (mods === 0) problems.push('no mod was found in hooks/, so nothing was checked')

// Report from an 'exit' handler: a check that never settles ends the process (exit code 13, an unsettled
// top-level await) before any line below would run, and the problems would vanish.
process.on('exit', (code) => {
  if (problems.length === 0 && code === 0) {
    console.log(`register unit: ${seen.size} hooks from ${mods} mods, each event and matcher once, every mod registered`)
    return
  }
  console.error(`register unit FAILED -- ${problems.length} problem(s), exit code ${code}:`)
  for (const p of problems) console.error(`  - ${p}`)
  process.exitCode = 1
})
