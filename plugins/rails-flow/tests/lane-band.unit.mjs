// Unit tests for hooks/lane-band.js against a fake Claude Code host, run by plain Node (#1537).
//
// WHY THIS EXISTS BESIDE lane-band.test.ts: `claude plugin test` needs the `claude` CLI, which the gate
// runners do not have. This file runs in CI (scripts/maintainer_doctor.py gate "mod unit tests", through
// scripts/check_mods.py) and under the mutation guard plugins/rails-flow/scripts/mutations/lane_band.py,
// so the module's own logic is able to fail there. It does NOT exercise the real engine: that the engine
// calls these hooks, with these event shapes, is what the .test.ts file and `claude plugin validate` check,
// locally.
//
// It also holds the checks that keep the band READ-ONLY: only reviewed mods API calls, only the three
// reviewed git calls, and no await of the refresh inside a hook.
//
// Run: node plugins/rails-flow/tests/lane-band.unit.mjs

import fs from 'node:fs'
import path from 'node:path'

const here = path.dirname(new URL(import.meta.url).pathname)
const hooksDir = path.join(here, '..', 'hooks')
const failures = []
let checks = 0
let fresh = 0

// Print what failed even when the process ends early (a hook that hangs leaves a top-level await
// unsettled and Node exits without reaching the end of this file).
process.on('exit', (code) => {
  if (failures.length) console.log(failures.join('\n') + `\n${failures.length} of ${checks} checks failed`)
  else if (code !== 0) console.log(`lane-band unit ended early with exit code ${code} after ${checks} checks`)
})
function check(name, ok, detail = '') {
  checks += 1
  if (!ok) failures.push(`FAIL ${name}${detail ? ': ' + detail : ''}`)
}

// A new copy of the module each time: it keeps its state in module variables, as a mod does.
const load = () => import(`../hooks/lane-band.js?fresh=${++fresh}`)

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
    ui: {
      invalidate: () => {
        note('ui.invalidate')
        if (invalidateThrows) throw new Error('redraw refused')
      },
      resolve: () => (note('ui.resolve'), { Box: el('Box'), Text: el('Text') }),
    },
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

// A host with the module registered and session.start already fired.
async function started(opts) {
  const { register } = await load()
  const h = host(opts)
  register(h.on)
  await h.find('session.start').fn(h.$, {}, async (e) => e)
  return h
}

const PASSTHROUGH = (e) => ({ passed: e })
const REPO = {
  'rev-parse --show-toplevel': '/work/lane-band-1537',
  'branch --show-current': 'feature/1537-lane-band',
  '--no-optional-locks status --porcelain': ' M a.rb\n?? b.rb',
}
const textOf = (tree) => JSON.stringify(tree)

// 1. registration: exactly these two hooks, ui.render narrowed to the band
{
  const { register } = await load()
  const h = host()
  register(h.on)
  check('registers session.start and ui.render only',
    h.handlers.map((x) => x.event).sort().join() === 'session.start,ui.render', h.handlers.map((x) => x.event).join())
  check('ui.render is limited to AbovePrompt', h.find('ui.render')?.matcher?.component === 'AbovePrompt')
  check('no turn.complete hook is registered: the timer is the only trigger', !h.find('turn.complete'))
}

