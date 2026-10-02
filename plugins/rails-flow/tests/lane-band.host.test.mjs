// Runs hooks/lane-band.js against a fake Claude Code host, with plain Node: no `claude` binary, no
// session. `claude plugin test` covers the same module with the real test kit, but CI does not
// install `claude`, so this file is what the gate sweep can actually run (scripts/check_lane_band.py).
// Exit 0 when every check holds; each failure prints one `FAIL <name>` line and exits 1.
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { pathToFileURL } from 'node:url'

const here = path.dirname(new URL(import.meta.url).pathname)
const source = fs.readFileSync(path.join(here, '..', 'hooks', 'lane-band.js'), 'utf8')
// The module is ESM in a .js file with no package.json "type"; copy it to .mjs so every Node reads it as ESM.
const copy = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'lane-band-')), 'lane-band.mjs')
fs.writeFileSync(copy, source)

const failures = []
let checks = 0
// Print what failed even when the process ends early (a hook that hangs leaves a top-level await
// unsettled and Node exits without reaching the end of this file).
process.on('exit', (code) => {
  if (failures.length) console.log(failures.join('\n') + `\n${failures.length} of ${checks} checks failed`)
  else if (code !== 0) console.log(`host test ended early with exit code ${code} after ${checks} checks`)
})
function check(name, ok, detail = '') {
  checks += 1
  if (!ok) failures.push(`FAIL ${name}${detail ? ': ' + detail : ''}`)
}

// A fake host. `git` maps "arg arg ..." to stdout (null = exit 1, 'THROW' = reject); `lane` is the env value.
function host({ git = {}, lane, runDelay = {}, invalidateThrows = false } = {}) {
  const handlers = []
  const argvs = []
  const timers = []
  const used = new Set()
  const note = (name) => used.add(name)
  const el = (type) => (props) => ({ type, props, children: props.children })
  const $ = {
    process: {
      run: async (argv) => {
        note('process.run')
        argvs.push(argv.join(' '))
        const key = argv.slice(1).join(' ')
        if (runDelay[key]) await runDelay[key]
        const out = git[key]
        if (out === 'THROW') throw new Error('cannot start')
        return { exitCode: out === null || out === undefined ? 1 : 0, stdout: out ?? '', stderr: '' }
      },
    },
    env: { get: async () => (note('env.get'), lane) },
    ui: { invalidate: () => { note('ui.invalidate'); if (invalidateThrows) throw new Error('redraw refused') }, resolve: () => (note('ui.resolve'), { Box: el('Box'), Text: el('Text') }) },
    clock: { every: (ms, fn) => (note('clock.every'), timers.push({ ms, fn })) },
  }
  // Any other namespace or method is a call the module is not documented to make: record it.
  const guarded = new Proxy($, { get: (t, k) => (k in t ? t[k] : (note(`UNEXPECTED ${String(k)}`), undefined)) })
  const on = (event, a, b) => handlers.push({ event, matcher: b ? a : undefined, fn: b ?? a })
  return {
    $: guarded, on, handlers, argvs, timers, used,
    find: (event) => handlers.find((h) => h.event === event),
    runTimers: async () => { while (timers.length) await timers.shift().fn() },
  }
}

const { register } = await import(pathToFileURL(copy).href)
const PASSTHROUGH = (e) => ({ passed: e })
const REPO = {
  'rev-parse --show-toplevel': '/work/lane-band-1537',
  'branch --show-current': 'feature/1537-lane-band',
  '--no-optional-locks status --porcelain': ' M a.rb\n?? b.rb',
}
const textOf = (tree) => JSON.stringify(tree)

// 1. registration: exactly these two hooks, ui.render narrowed to the band
{
  const h = host()
  register(h.on)
  check('registers session.start and ui.render only',
    h.handlers.map((x) => x.event).sort().join() === 'session.start,ui.render', h.handlers.map((x) => x.event).join())
  check('ui.render is limited to AbovePrompt', h.find('ui.render')?.matcher?.component === 'AbovePrompt')
}

