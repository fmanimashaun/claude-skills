// Unit tests for hooks/session-reset.mjs and the mid-job compaction in hooks/context-nudge.mjs
// (#1687 the job-done clear, #1723 the mid-job compact, #1724 the role election), against a fake host, run by
// plain Node. Run by scripts/check_mods.py and the mutation guard plugins/rails-flow/scripts/mutations/session_reset.py.
//
// The election runs its REAL POSIX sh script, against a throwaway HOME: each simulated session is a long-lived
// `sh` whose children see it as $PPID, as the engine's process is to the shell `$.process.run` starts
// (measured under `claude -p` 2.1.293). What is NOT exercised: the engine itself. That `$.command.run` queues a
// clear, and that session.start does not fire on /clear, rest on the declaration excerpts in
// docs/evidence/audits/2026-10-09-mods-command-run-clear-2.1.292.md and on `claude plugin validate`, locally.
//
// Run: node plugins/rails-flow/tests/session-reset.unit.mjs

import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const failures = []
let checks = 0
let fresh = 0
const cleanups = []
process.on('exit', (code) => {
  for (const c of cleanups) c()
  if (failures.length === 0 && code === 0) return console.log(`session-reset unit: ${checks} checks passed`)
  console.error(`session-reset unit FAILED -- ${failures.length} failed of ${checks}:`)
  for (const f of failures) console.error(`  - ${f}`)
  process.exitCode = 1
})
async function check(name, body) {
  checks++
  if (process.env.UNIT_VERBOSE) console.error(`check: ${name}`)
  try {
    await body()
  } catch (err) {
    failures.push(`${name}: ${String(err.message).split('\n')[0]}`)
  }
}
const flush = () => new Promise((r) => setTimeout(r, 5))

const reset = await import('../hooks/session-reset.mjs') // the one instance context-nudge also imports

// A simulated session process: a long-lived sh. What it runs has it as $PPID.
class Proc {
  constructor(home) {
    this.sh = spawn('sh', [], { env: { ...process.env, HOME: home, ELECT: reset.ELECT_SCRIPT }, stdio: ['pipe', 'pipe', 'ignore'] })
    this.buf = ''
    this.sh.stdout.on('data', (d) => (this.buf += d))
    cleanups.push(() => this.kill())
  }
  get pid() { return this.sh.pid }
  kill() { try { this.sh.kill('SIGKILL') } catch { /* gone */ } }
  // Run the election script as this process's child; resolve with its stdout.
  run(argv) {
    const tag = `__DONE_${++fresh}__`
    this.sh.stdin.write(`sh -c "$ELECT" sh '${argv[4]}' '${argv[5]}'; echo ${tag}\n`)
    return new Promise((resolve) => {
      const t = setInterval(() => {
        if (this.buf.includes(tag)) {
          clearInterval(t)
          const out = this.buf.slice(0, this.buf.indexOf(tag))
          this.buf = this.buf.slice(this.buf.indexOf(tag) + tag.length)
          resolve(out)
        }
      }, 10)
    })
  }
}
const home = () => {
  const h = mkdtempSync(join(tmpdir(), 'rf-elect-'))
  cleanups.push(() => rmSync(h, { recursive: true, force: true }))
  return h
}

