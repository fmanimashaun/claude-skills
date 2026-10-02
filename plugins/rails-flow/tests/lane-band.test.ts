import { expect, mock, test } from 'claude-code/testing'

// What Claude Code passes to a ui.render hook for the band, apart from the app
const BAND = {
  plugin: 'rails-flow',
  component: 'AbovePrompt',
  requestId: 'band',
  viewport: { columns: 100, rows: 30 },
  props: { hasSurvey: false, isWorking: false, maxRows: 3, bodyColumns: 100, scroll: { offset: 0, bodyRows: 3 }, view: {} },
} as const

// Answer each git call from a table keyed by its arguments; anything else exits 1
function stubGit(on, answers: Record<string, string | null>) {
  on('process.run', ($, e) => {
    const out = answers[e.argv.slice(1).join(' ')]
    return { value: { exitCode: out === null || out === undefined ? 1 : 0, stdout: out ?? '', stderr: '' } }
  })
}

// The band refreshes on a zero-delay timer, so the test advances the mock clock after the turn.
async function completeTurn($, clock) {
  await $.turn.complete({ turnId: 't', answer: '', durationMs: 1, isAborted: false, usage: null })
  await clock.advance(0)
}

test('the band shows branch, worktree, lane and dirty count', async ($, on) => {
  const clock = mock.clock(on)
  stubGit(on, {
    'rev-parse --show-toplevel': '/work/lane-band-1537',
    'branch --show-current': 'feature/1537-lane-band',
    '--no-optional-locks status --porcelain': ' M a.rb\n?? b.rb',
  })
  on('env.get', () => ({ value: 'app/models' }))
  on('turn.complete', () => ({ text: '' }))
  on('ui.render', () => ({ type: 'Text', props: {}, children: ['drawn by Claude Code'] }))

  await completeTurn($, clock)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(
    await ui.find({ type: 'Text', text: 'feature/1537-lane-band · lane-band-1537 · lane app/models · 2 uncommitted' }),
  ).toBeDefined()
})

test('a clean tree with no lane says clean and omits the lane', async ($, on) => {
  const clock = mock.clock(on)
  stubGit(on, {
    'rev-parse --show-toplevel': '/work/repo',
    'branch --show-current': 'dev',
    '--no-optional-locks status --porcelain': '',
  })
  on('env.get', () => ({ value: undefined }))
  on('turn.complete', () => ({ text: '' }))
  on('ui.render', () => ({ type: 'Text', props: {}, children: ['drawn by Claude Code'] }))

  await completeTurn($, clock)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await ui.find({ type: 'Text', text: 'dev · repo · clean' })).toBeDefined()
})

test('outside a git repository the band draws nothing of its own', async ($, on) => {
  const clock = mock.clock(on)
  stubGit(on, {})
  on('env.get', () => ({ value: undefined }))
  on('turn.complete', () => ({ text: '' }))
  on('ui.render', () => ({ type: 'Text', props: {}, children: ['drawn by Claude Code'] }))

  await completeTurn($, clock)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await ui.find({ type: 'Text', text: /·/ })).toBeUndefined()
  expect(await ui.find({ type: 'Text', text: 'drawn by Claude Code' })).toBeDefined()
})

test('the turn still completes unchanged and git is only read', async ($, on) => {
  const argvs: string[] = []
  on('process.run', ($, e) => {
    argvs.push(e.argv.join(' '))
    return { value: { exitCode: 0, stdout: 'x', stderr: '' } }
  })
  on('env.get', () => ({ value: undefined }))
  on('turn.complete', () => ({ text: 'unchanged' }))

  const clock = mock.clock(on)
  const result = await $.turn.complete({ turnId: 't', answer: '', durationMs: 1, isAborted: false, usage: null })
  // The hook returned before any git ran: the refresh waits on the zero-delay timer
  expect(argvs).toEqual([])
  expect(result).toEqual({ text: 'unchanged' })
  await clock.advance(0)
  // The status call carries the flag; without this the loop below could pass on an empty list
  expect(argvs).toContain('git --no-optional-locks status --porcelain')
  // Only these read-only git verbs may ever be run by the mod
  for (const a of argvs) expect(a).toMatch(/^git (rev-parse --show-toplevel|branch --show-current|--no-optional-locks status --porcelain)$/)
})
