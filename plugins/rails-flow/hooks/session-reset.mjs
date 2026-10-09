// session-reset: a session resets its own context when its job is done, and compacts, never clears,
// while work is still in flight (#1687, related #1564). Owner rules, 2026-10-09: a finished
// implementation session clears itself; a coordinator compacts itself; a session near a limit with work
// in flight compacts and keeps its worktrees. The owner never types /clear.
//
// It is advisory and fails open: every hook returns what `next` gave it, a throw anywhere is swallowed,
// and when it cannot tell what the session is doing it does nothing (an undeclared role, a `claude -p`
// run, an unreadable pull request). A reset that fires in the middle of work is the failure to avoid,
// so each doubt resolves to "no action".
//
// The role is ELECTED at session.start, machine-wide (owner rule, 2026-10-09): the first live session to
// ask becomes the coordinator, every later one is an implementation session, and a claim whose process is
// gone is stale and taken over. RAILS_FLOW_ROLE=coordinator|implementation overrides the election (the
// owner's hand-over). Until a role is known, or if the election fails, the role is null: no action.
// See reference/context-budget.md, "A session resets itself".
//
// API relied on (Claude Code 2.1.292 declaration, the newest available; the CLI here is 2.1.293 and
// 2.1.295 is the version in scope; docs/evidence/audits/2026-10-09-mods-command-run-clear-2.1.292.md):
//   $.command.run({ command })  "Runs a slash command as if the person typed `/command args` ... queued
//                               and run once the session is idle ... Rejects an unknown name, and inside
//                               a hook the turn is waiting on."  So it is called from a $.clock.after
//                               timer, never from the awaited hook itself.
//   $.session.compact({ instructions })  "between turns ... rejects while a turn runs"
//   $.prompt.submit({ text })   "a turn of its own, once the session is idle"
//   $.session.surfaces()        "Empty in a plain -p run"
//   session.start never fires on /clear ("never `/clear`"), so this module's variables survive it.
// The state is not persisted to $.store on purpose: a reload loses it, and a session that lost track of
// its job does nothing.

export const DEFAULT_COMPACT_PCT = 75
export const DEFAULT_COORDINATOR_HANDOFF = '~/projects/claude-skills-wt/_logs/COORDINATOR-HANDOFF.md'

// This session's elected role. Module variables survive a /clear (the process goes on, and session.start does
// not fire again), so the role survives it; a resume is a new process and elects again.
export const state = { role: null, coordinator: null, line: null }

// POSIX sh, run with $1 = this session's id and $2 = "1" to force a claim. $PPID is the engine's own pid
// (measured under `claude -p` 2.1.293: the shell `$.process.run` starts has the claude process as parent).
// The claim is a directory made with mkdir, which is atomic: of two simultaneous starts exactly one makes it.
// A claim is live only while its pid exists AND its process start time matches (a recycled pid after a
// reboot is not the coordinator). A stale claim is replaced under a second mkdir lock, so two takers cannot
// both win; a taker that finds the lock held reports implementation (fewer coordinators, never more).
export const ELECT_SCRIPT = `
d="$HOME/.claude/rails-flow"; c="$d/coordinator"; lk="$d/lock"; me="$PPID"; sid="$1"; force="$2"
mkdir -p "$d" || { echo error; exit 0; }
start() { ps -o lstart= -p "$1" 2>/dev/null | sed 's/^ *//'; }
claim() { mkdir "$c" 2>/dev/null || return 1; printf '%s\\n%s\\n%s\\n%s\\n' "$me" "$sid" "$(date +%s)" "$(start "$me")" > "$c/claim"; }
alive() { [ -n "$1" ] && kill -0 "$1" 2>/dev/null && [ "$(start "$1")" = "$2" ]; }
read_claim() { hp=$(sed -n 1p "$c/claim" 2>/dev/null); hs=$(sed -n 2p "$c/claim" 2>/dev/null); hl=$(sed -n 4p "$c/claim" 2>/dev/null); }
report() { echo "implementation $hp $hs"; exit 0; }
if [ "$force" = "1" ]; then rm -rf "$c"; fi
if claim; then echo coordinator; exit 0; fi
read_claim
if [ -z "$hp" ]; then sleep 1; read_claim; fi
if [ "$hp" = "$me" ] && [ "$hl" = "$(start "$me")" ]; then echo coordinator; exit 0; fi
if alive "$hp" "$hl"; then report; fi
if [ -n "$(find "$lk" -maxdepth 0 -mmin +1 2>/dev/null)" ]; then rmdir "$lk" 2>/dev/null; fi
mkdir "$lk" 2>/dev/null || report
read_claim
if alive "$hp" "$hl"; then rmdir "$lk"; report; fi
rm -rf "$c"
if claim; then rmdir "$lk"; echo coordinator; exit 0; fi
rmdir "$lk"; read_claim; report
`