// 2. session.start returns next(e) at once, starts the repeating timer, and runs no git until it fires
{
  const h = host({ git: REPO, lane: 'app/models' })
  register(h.on)
  const out = await h.find('session.start').fn(h.$, { cwd: '/x' }, async (e) => PASSTHROUGH(e))
  check('session.start passes the event on unchanged', out?.passed?.cwd === '/x')
  check('session.start runs no git before its timer', h.argvs.length === 0, h.argvs.join(' | '))
  check('session.start starts one 2000 ms repeating timer', h.timers.length === 1 && h.timers[0].ms === 2000, JSON.stringify(h.timers.map((t) => t.ms)))
  await h.runTimers()
  check('the refresh runs exactly the three read-only git calls',
    h.argvs.join(' | ') === 'git rev-parse --show-toplevel | git branch --show-current | git --no-optional-locks status --porcelain',
    h.argvs.join(' | '))
  check('git status takes no optional locks (the flag precedes the subcommand)',
    h.argvs.some((a) => a === 'git --no-optional-locks status --porcelain'))
  check('only documented calls were made', [...h.used].every((u) => !u.startsWith('UNEXPECTED')), [...h.used].join())
  check('the refresh asks for a redraw', h.used.has('ui.invalidate'))
}

// 3. there is no turn.complete hook: the timer is the only trigger, so nothing runs at a turn's end
check('no turn.complete hook is registered', (() => { const h = host(); register(h.on); return !h.find('turn.complete') })())

// 4. the band's text, and that other mods' drawing is kept
{
  const h = host({ git: REPO, lane: 'app/models' })
  register(h.on)
  await h.find('session.start').fn(h.$, {}, async (e) => e)
  await h.runTimers()
  const theirs = { type: 'engine', ref: 1 }
  const tree = await h.find('ui.render').fn(h.$, { component: 'AbovePrompt' }, async () => theirs)
  const s = textOf(tree)
  check('band shows branch, worktree, lane and dirty count',
    s.includes('feature/1537-lane-band · lane-band-1537 · lane app/models · 2 uncommitted'), s)
  check('band keeps what the mods after it draw', s.includes('"type":"engine"'), s)
}
{
  const h = host({ git: { ...REPO, '--no-optional-locks status --porcelain': '' } })
  register(h.on)
  await h.find('session.start').fn(h.$, {}, async (e) => e)
  await h.runTimers()
  const s = textOf(await h.find('ui.render').fn(h.$, {}, async () => null))
  check('a clean tree with no lane says clean and omits the lane', s.includes('feature/1537-lane-band · lane-band-1537 · clean'), s)
}

// 5. outside a repository, with git missing, or when git fails: the band draws nothing of its own
for (const [name, git] of [
  ['outside a git repository', {}],
  ['git cannot start', { 'rev-parse --show-toplevel': 'THROW' }],
]) {
  const h = host({ git })
  register(h.on)
  await h.find('session.start').fn(h.$, {}, async (e) => e)
  await h.runTimers()
  const theirs = { type: 'engine', ref: 2 }
  const tree = await h.find('ui.render').fn(h.$, {}, async () => theirs)
  check(`${name}: the band draws nothing of its own`, tree === theirs)
}

// 5b. a redraw request that throws is caught inside the timer callback, so the host never sees it
{
  const h = host({ git: REPO, invalidateThrows: true })
  register(h.on)
  await h.find('session.start').fn(h.$, {}, async (e) => e)
  let escaped = null
  try {
    await h.runTimers()
  } catch (error) {
    escaped = error
  }
  check('a throwing redraw request does not escape the timer callback', escaped === null, String(escaped))
}

// 6. detached HEAD
{
  const h = host({ git: { ...REPO, 'branch --show-current': '' } })
  register(h.on)
  await h.find('session.start').fn(h.$, {}, async (e) => e)
  await h.runTimers()
  const s = textOf(await h.find('ui.render').fn(h.$, {}, async () => null))
  check('a detached HEAD is named', s.includes('detached HEAD'), s)
}

// 7. a tick that arrives while a refresh is still running is skipped, and ticking resumes afterwards
{
  let release
  const slow = new Promise((r) => (release = r))
  const h = host({ git: REPO, runDelay: { 'rev-parse --show-toplevel': slow } })
  register(h.on)
  await h.find('session.start').fn(h.$, {}, async (e) => e)
  const tick = h.timers[0].fn
  const first = tick() // stuck on the delayed rev-parse
  await new Promise((r) => setTimeout(r, 0))
  const second = tick() // arrives while the first is running; not awaited, so a missing guard cannot hang the test
  await new Promise((r) => setTimeout(r, 0))
  check('an overlapping tick starts no second refresh', h.argvs.length === 1, h.argvs.join(' | '))
  release()
  await first
  await second
  h.argvs.length = 0
  await tick()
  check('ticking resumes once the slow refresh ends', h.argvs.length === 3, h.argvs.join(' | '))
}

fs.rmSync(path.dirname(copy), { recursive: true, force: true })
if (failures.length) process.exit(1)
console.log(`ok: ${checks} checks`)