// 2. session.start returns next(e) at once, starts the repeating timer, and runs no git until it fires
{
  const { register } = await load()
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

// 3. the band's text, and that other mods' drawing is kept
{
  const h = await started({ git: REPO, lane: 'app/models' })
  await h.runTimers()
  const theirs = { type: 'engine', ref: 1 }
  const s = textOf(await h.find('ui.render').fn(h.$, { component: 'AbovePrompt' }, async () => theirs))
  check('band shows branch, worktree, lane and dirty count',
    s.includes('feature/1537-lane-band · lane-band-1537 · lane app/models · 2 uncommitted'), s)
  check('band keeps what the mods after it draw', s.includes('"type":"engine"'), s)
}
{
  const h = await started({ git: { ...REPO, '--no-optional-locks status --porcelain': '' } })
  await h.runTimers()
  const s = textOf(await h.find('ui.render').fn(h.$, {}, async () => null))
  check('a clean tree with no lane says clean and omits the lane', s.includes('feature/1537-lane-band · lane-band-1537 · clean'), s)
}

// 4. outside a repository, or when git cannot start: the band draws nothing of its own
for (const [name, git] of [
  ['outside a git repository', {}],
  ['git cannot start', { 'rev-parse --show-toplevel': 'THROW' }],
]) {
  const h = await started({ git })
  await h.runTimers()
  const theirs = { type: 'engine', ref: 2 }
  const tree = await h.find('ui.render').fn(h.$, {}, async () => theirs)
  check(`${name}: the band draws nothing of its own`, tree === theirs)
}

// 5. a redraw request that throws is caught inside the timer callback, so the host never sees it
{
  const h = await started({ git: REPO, invalidateThrows: true })
  let escaped = null
  try {
    await h.runTimers()
  } catch (error) {
    escaped = error
  }
  check('a throwing redraw request does not escape the timer callback', escaped === null, String(escaped))
}

// 6. a detached HEAD is named, not hidden
{
  const h = await started({ git: { ...REPO, 'branch --show-current': '' } })
  await h.runTimers()
  const s = textOf(await h.find('ui.render').fn(h.$, {}, async () => null))
  check('a detached HEAD is named', s.includes('detached HEAD'), s)
}

// 7. a tick that arrives while a refresh is still running is skipped, and ticking resumes afterwards
{
  let release
  const slow = new Promise((r) => (release = r))
  const h = await started({ git: REPO, runDelay: { 'rev-parse --show-toplevel': slow } })
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

// 8. READ-ONLY, from the source: reviewed mods API calls only, the three reviewed git calls, and no
// await of the refresh in a hook (it would delay the first prompt or the end of a turn).
const ALLOWED_CALLS = new Set(['process.run', 'env.get', 'ui.invalidate', 'ui.resolve', 'clock.every'])
const ALLOWED_GIT = new Set(['rev-parse --show-toplevel', 'branch --show-current', '--no-optional-locks status --porcelain'])
function staticFindings(js) {
  const findings = []
  for (const call of new Set([...js.matchAll(/\$\.([a-z]+\.[a-zA-Z]+)\b/g)].map((m) => m[1]))) {
    if (!ALLOWED_CALLS.has(call)) findings.push(`calls $.${call}, which is not in the reviewed read-only set`)
  }
  for (const m of js.matchAll(/\bgit\(\$,\s*\[([^\]]*)\]/g)) {
    const verbs = [...m[1].matchAll(/['"]([^'"]+)['"]/g)].map((x) => x[1]).join(' ')
    if (!ALLOWED_GIT.has(verbs)) findings.push(`runs git ${verbs}, which is not one of the three reviewed read-only calls`)
  }
  // `tick` is the timer callback and the one place that awaits `refresh`; anywhere else an await of
  // either one sits in a hook.
  const outsideTick = js.replace(/async function tick\(\$\) \{[\s\S]*?\n\}/, '')
  if (/\bawait\s+(refresh|tick)\(/.test(outsideTick)) findings.push('awaits refresh() or tick() inside a hook')
  return findings
}
{
  const source = fs.readFileSync(path.join(hooksDir, 'lane-band.js'), 'utf8')
  const found = staticFindings(source)
  check('the source calls only reviewed read-only things', found.length === 0, found.join('; '))

  // The checks above must be able to fail: each fixture breaks exactly one of them.
  const clean =
    "const a = await git($, ['rev-parse', '--show-toplevel'])\n" +
    "const b = await git($, ['branch', '--show-current'])\n" +
    "const c = await git($, ['--no-optional-locks', 'status', '--porcelain'])\n" +
    "$.process.run($.env.get('X'))\n$.ui.invalidate('ui.render')\n$.ui.resolve(e)\n$.clock.every(2000, f)\n" +
    'async function tick($) {\n  try {\n    await refresh($)\n  } catch {}\n}\n'
  check('selftest: the reviewed shape is clean', staticFindings(clean).length === 0)
  check('selftest: a write call is refused', staticFindings(clean + "$.fs.write('a','b')\n").some((f) => f.includes('$.fs.write')))
  check('selftest: a network call is refused', staticFindings(clean + '$.http.fetch(u)\n').some((f) => f.includes('$.http.fetch')))
  check('selftest: a mutating git call is refused', staticFindings(clean + "await git($, ['add', '-A'])\n").some((f) => f.includes('add -A')))
  check('selftest: status without the flag is refused',
    staticFindings(clean.replace("'--no-optional-locks', ", '')).some((f) => f.includes('status --porcelain')))
  check('selftest: an awaited refresh in a hook is refused', staticFindings(clean + 'await refresh($)\n').length > 0)
  check('selftest: an awaited tick in a hook is refused', staticFindings(clean + 'await tick($)\n').length > 0)
}

// 9. wiring: hooks.json names ONE module, register.js, and register.js calls this mod
{
  const hooksJson = JSON.parse(fs.readFileSync(path.join(hooksDir, 'hooks.json'), 'utf8'))
  check('hooks.json names exactly ./register.js', JSON.stringify(hooksJson.modules) === '["./register.js"]', JSON.stringify(hooksJson.modules))
  const registerJs = fs.readFileSync(path.join(hooksDir, 'register.js'), 'utf8')
  check('register.js imports and calls the lane band',
    registerJs.includes("from './lane-band.js'") && /laneBand\(on/.test(registerJs))
}

if (failures.length) process.exit(1)
console.log(`lane-band unit: ${checks} checks`)