// One session: both modules registered onto one hook table, a recording host.
//   role: pre-set role (null = leave to the election); proc: the process that runs the election script
async function session({ env = {}, role = 'implementation', gh = {}, surfaces = ['terminal'], compactRejects = 0, proc = null, sid = 's1' } = {}) {
  reset.resetJob()
  reset.state.role = role
  reset.state.coordinator = null
  reset.state.line = null
  const hooks = {}
  const add = (event, ...rest) => {
    hooks[rest.length > 1 ? `${event}:${JSON.stringify(rest[0])}` : event] = rest[rest.length - 1]
  }
  reset.register(add)
  const nudge = await import(`../hooks/context-nudge.mjs?fresh=${++fresh}`)
  nudge.register(add)
  const calls = { clear: 0, compact: [], submitted: [], gh: [] }
  const timers = []
  let rejects = compactRejects
  const $ = {
    env: { get: async (k) => env[k] },
    ui: { status() {} },
    clock: { now: async () => 0, after: (ms, fn) => { timers.push(fn); return { cancel() {} } } },
    session: {
      id: async () => sid,
      surfaces: async () => surfaces,
      compact: async (a) => {
        if (rejects-- > 0) throw new Error('a turn is running')
        calls.compact.push(a.instructions)
        return {}
      },
    },
    command: { run: async ({ command }) => { if (command === 'clear') calls.clear++; return { text: '' } } },
    prompt: { submit: async (p) => { calls.submitted.push(p.text) } },
    process: {
      run: async (argv) => {
        if (argv[0] === 'sh') return { exitCode: 0, stdout: await proc.run(argv) }
        calls.gh.push(argv.join(' '))
        await flush() // gh answers on a later macrotask, so a reset that ran inside the hook would clear before the timer fires
        const n = argv[3]
        return gh[n] ? { exitCode: 0, stdout: JSON.stringify(gh[n]) } : { exitCode: 1, stdout: '' }
      },
    },
  }
  const bash = (command, text, extra = {}) => hooks['tool.call:{"tool":"Bash"}']($, { tool: 'Bash', command, ...extra }, async () => ({ text }))
  const write = (file_path) => hooks['tool.call:{"tool":["Write","Edit"]}']($, { tool: 'Write', file_path }, async () => ({ result: {} }))
  const turnDone = () => hooks['turn.complete']($, { answer: '', durationMs: 1, isAborted: false, turnId: 't', reason: 'answer' }, async (e) => e)
  const start = () => hooks['session.start:{"isInteractive":true}']($, { cwd: '/x', surface: 'terminal', isInteractive: true }, async (e) => e)
  const measure = (ctx, week, five) =>
    hooks['session.measure'](
      $,
      {
        context: { window: 200000, ...(ctx === undefined ? {} : { percent: ctx, tokens: ctx * 2000 }) },
        rateLimits: [
          ...(week === undefined ? [] : [{ kind: 'seven_day', percentUsed: week, resetsAt: '2026-10-10T00:00:00Z' }]),
          ...(five === undefined ? [] : [{ kind: 'five_hour', percentUsed: five, resetsAt: '2026-10-10T00:00:00Z' }]),
        ],
        changed: ['context'],
      },
      async (e) => e,
    )
  const submit = (origin) => hooks['prompt.submit']($, { text: 'hi', ...(origin ? { origin } : {}) }, async (e) => e)
  const run = async () => { while (timers.length) timers.shift()(); await flush() }
  return { calls, bash, write, turnDone, start, measure, submit, run, hooks }
}

const MERGED = { 7: { state: 'MERGED', baseRefName: 'dev' } }
// A whole finished job: worktree added, PR opened, handoff written, worktree removed (gh says the PR is merged).
async function finishJob(s) {
  await s.bash('git worktree add -b feature/x /tmp/wt-x origin/dev', '')
  await s.bash('gh pr create --base dev', 'https://github.com/o/r/pull/7')
  await s.write('/tmp/wt-x/HANDOFF.md')
  await s.bash('git worktree remove /tmp/wt-x', '')
}

// ---- parsers ---------------------------------------------------------------------------------------

await check('parsers read the worktree, the pull request and the handoff', () => {
  assert.deepEqual(reset.parseWorktreeAdd('git worktree add -b feature/x "/tmp/a b" origin/dev'), { path: '/tmp/a b', branch: 'feature/x' })
  assert.equal(reset.parseWorktreeRemove('cd x && git worktree remove --force /tmp/y; true'), '/tmp/y')
  assert.equal(reset.parseWorktreeRemove('git worktree list'), null)
  assert.equal(reset.createdPr('gh pr create --base dev', 'https://github.com/o/r/pull/12\n'), 12)
  assert.equal(reset.createdPr('gh pr view 12', 'https://github.com/o/r/pull/12'), null)
  assert.equal(reset.handoffFile('Write', '/a/HANDOFF.md'), '/a/HANDOFF.md')
  assert.equal(reset.handoffFile('Write', '/a/notes.md'), null)
  assert.equal(reset.handoffFile('Read', '/a/HANDOFF.md'), null)
  assert.ok(reset.handoffComment('gh pr comment 7 --body "handoff: next step"'))
  assert.equal(reset.roleOf('coordinator'), 'coordinator')
  assert.equal(reset.roleOf('Implementation'), null)
  assert.equal(reset.roleOf(undefined), null)
})

