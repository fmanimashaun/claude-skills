// Unit tests for hooks/context-nudge.mjs against a fake host, run by plain Node (#1547).
//
// WHY THIS EXISTS BESIDE context-nudge.test.ts: `claude plugin test` needs the `claude` CLI, which the gate
// runners do not have, so those tests can only run on a maintainer's machine. This file runs in CI
// (scripts/maintainer_doctor.py gate "mod unit tests") and under the mutation guard
// plugins/rails-flow/scripts/mutations/context_nudge.py, so the module's own logic is able to fail there.
// It drives the hooks the module registers with a hand-built `$` and a `next` that echoes its argument.
// It does NOT exercise the real engine: that the engine calls these hooks, with these event shapes, is
// what the .test.ts file and `claude plugin validate` check, locally.
//
// Run: node plugins/rails-flow/tests/context-nudge.unit.mjs

import assert from 'node:assert/strict'

const failures = []
let checks = 0
let inFlight = '' // the check running right now, named if it never settles
let fresh = 0
const reset = await import('../hooks/session-reset.mjs')

// Report from an 'exit' handler registered BEFORE the first await (so it exists when a check never settles): a check that never settles ends the process (exit
// code 13, an unsettled top-level await) before any line below would run, and the failures would vanish.
process.on('exit', (code) => {
  if (inFlight !== '') failures.push(`${inFlight}: never settled (an await that never resolves), so nothing after it ran`)
  if (failures.length === 0 && code === 0) {
    console.log(`context-nudge unit: ${checks} checks passed`)
    return
  }
  const ended = code === 0 ? '' : `; the process had already ended with exit code ${code}`
  console.error(`context-nudge unit FAILED -- ${failures.length} failed, ${checks} started${ended}:`)
  for (const f of failures) console.error(`  - ${f}`)
  process.exitCode = 1
})

// A new copy of the module each time: it keeps its state in module variables, as a mod does.
async function harness(env) {
  reset.state.role = 'implementation'
  reset.state.line = null
  const mod = await import(`../hooks/context-nudge.mjs?fresh=${++fresh}`)
  const hooks = {}
  mod.register((event, ...rest) => {
    hooks[event] = rest[rest.length - 1]
  })
  const status = []
  const $ = { env: { get: async (k) => env }, ui: { status: (t) => status.push(t) } }
  const echo = async (e) => e
  await hooks['prompt.submit']($, { text: 'prime' }, echo) // the one role line, so the checks below see only their own
  return {
    mod,
    status,
    measure: (percent) =>
      hooks['session.measure'](
        $,
        {
          context: { window: 200000, ...(percent === undefined ? {} : { tokens: percent * 2000, percent }) },
          rateLimits: [],
          changed: ['context'],
        },
        echo,
      ),
    submit: (text, origin) => hooks['prompt.submit']($, { text, ...(origin ? { origin } : {}) }, echo),
  }
}

async function check(label, fn) {
  checks += 1
  inFlight = label
  try {
    await fn()
  } catch (err) {
    failures.push(`${label}: ${String(err.message).split('\n')[0]}`)
  }
  inFlight = ''
}

await check('the fill is pinned under the prompt, and cleared when the window has no reading', async () => {
  const h = await harness(undefined)
  await h.measure(42)
  await h.measure(undefined)
  assert.deepEqual(h.status, ['context 42%', undefined])
})

await check('below the threshold a prompt carries no added context', async () => {
  const h = await harness(undefined)
  await h.measure(69)
  const r = await h.submit('next step')
  assert.deepEqual(r.context ?? [], [])
  assert.equal(r.text, 'next step')
})

await check('at the threshold one line is added, once, and the prompt text is untouched', async () => {
  const h = await harness(undefined)
  await h.measure(74)
  const first = await h.submit('next step')
  assert.equal(first.text, 'next step')
  assert.equal(first.context.length, 1)
  assert.ok(first.context[0].includes('74% full'))
  assert.ok(first.context[0].includes('/rails-flow:handoff'))
  await h.measure(81)
  const second = await h.submit('and again')
  assert.deepEqual(second.context ?? [], [])
})

await check('the line is short, because it is billed again on every later request', async () => {
  const h = await harness(undefined)
  await h.measure(99)
  const r = await h.submit('x')
  assert.ok(r.context[0].length <= 400, `length ${r.context[0].length}`)
})

await check('a compaction resets it: the next climb past the threshold is told again', async () => {
  const h = await harness(undefined)
  await h.measure(75)
  await h.submit('one')
  await h.measure(undefined)
  await h.measure(72)
  const r = await h.submit('two')
  assert.equal(r.context.length, 1)
})

await check('RAILS_FLOW_CONTEXT_NUDGE_PCT moves the threshold', async () => {
  const h = await harness('40')
  await h.measure(45)
  const r = await h.submit('a')
  assert.equal(r.context.length, 1)
})

// A bad value must fall back to the default, 70: quiet at 69 and told at 80. 69 alone cannot tell a
// fallback from a threshold of 150, which is also quiet there.
for (const bad of ['lots', '150', '0', '-5', '']) {
  await check(`a threshold of ${JSON.stringify(bad)} falls back to the default`, async () => {
    const h = await harness(bad)
    await h.measure(69)
    assert.deepEqual((await h.submit('a')).context ?? [], [])
    await h.measure(80)
    assert.equal((await h.submit('b')).context.length, 1)
  })
}

// Every origin kind in the engine's closed set (PromptOrigin, 2.1.287) except the two that are a person at
// an interactive surface. Each is refused on purpose and must not use the line up for the person's next prompt.
const NOT_A_PERSON = [
  { kind: 'sdk' },
  { kind: 'task-notification' },
  { kind: 'scheduled-trigger' },
  { kind: 'peer' },
  { kind: 'peer-send-message' },
  { kind: 'projects-relay' },
  { kind: 'channel', server: 'slack' },
  { kind: 'coordinator' },
  { kind: 'observer' },
  { kind: 'observer-activity' },
  { kind: 'auto-continuation' },
  { kind: 'unclassified' },
  { kind: 'slack-ping' },
  { kind: 'plugin', name: 'some-plugin' },
]
for (const origin of NOT_A_PERSON) {
  await check(`a prompt from "${origin.kind}" never takes the line, and does not use it up`, async () => {
    const h = await harness(undefined)
    await h.measure(90)
    assert.deepEqual((await h.submit('not typed by a person', origin)).context ?? [], [])
    const theirs = await h.submit('typed', { kind: 'composer' })
    assert.equal(theirs.context.length, 1)
  })
}

await check('a Remote Control prompt counts as the person', async () => {
  const h = await harness(undefined)
  await h.measure(90)
  const r = await h.submit('from a phone', { kind: 'bridge' })
  assert.equal(r.context.length, 1)
})
