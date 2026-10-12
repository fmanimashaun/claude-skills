import { expect, test } from 'claude-code/testing'

// What the engine measures after a turn: the live window and, once a response has reported one, its fill
const measure = (percent: number | undefined) => ({
  context: { window: 200000, ...(percent === undefined ? {} : { tokens: percent * 2000, percent }) },
  rateLimits: [],
  changed: ['context' as const],
})

// Core of prompt.submit: the text and the context that reached the bottom, so a test reads what was attached
function core(on) {
  on('prompt.submit', (_$, e) => ({ text: e.text, context: e.context }))
  on('session.measure', (_$, e) => ({ changed: e.changed }))
}

// Record every line the mod pins under the prompt
function recordStatus(on): (string | undefined)[] {
  const seen: (string | undefined)[] = []
  on('ui.status', (_$, e) => {
    seen.push(e.text)
    return { value: undefined }
  })
  return seen
}

// The lines a prompt carries besides the one role line the first person prompt of a session adds (#1724)
const only = (r: { context?: string[] }) => (r.context ?? []).filter((l) => !l.startsWith('rails-flow role'))

function noEnv(on) {
  on('env.get', () => ({ value: undefined }))
}

test('the fill is pinned under the prompt, and cleared when the window has no reading', async ($, on) => {
  core(on)
  noEnv(on)
  const status = recordStatus(on)
  await $.session.measure(measure(42))
  await $.session.measure(measure(undefined))
  expect(status).toEqual(['context 42%', undefined])
})

test('below the threshold a prompt carries no added context', async ($, on) => {
  core(on)
  noEnv(on)
  recordStatus(on)
  await $.session.measure(measure(69))
  const r = await $.prompt.submit({ text: 'next step' })
  expect(only(r)).toEqual([])
  expect(r.text).toBe('next step')
})

test('at the threshold one line is added, once, and the prompt text is untouched', async ($, on) => {
  core(on)
  noEnv(on)
  recordStatus(on)
  await $.session.measure(measure(74))
  const first = await $.prompt.submit({ text: 'next step' })
  expect(first.text).toBe('next step')
  // The first prompt of a session also carries the one role line (#1724); the nudge is the other.
  const lines = only(first)
  expect(lines).toHaveLength(1)
  expect(lines[0]).toContain('74% full')
  expect(lines[0]).toContain('/rails-flow:handoff')
  await $.session.measure(measure(81))
  const second = await $.prompt.submit({ text: 'and again' })
  expect(only(second)).toEqual([])
})

test('the line is short, because it is billed again on every later request', async ($, on) => {
  core(on)
  noEnv(on)
  recordStatus(on)
  await $.session.measure(measure(99))
  const r = await $.prompt.submit({ text: 'x' })
  for (const line of only(r)) expect(line.length).toBeLessThanOrEqual(400)
})

test('a compaction resets it: the next climb past the threshold is told again', async ($, on) => {
  core(on)
  noEnv(on)
  recordStatus(on)
  await $.session.measure(measure(75))
  await $.prompt.submit({ text: 'one' })
  await $.session.measure(measure(undefined))
  await $.session.measure(measure(72))
  const r = await $.prompt.submit({ text: 'two' })
  expect(only(r)).toHaveLength(1)
})

test('RAILS_FLOW_CONTEXT_NUDGE_PCT moves the threshold; a bad value keeps the default', async ($, on) => {
  core(on)
  recordStatus(on)
  on('env.get', () => ({ value: '40' }))
  await $.session.measure(measure(45))
  const lowered = await $.prompt.submit({ text: 'a' })
  expect(only(lowered)).toHaveLength(1)
})

test('a bad threshold value falls back to the default', async ($, on) => {
  core(on)
  recordStatus(on)
  on('env.get', () => ({ value: 'lots' }))
  await $.session.measure(measure(69))
  const below = await $.prompt.submit({ text: 'a' })
  expect(only(below)).toEqual([])
})

test("a peer session's message or an SDK turn never takes the line, and does not use it up", async ($, on) => {
  core(on)
  noEnv(on)
  recordStatus(on)
  await $.session.measure(measure(90))
  const peer = await $.prompt.submit({ text: 'from a peer', origin: { kind: 'peer' } })
  expect(only(peer)).toEqual([])
  const sdk = await $.prompt.submit({ text: 'from claude -p', origin: { kind: 'sdk' } })
  expect(only(sdk)).toEqual([])
  const theirs = await $.prompt.submit({ text: 'typed', origin: { kind: 'composer' } })
  expect(only(theirs)).toHaveLength(1)
})