// What the script printed -> { role, coordinator }, or null when it said nothing usable.
export function parseElection(out) {
  const [role, pid, sid] = String(out ?? '').trim().split(/\s+/)
  if (role === 'coordinator') return { role, coordinator: null }
  if (role === 'implementation') return { role, coordinator: pid ? `session ${sid || 'unknown'} (pid ${pid})` : null }
  return null
}

export function electionLine(r) {
  return r.role === 'coordinator'
    ? 'Role note: this session was elected coordinator (none was live). It compacts itself near a limit and never clears.'
    : `Role note: this session is an implementation session; the coordinator is ${r.coordinator ?? 'another live session'}. ` +
        'It clears itself after its PR is merged into dev and its worktree is removed.'
}

// Elect this session's role. Fails open to null: any error leaves the session with no automatic action.
export async function electRole($) {
  try {
    const forced = roleOf(await $.env.get('RAILS_FLOW_ROLE'))
    if (forced === 'implementation') return { role: forced, coordinator: null }
    const sid = await $.session.id()
    const r = await $.process.run(['sh', '-c', ELECT_SCRIPT, 'sh', String(sid), forced === 'coordinator' ? '1' : '0'], { timeoutMs: 8000 })
    return r.exitCode === 0 ? parseElection(r.stdout) : null
  } catch {
    return null
  }
}

// What this session has done in its current job. Reset after a clear.
export const job = freshJob()
function freshJob() {
  return { worktrees: new Map(), prs: new Set(), handoff: null, removed: false, background: 0, pending: false, cleared: false }
}
export function resetJob() {
  Object.assign(job, freshJob())
}

// --- pure helpers ----------------------------------------------------------------------------------

// Words of a shell command line, quotes stripped. Enough for `git worktree add -b br path`.
function words(cmd) {
  return (String(cmd).match(/"[^"]*"|'[^']*'|\S+/g) ?? []).map((w) => w.replace(/;$/, '').replace(/^["']|["']$/g, ''))
}

// `git worktree add [-b|-B branch] <path> [commit]` -> { path, branch } or null.
export function parseWorktreeAdd(cmd) {
  const w = words(cmd)
  const i = w.findIndex((x, k) => x === 'git' && w[k + 1] === 'worktree' && w[k + 2] === 'add')
  if (i < 0) return null
  let branch = ''
  const rest = []
  for (let k = i + 3; k < w.length; k++) {
    if (/^(;|&&|\|\||\|)$/.test(w[k])) break
    if (w[k] === '-b' || w[k] === '-B') branch = w[++k] ?? ''
    else if (!w[k].startsWith('-')) rest.push(w[k])
  }
  return rest.length ? { path: rest[0], branch } : null
}

// `git worktree remove [flags] <path>` -> the path, or null.
export function parseWorktreeRemove(cmd) {
  const w = words(cmd)
  const i = w.findIndex((x, k) => x === 'git' && w[k + 1] === 'worktree' && w[k + 2] === 'remove')
  if (i < 0) return null
  for (let k = i + 3; k < w.length; k++) {
    if (/^(;|&&|\|\||\|)$/.test(w[k])) break
    if (!w[k].startsWith('-')) return w[k]
  }
  return null
}

// The number of the pull request `gh pr create` printed, or null.
export function createdPr(cmd, text) {
  if (!/\bgh\s+pr\s+create\b/.test(String(cmd))) return null
  const m = /\/pull\/(\d+)/.exec(String(text ?? ''))
  return m ? Number(m[1]) : null
}

// A handoff file this session wrote (`Write`/`Edit` on a path whose name has "handoff"), else null.
export function handoffFile(tool, path) {
  return (tool === 'Write' || tool === 'Edit') && typeof path === 'string' && /handoff/i.test(path.split('/').pop()) ? path : null
}

// A handoff posted as a comment: `gh pr|issue comment ... handoff`.
export function handoffComment(cmd) {
  return /\bgh\s+(pr|issue)\s+comment\b/.test(String(cmd)) && /handoff/i.test(String(cmd))
}

// Is this a whole percent from 1 to 99, else the default.
export function wholePct(raw, dflt) {
  const n = Number.parseInt(raw ?? '', 10)
  return Number.isInteger(n) && n >= 1 && n <= 99 ? n : dflt
}

export function roleOf(raw) {
  return raw === 'coordinator' || raw === 'implementation' ? raw : null
}