// ---- #1687: the job-done clear ---------------------------------------------------------------------

await check('job done: the session clears exactly once, then submits one prompt naming the handoff', async () => {
  const s = await session({ gh: MERGED })
  await finishJob(s)
  await s.turnDone()
  await s.run()
  assert.equal(s.calls.clear, 1)
  assert.deepEqual(s.calls.submitted, [reset.resetPrompt('/tmp/wt-x/HANDOFF.md')])
  assert.ok(s.calls.submitted[0].includes('/tmp/wt-x/HANDOFF.md') && s.calls.submitted[0].includes('wait for the coordinator'))
  await s.turnDone()
  await s.run()
  assert.equal(s.calls.clear, 1, 'later turns of the cleared session do not clear again')
  assert.equal(s.calls.compact.length, 0, 'a finished job is cleared, never compacted')
})

await check('the clear is requested from a timer, not inside the awaited hook', async () => {
  const s = await session({ gh: MERGED })
  await finishJob(s)
  await s.turnDone()
  await new Promise((r) => setTimeout(r, 40))
  assert.equal(s.calls.clear, 0, 'nothing ran inside turn.complete: only the timer clears')
  await s.run()
  assert.equal(s.calls.clear, 1)
})

await check('never mid-job: a live worktree, an unmerged PR, a PR merged elsewhere, an unreadable PR, no handoff, no PR each block the clear', async () => {
  let s = await session({ gh: MERGED })
  await s.bash('git worktree add -b a /tmp/a origin/dev', '')
  await s.bash('git worktree add -b b /tmp/b origin/dev', '')
  await s.bash('gh pr create', 'https://github.com/o/r/pull/7')
  await s.write('/tmp/a/HANDOFF.md')
  await s.bash('git worktree remove /tmp/a', '')
  await s.turnDone(); await s.run()
  assert.equal(s.calls.clear, 0, 'a second live worktree')
  s = await session({ gh: { 7: { state: 'OPEN', baseRefName: 'dev' } } })
  await finishJob(s); await s.turnDone(); await s.run()
  assert.equal(s.calls.clear, 0, 'an open PR')
  s = await session({ gh: { 7: { state: 'MERGED', baseRefName: 'main' } } })
  await finishJob(s); await s.turnDone(); await s.run()
  assert.equal(s.calls.clear, 0, 'a PR merged somewhere else')
  s = await session({ gh: {} })
  await finishJob(s); await s.turnDone(); await s.run()
  assert.equal(s.calls.clear, 0, 'an unreadable PR')
  s = await session({ gh: MERGED })
  await s.bash('git worktree add -b a /tmp/a origin/dev', '')
  await s.bash('gh pr create', 'https://github.com/o/r/pull/7')
  await s.bash('git worktree remove /tmp/a', '')
  await s.turnDone(); await s.run()
  assert.equal(s.calls.clear, 0, 'no handoff')
  s = await session({ gh: MERGED })
  await s.bash('git worktree add -b a /tmp/a origin/dev', '')
  await s.write('/tmp/a/HANDOFF.md')
  await s.bash('git worktree remove /tmp/a', '')
  await s.turnDone(); await s.run()
  assert.equal(s.calls.clear, 0, 'no PR recorded')
})

await check('a Bash call that errors or is denied records nothing', async () => {
  reset.resetJob()
  const hooks = {}
  reset.register((event, ...rest) => { hooks[rest.length > 1 ? `${event}:${JSON.stringify(rest[0])}` : event] = rest[rest.length - 1] })
  const call = hooks['tool.call:{"tool":"Bash"}']
  const add = { tool: 'Bash', command: 'git worktree add -b a /tmp/a origin/dev' }
  await call({}, add, async () => ({ isError: true, text: '' }))
  await call({}, add, async () => ({ deny: 'no' }))
  assert.equal(reset.job.worktrees.size, 0)
  await call({}, add, async () => ({ text: '' }))
  await call({}, { tool: 'Bash', command: 'git worktree remove /tmp/a' }, async () => ({ isError: true, text: '' }))
  assert.equal(reset.job.worktrees.size, 1)
  assert.equal(reset.job.removed, false)
})

