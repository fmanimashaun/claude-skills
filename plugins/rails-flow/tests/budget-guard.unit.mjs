// Unit tests for hooks/budget-guard.mjs, and its usage view inside hooks/context-nudge.mjs, against a fake
// host, run by plain Node (#1676, #1677). Run by scripts/check_mods.py and the mutation guard
// plugins/rails-flow/scripts/mutations/budget_guard.py. It does NOT exercise the real engine; that stays with
// `claude plugin validate` and `claude plugin test`, locally.
//
// Run: node plugins/rails-flow/tests/budget-guard.unit.mjs

import assert from 'node:assert/strict'

const failures = []
let checks = 0
let fresh = 0
process.on('exit', (code) => {
  if (failures.length === 0 && code === 0) return console.log(`budget-guard unit: ${checks} checks passed`)
  console.error(`budget-guard unit FAILED -- ${failures.length} failed of ${checks}:`)
  for (const f of failures) console.error(`  - ${f}`)
  process.exitCode = 1
})
async function check(name, body) {
  checks++
  try { await body() } catch (err) { failures.push(`${name}: ${err.message}`) }
}

const win = (week, five) => [
  ...(week === undefined ? [] : [{ kind: 'seven_day', percentUsed: week }]),
  ...(five === undefined ? [] : [{ kind: 'five_hour', percentUsed: five }]),
]
const echo = async (e) => ({ passed: e })
const RELAY = "await parallel(peers.map(p => () => agent(`Load SendMessage and send this to ${p}`)))"
const WORK = "const r = await agent('read the controller and list the routes')"

// The guard's two hooks, with a host answering the given usage and environment.
async function guard(week, env = {}) {
  const mod = await import(`../hooks/budget-guard.mjs?fresh=${++fresh}`)
  const hooks = {}
  mod.register((event, matcher, hook) => { hooks[`${event}:${matcher.tool}`] = hook })
  const $ = { env: { get: async (k) => env[k] }, session: { usage: async () => ({ rateLimits: win(week) }) } }
  return {
    mod,
    workflow: (script) => hooks['tool.call:Workflow']($, { script }, echo),
    agent: () => hooks['tool.call:Agent']($, { prompt: 'x' }, echo),
  }
}

// context-nudge's two hooks, to see the usage view it carries.
async function nudge(env = {}) {
  const mod = await import(`../hooks/context-nudge.mjs?fresh=${++fresh}`)
  const hooks = {}
  mod.register((event, ...rest) => { hooks[event] = rest[rest.length - 1] })
  const status = []
  const $ = { env: { get: async (k) => env[k] }, ui: { status: (t) => status.push(t) } }
  const id = async (e) => e
  return {
    status,
    measure: (week, five, ctx) => hooks['session.measure']($, { context: { window: 200000, ...(ctx === undefined ? {} : { percent: ctx, tokens: ctx * 2000 }) }, rateLimits: win(week, five), changed: ['rateLimits'] }, id),
    submit: () => hooks['prompt.submit']($, { text: 'hi' }, id),
  }
}

await check('a relay workflow is refused at any usage, naming the fix', async () => {
  const g = await guard(10)
  const r = await g.workflow(RELAY)
  assert.ok(r.deny && r.deny.includes('SendMessage directly'))
})
await check('a relay with no usage reading is still refused', async () => {
  assert.ok((await (await guard(undefined)).workflow(RELAY)).deny)
})
await check('the not-a-relay marker opts a working script out', async () => {
  const g = await guard(10)
  assert.ok((await g.workflow(`${RELAY}\n${g.mod.NOT_A_RELAY}`)).passed)
})
await check('a working workflow passes below the hard limit', async () => {
  assert.ok((await (await guard(85)).workflow(WORK)).passed)
})
await check('a working workflow is refused at the hard limit', async () => {
  const r = await (await guard(90)).workflow(WORK)
  assert.ok(r.deny && r.deny.includes('90%'))
})
await check('RAILS_FLOW_BUDGET_ALLOW=1 lets fan-out through at the hard limit', async () => {
  assert.ok((await (await guard(97, { RAILS_FLOW_BUDGET_ALLOW: '1' })).workflow(WORK)).passed)
  assert.ok((await (await guard(97, { RAILS_FLOW_BUDGET_ALLOW: '1' })).agent()).passed)
})
await check('the override does not let a relay through', async () => {
  assert.ok((await (await guard(10, { RAILS_FLOW_BUDGET_ALLOW: '1' })).workflow(RELAY)).deny)
})
await check('an agent is refused at the hard limit and passes below it', async () => {
  assert.ok((await (await guard(95)).agent()).deny)
  assert.ok((await (await guard(89.9)).agent()).passed)
})
await check('no usage reading refuses nothing for usage', async () => {
  assert.ok((await (await guard(undefined)).agent()).passed)
  assert.ok((await (await guard(undefined)).workflow(WORK)).passed)
})
await check('RAILS_FLOW_BUDGET_BLOCK_PCT moves the hard limit', async () => {
  assert.ok((await (await guard(60, { RAILS_FLOW_BUDGET_BLOCK_PCT: '50' })).agent()).deny)
  assert.ok((await (await guard(60, { RAILS_FLOW_BUDGET_BLOCK_PCT: 'x' })).agent()).passed)
})
await check('isRelay needs both an agent and SendMessage', async () => {
  const { isRelay } = (await guard(0)).mod
  assert.equal(isRelay("log('use SendMessage')"), false)
  assert.equal(isRelay(WORK), false)
  assert.equal(isRelay(undefined), false)
})
await check('the status line carries the weekly and 5-hour windows beside the context fill', async () => {
  const n = await nudge()
  await n.measure(41.6, 12, 30)
  assert.equal(n.status.at(-1), 'context 30% · week 42% · 5h 12%')
})
await check('with no windows the status line is the context fill alone', async () => {
  const n = await nudge()
  await n.measure(undefined, undefined, 30)
  assert.equal(n.status.at(-1), 'context 30%')
})
await check('at the warn level one usage line rides on the next prompt, once', async () => {
  const n = await nudge()
  await n.measure(85)
  const first = await n.submit()
  assert.equal(first.context.length, 1)
  assert.ok(first.context[0].includes('85% used'))
  assert.equal((await n.submit()).context, undefined)
})
await check('reaching block after warn adds the block line, once', async () => {
  const n = await nudge()
  await n.measure(85); await n.submit()
  await n.measure(92)
  const r = await n.submit()
  assert.ok(r.context[0].includes('refused'))
  assert.equal((await n.submit()).context, undefined)
})
await check('falling below warn resets, so the next climb is told again', async () => {
  const n = await nudge()
  await n.measure(85); await n.submit()
  await n.measure(40); await n.submit()
  await n.measure(81)
  assert.equal((await n.submit()).context.length, 1)
})
await check('the usage line is short (it is billed on every later request)', async () => {
  const { budgetLine } = (await guard(0)).mod
  assert.ok(budgetLine(96, 'block').length <= 200 && budgetLine(85, 'warn').length <= 200)
})