// What a compaction keeps. The handoff path is the load-bearing part.
export function compactInstructions(role, j, coordinatorHandoff) {
  if (role === 'coordinator')
    return (
      `Keep only: the coordinator handoff path ${coordinatorHandoff}, the work queue, and the open pull requests ` +
      'with their state. After compacting, read that handoff first, then continue coordinating.'
    )
  const trees = [...j.worktrees.entries()].map(([p, b]) => (b ? `${p} (${b})` : p))
  return (
    `Keep only: the handoff (${j.handoff ?? 'the latest handoff you wrote, in HANDOFF.md or a PR comment'}), ` +
    `worktrees ${trees.join(', ') || 'none recorded'}, pull requests ${[...j.prs].map((n) => `#${n}`).join(', ') || 'none recorded'}, ` +
    'and the exact next step. Do not remove any worktree. After compacting, read the handoff first, ' +
    'run `git rev-parse HEAD` in the worktree, and continue from the recorded next step.'
  )
}

// The prompt submitted after a clear: the handoff path only.
export function resetPrompt(handoff) {
  return `Read ${handoff} first, then wait for the coordinator's message. Do not start new work.`
}

// Why a mid-job (or coordinator) compaction should run now, or null.
//   fill: context percent or null; windows: [{ lvl, announced }] per usage window.
// The warning line must have reached the model first (`nudged`, `announced`), so it has had a turn to
// write the handoff and push; a coordinator keeps its handoff outside the conversation and is exempt.
export function compactReason({ role, fill, compactPct, nudged, windows }) {
  if (role === null) return null
  const handoffAsked = role === 'coordinator' || nudged
  if (fill !== null && fill >= compactPct && handoffAsked) return `context ${fill}%`
  for (const w of windows) if (w.lvl !== null && (role === 'coordinator' || w.announced !== null)) return 'usage limit'
  return null
}

// --- the job-done reset ----------------------------------------------------------------------------

// True when every pull request this session opened is merged into dev, by the live answer of gh.
async function allMerged($) {
  if (job.prs.size === 0) return false
  for (const n of job.prs) {
    const r = await $.process.run(['gh', 'pr', 'view', String(n), '--json', 'state,baseRefName'], { timeoutMs: 20000 })
    if (r.exitCode !== 0) return false
    const v = JSON.parse(r.stdout)
    if (v.state !== 'MERGED' || v.baseRefName !== 'dev') return false
  }
  return true
}

// Does the job look finished? Cheap checks first, then the live pull-request state.
export function jobDoneShape() {
  return job.removed && job.handoff !== null && job.worktrees.size === 0 && job.background === 0 && !job.pending && !job.cleared
}

async function reset($) {
  try {
    if (!(await allMerged($))) {
      job.pending = false
      return
    }
    const handoff = job.handoff
    job.cleared = true
    await $.command.run({ command: 'clear' })
    resetJob()
    await $.prompt.submit({ text: resetPrompt(handoff) })
  } catch {
    // Fail open: a failed reset leaves the session as it was. `cleared` stays set so it is not retried in a loop.
    job.pending = false
  }
}

export function register(on) {
  // Distinct from lane-band's unmatched session.start: this one carries a matcher (isInteractive), so the two do not
  // collide. A `-p` run never runs it, and so never gets a role.
  on('session.start', { isInteractive: true }, async ($, e, next) => {
    const r = await electRole($)
    if (r !== null) {
      state.role = r.role
      state.coordinator = r.coordinator
      state.line = electionLine(r)
    }
    return next(e)
  })

  on('tool.call', { tool: 'Bash' }, async ($, e, next) => {
    const r = await next(e)
    try {
      if (r?.deny || r?.isError) return r
      const cmd = e.command ?? ''
      if (e.run_in_background === true) job.background += 1
      const add = parseWorktreeAdd(cmd)
      if (add) {
        if (job.cleared) resetJob()
        job.worktrees.set(add.path, add.branch)
        job.removed = false
      }
      const rm = parseWorktreeRemove(cmd)
      if (rm) {
        job.worktrees.delete(rm)
        job.removed = true
      }
      const pr = createdPr(cmd, r?.text ?? r?.result?.stdout)
      if (pr !== null) job.prs.add(pr)
      if (handoffComment(cmd)) job.handoff = job.handoff ?? 'the handoff comment you posted on the pull request or issue'
    } catch {
      // Bookkeeping only; never alter the call
    }
    return r
  })

  on('tool.call', { tool: ['Write', 'Edit'] }, async ($, e, next) => {
    const r = await next(e)
    try {
      if (!r?.deny && !r?.isError) job.handoff = handoffFile(e.tool, e.file_path) ?? job.handoff
    } catch {
      // Bookkeeping only
    }
    return r
  })

  // The reset runs from a timer, never inside this awaited hook: command.run rejects there.
  on('turn.complete', async ($, e, next) => {
    try {
      if (e.agentId === undefined && state.role === 'implementation' && jobDoneShape() && (await $.session.surfaces()).length > 0) {
        job.pending = true
        $.clock.after(0, () => void reset($))
      }
    } catch {
      job.pending = false
    }
    return next(e)
  })
}