await check('a background job started this job blocks the clear', async () => {
  const s = await session({ gh: MERGED })
  await s.bash('bin/ci', '', { run_in_background: true })
  await finishJob(s); await s.turnDone(); await s.run()
  assert.equal(s.calls.clear, 0)
})

await check('claude -p (no surface) never clears', async () => {
  const s = await session({ gh: MERGED, surfaces: [] })
  await finishJob(s); await s.turnDone(); await s.run()
  assert.equal(s.calls.clear, 0)
})

await check('only an implementation session clears: the coordinator and a role-less session never do', async () => {
  for (const role of ['coordinator', null]) {
    const s = await session({ role, gh: MERGED })
    await finishJob(s); await s.turnDone(); await s.run()
    assert.equal(s.calls.clear, 0, `role ${role}`)
  }
})

await check('a cleared session that starts its next job and finishes it clears again', async () => {
  const s = await session({ gh: MERGED })
  await finishJob(s); await s.turnDone(); await s.run()
  assert.equal(s.calls.clear, 1)
  await s.bash('git worktree add -b feature/y /tmp/wt-y origin/dev', '')
  await s.bash('gh pr create', 'https://github.com/o/r/pull/7')
  await s.write('/tmp/wt-y/HANDOFF.md')
  await s.bash('git worktree remove /tmp/wt-y', '')
  await s.turnDone(); await s.run()
  assert.equal(s.calls.clear, 2)
})

// ---- #1723: the mid-job compact --------------------------------------------------------------------

await check('mid-job at the context threshold: an implementation session compacts, keeps its worktree, never clears', async () => {
  const s = await session({ gh: MERGED })
  await s.bash('git worktree add -b feature/x /tmp/wt-x origin/dev', '')
  await s.bash('gh pr create', 'https://github.com/o/r/pull/7')
  await s.write('/tmp/wt-x/HANDOFF.md')
  await s.measure(80)
  await s.run()
  assert.equal(s.calls.compact.length, 0, 'not before the nudge reached the model')
  await s.submit()
  await s.measure(80)
  await s.run()
  assert.equal(s.calls.compact.length, 1)
  assert.equal(s.calls.clear, 0)
  for (const k of ['/tmp/wt-x/HANDOFF.md', '/tmp/wt-x', 'feature/x', '#7', 'Do not remove any worktree']) assert.ok(s.calls.compact[0].includes(k), `keeps ${k}`)
  assert.ok(reset.job.worktrees.has('/tmp/wt-x'), 'the worktree is untouched')
  await s.measure(82); await s.run()
  assert.equal(s.calls.compact.length, 1, 'once per climb')
  await s.measure(undefined); await s.measure(80); await s.submit(); await s.measure(80); await s.run()
  assert.equal(s.calls.compact.length, 2, 'the next climb compacts again')
})

await check('a compaction that is rejected (a turn is running) is tried again at the next measure', async () => {
  const s = await session({ compactRejects: 1 })
  await s.measure(80); await s.submit(); await s.measure(80); await s.run()
  assert.equal(s.calls.compact.length, 0)
  await s.measure(81); await s.run()
  assert.equal(s.calls.compact.length, 1)
})

await check('RAILS_FLOW_COMPACT_PCT moves the compact threshold', async () => {
  const s = await session({ env: { RAILS_FLOW_COMPACT_PCT: '90' } })
  await s.measure(80); await s.submit(); await s.measure(80); await s.run()
  assert.equal(s.calls.compact.length, 0)
  await s.measure(91); await s.run()
  assert.equal(s.calls.compact.length, 1)
})

await check('the coordinator compacts at the threshold with its handoff path, queue and open PRs kept, and never clears', async () => {
  const s = await session({ role: 'coordinator' })
  await s.measure(80); await s.run()
  assert.equal(s.calls.compact.length, 1)
  assert.equal(s.calls.clear, 0)
  assert.ok(s.calls.compact[0].includes(reset.DEFAULT_COORDINATOR_HANDOFF) && /queue/.test(s.calls.compact[0]) && /open pull requests/.test(s.calls.compact[0]))
  const t = await session({ role: 'coordinator', env: { RAILS_FLOW_COORDINATOR_HANDOFF: '/x/H.md' } })
  await t.measure(80); await t.run()
  assert.ok(t.calls.compact[0].includes('/x/H.md'))
})

