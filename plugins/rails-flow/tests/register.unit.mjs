// hooks.json names ONE module (hooks/register.js) and it registers every mod rails-flow ships. Three things
// can go wrong there while every mod's own test stays green, and this checks all three (#1547, #1557):
//
//   0. hooks.json stops naming exactly ./register.js: a second path, or a mod named directly, bypasses the
//      aggregator below.
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

import { readdirSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { register } from '../hooks/register.js'

const HOOKS = fileURLToPath(new URL('../hooks/', import.meta.url))
const problems = []
let fresh = 0

// The options object handed to every register(on, options) below. register.js forwards whatever it is given
// to each mod, so calling register.js and each mod alone with the SAME object keeps the comparison fair, and a
// mod that reads `options` finds one instead of crashing on undefined.
const OPTIONS = {}

// What has been registered so far, kept up here with the report because the report must exist BEFORE the first
// await below: a mod whose import never settles ends the process with exit code 13 right there, and a handler
// registered at the bottom of the file would never have been registered at all.
const seen = new Set()
let mods = 0
let loading = '' // the file being imported right now, named if the import never finishes

process.on('exit', (code) => {
  if (loading !== '') problems.push(`${loading}: its import never finished (an await that never settles), so nothing after it was checked`)
  if (problems.length === 0 && code === 0) {
    console.log(`register unit: ${seen.size} hooks from ${mods} mods, each event and matcher once, every mod registered`)
    return
  }
  // `code` is the status the process was ABOUT to exit with: 0 when only a check failed (this handler then makes
  // it 1), 13 when an await never settled. It is named only when it is not 0, so the line never says "0" of a failure.
  const ended = code === 0 ? '' : `; the process had already ended with exit code ${code}`
  console.error(`register unit FAILED -- ${problems.length} problem(s)${ended}:`)
  for (const p of problems) console.error(`  - ${p}`)
  process.exitCode = 1
})

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

// 0. hooks.json names exactly ./register.js. Claude Code takes ONE module path there, and everything below
// assumes it is register.js: a second path, or a mod named directly, would bypass the aggregator and put
// two modules on the same events. (tests/lane-band.unit.mjs asserts the same from the lane band's side.)
const hooksJson = JSON.parse(readFileSync(new URL('../hooks/hooks.json', import.meta.url), 'utf8'))
if (JSON.stringify(hooksJson.modules) !== '["./register.js"]') {
  problems.push(`hooks.json "modules" is ${JSON.stringify(hooksJson.modules)}, not ["./register.js"]: it takes one path, and register.js is the module that registers every mod`)
}

// 1. register.js: every hook is a function, none is registered twice, and there is at least one. A throw is
// reported with the file's name, not left as a raw stack trace.
let viaRegister = []
try {
  viaRegister = record((on) => register(on, OPTIONS))
} catch (err) {
  problems.push(`register.js: register() threw: ${String(err.message).split('\n')[0]}`)
}
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
for (const file of files) {
  let mod
  try {
    loading = file
    mod = await import(`../hooks/${file}?fresh=${++fresh}`)
    loading = ''
  } catch (err) {
    loading = ''
    problems.push(`${file}: could not be imported (${String(err.message).split('\n')[0]})`)
    continue
  }
  if (typeof mod.register !== 'function') continue // a helper module, not a mod
  mods += 1
  let own = []
  try {
    own = record((on) => mod.register(on, OPTIONS))
  } catch (err) {
    problems.push(`${file}: register() threw: ${String(err.message).split('\n')[0]}`)
    continue
  }
  for (const { key } of own) {
    if (!seen.has(key)) problems.push(`${file}: its hook "${key}" is not registered by register.js, so the mod never runs`)
  }
}
if (mods === 0) problems.push('no mod was found in hooks/, so nothing was checked')