await check('below the threshold nothing compacts', async () => {
  const s = await session({ role: 'coordinator' })
  await s.measure(60); await s.run()
  assert.equal(s.calls.compact.length, 0)
})

await check('a usage window at warn compacts mid-job once its line has reached the model; budget-guard still asks for the handoff', async () => {
  for (const [week, five] of [[85, undefined], [undefined, 85]]) {
    const s = await session()
    await s.bash('git worktree add -b feature/x /tmp/wt-x origin/dev', '')
    await s.measure(10, week, five); await s.run()
    assert.equal(s.calls.compact.length, 0, 'the line has not reached the model yet')
    const r = await s.submit()
    assert.ok(r.context.some((l) => l.startsWith('Usage note')), 'budget-guard still asks for the handoff')
    await s.measure(10, week, five); await s.run()
    assert.equal(s.calls.compact.length, 1)
    assert.equal(s.calls.clear, 0)
    await s.measure(10, week, five); await s.run()
    assert.equal(s.calls.compact.length, 1, 'once while the window stays at warn')
  }
})

await check('the 5-hour hard level still schedules its resume, beside the compaction', async () => {
  const s = await session()
  await s.measure(10, undefined, 95); await s.run()
  assert.ok(s.calls.submitted.some((t) => t.startsWith('The 5-hour usage limit has reset')))
})

await check('a session whose job is done is not compacted: the clear takes over', async () => {
  const s = await session({ gh: MERGED })
  await finishJob(s)
  await s.measure(90); await s.submit(); await s.measure(90); await s.run()
  assert.equal(s.calls.compact.length, 0)
})

await check('claude -p (no surface) and a role-less session never compact', async () => {
  let s = await session({ surfaces: [], role: 'coordinator' })
  await s.measure(95); await s.run()
  assert.equal(s.calls.compact.length, 0)
  s = await session({ role: null })
  await s.measure(99, 95, 95); await s.submit(); await s.measure(99, 95, 95); await s.run()
  assert.equal(s.calls.compact.length, 0)
})

// ---- #1724: the role election ----------------------------------------------------------------------

await check('the first session is elected coordinator, the second implementation, and it is told who', async () => {
  const h = home()
  const a = new Proc(h)
  const b = new Proc(h)
  const sa = await session({ role: null, proc: a, sid: 'sess-a' })
  await sa.start()
  assert.equal(reset.state.role, 'coordinator')
  const lineA = (await sa.submit()).context[0]
  assert.ok(lineA.includes('elected coordinator'))
  const sb = await session({ role: null, proc: b, sid: 'sess-b' })
  await sb.start()
  assert.equal(reset.state.role, 'implementation')
  assert.ok(reset.state.coordinator.includes('sess-a') && reset.state.coordinator.includes(String(a.pid)))
  const lineB = (await sb.submit()).context[0]
  assert.ok(lineB.includes('implementation session') && lineB.includes('sess-a'))
  assert.equal((await sb.submit()).context, undefined, 'told once')
})

await check('two simultaneous starts elect exactly one coordinator', async () => {
  for (let round = 0; round < 5; round++) {
    const h = home()
    const procs = [new Proc(h), new Proc(h), new Proc(h)]
    const outs = await Promise.all(procs.map((p, i) => p.run(['sh', '-c', '', 'sh', `s${i}`, '0'])))
    const roles = outs.map((o) => reset.parseElection(o)?.role)
    assert.equal(roles.filter((r) => r === 'coordinator').length, 1, `round ${round}: ${roles}`)
    assert.equal(roles.filter((r) => r === 'implementation').length, 2)
  }
})

await check('a stale claim (its process is gone) is taken over, and the takeover is single too', async () => {
  const h = home()
  const dead = new Proc(h)
  assert.equal(reset.parseElection(await dead.run(['sh', '-c', '', 'sh', 'old', '0'])).role, 'coordinator')
  dead.kill()
  await new Promise((r) => setTimeout(r, 100))
  const procs = [new Proc(h), new Proc(h)]
  const outs = await Promise.all(procs.map((p, i) => p.run(['sh', '-c', '', 'sh', `n${i}`, '0'])))
  const roles = outs.map((o) => reset.parseElection(o)?.role).sort()
  assert.deepEqual(roles, ['coordinator', 'implementation'])
})

await check('a live coordinator is not displaced by a later start', async () => {
  const h = home()
  const a = new Proc(h)
  await a.run(['sh', '-c', '', 'sh', 'a', '0'])
  for (let i = 0; i < 3; i++) assert.equal(reset.parseElection(await new Proc(h).run(['sh', '-c', '', 'sh', `x${i}`, '0'])).role, 'implementation')
  assert.equal(reset.parseElection(await a.run(['sh', '-c', '', 'sh', 'a', '0'])).role, 'coordinator', 'the same process asking again keeps it')
})

await check('a claim whose pid is recycled by another process is stale (start time differs)', async () => {
  const h = home()
  const a = new Proc(h)
  await a.run(['sh', '-c', '', 'sh', 'a', '0'])
  // overwrite the recorded start time so the live pid no longer matches
  const claim = join(h, '.claude/rails-flow/coordinator/claim')
  const { readFileSync, writeFileSync } = await import('node:fs')
  const lines = readFileSync(claim, 'utf8').split('\n')
  lines[3] = 'Mon Jan  1 00:00:00 2001'
  writeFileSync(claim, lines.join('\n'))
  assert.equal(reset.parseElection(await new Proc(h).run(['sh', '-c', '', 'sh', 'b', '0'])).role, 'coordinator')
})

await check('the role survives a clear: the process goes on and session.start does not fire again', async () => {
  const h = home()
  const a = new Proc(h)
  const s = await session({ role: null, proc: a, sid: 'before-clear' })
  await s.start()
  assert.equal(reset.state.role, 'coordinator')
  // a /clear gives the process a new session id and fires no session.start: nothing here may reset the role
  await s.turnDone(); await s.measure(10); await s.submit()
  assert.equal(reset.state.role, 'coordinator')
  const impl = await session({ role: null, proc: new Proc(h), sid: 'i1' })
  await impl.start()
  await impl.bash('git worktree add -b a /tmp/a origin/dev', '')
  await impl.bash('git worktree remove /tmp/a', '')
  assert.equal(reset.state.role, 'implementation', 'tool calls and the job bookkeeping leave the role alone')
})

await check('resume: a resumed coordinator in a new process re-takes the stale claim when it starts first', async () => {
  const h = home()
  const before = new Proc(h)
  await before.run(['sh', '-c', '', 'sh', 'old-id', '0'])
  before.kill()
  await new Promise((r) => setTimeout(r, 100))
  const s = await session({ role: null, proc: new Proc(h), sid: 'resumed-id' })
  await s.start()
  assert.equal(reset.state.role, 'coordinator')
})

await check('RAILS_FLOW_ROLE=coordinator takes the claim from a live coordinator (the hand-over)', async () => {
  const h = home()
  const a = new Proc(h)
  await a.run(['sh', '-c', '', 'sh', 'a', '0'])
  const s = await session({ role: null, proc: new Proc(h), sid: 'b', env: { RAILS_FLOW_ROLE: 'coordinator' } })
  await s.start()
  assert.equal(reset.state.role, 'coordinator')
  assert.equal(reset.parseElection(await new Proc(h).run(['sh', '-c', '', 'sh', 'c', '0'])).coordinator.includes('b'), true)
})

await check('RAILS_FLOW_ROLE=implementation never claims, even with no coordinator', async () => {
  const h = home()
  const s = await session({ role: null, proc: new Proc(h), sid: 'b', env: { RAILS_FLOW_ROLE: 'implementation' } })
  await s.start()
  assert.equal(reset.state.role, 'implementation')
  assert.equal(reset.parseElection(await new Proc(h).run(['sh', '-c', '', 'sh', 'c', '0'])).role, 'coordinator')
})

await check('an election that fails leaves no role, and the one line says so', async () => {
  const s = await session({ role: null, proc: { run: async () => 'garbage' } })
  await s.start()
  assert.equal(reset.state.role, null)
  const r = await s.submit()
  assert.ok(r.context[0].includes('could not elect') && r.context[0].includes('RAILS_FLOW_ROLE'))
  assert.equal((await s.submit()).context, undefined)
  const t = await session({ role: null, proc: { run: async () => { throw new Error('no sh') } } })
  await t.start()
  assert.equal(reset.state.role, null)
})

// The simulated session processes keep stdio open; end them so the process can exit and report.
for (const c of cleanups.splice(0)) c()
