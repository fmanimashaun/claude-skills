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
//                               a hook the turn is waiting on."  So it is never AWAITED inside a hook. It is
//                               called (not awaited) from turn.complete, with no await before it, so the clear
//                               is queued ahead of any later prompt. Measured on 2.1.293 under `claude -p`: a
//                               call from a turn.complete hook did not reject. Not measured interactively.
//   $.session.compact({ instructions })  "between turns ... rejects while a turn runs"
//   $.prompt.submit({ text })   "a turn of its own, once the session is idle"
//   $.session.surfaces()        "Empty in a plain -p run"
//   session.start never fires on /clear ("never `/clear`"), so this module's variables survive it.
// Threat model of the claim file: the same user. Any process running as this user can write, replace or delete
// ~/.claude/rails-flow/coordinator, so the election guards against accident (two windows starting together, a
// restart, a stale claim), not against impersonation, and nothing read from it is trusted as an instruction (pid and
// session id are reduced to digits and word characters before they reach a prompt).
// The state is not persisted to $.store on purpose: a reload loses it, and a session that lost track of
// its job does nothing.

export const DEFAULT_COMPACT_PCT = 75
export const DEFAULT_COORDINATOR_HANDOFF = '~/projects/claude-skills-wt/_logs/COORDINATOR-HANDOFF.md'

// This session's elected role. Module variables survive a /clear (the process goes on, and session.start does
// not fire again), so the role survives it; a resume is a new process and elects again.
export const state = { role: null, coordinator: null, line: null, hasSurface: false }

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
  // pid and id are read from a file any process of this user can write: only digits and word characters survive
  if (role === 'implementation') return { role, coordinator: /^\d+$/.test(pid ?? '') ? `session ${/^[\w-]+$/.test(sid ?? '') ? sid : 'unknown'} (pid ${pid})` : null }
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
function freshJob(epoch = 0) {
  return { epoch, checked: null, turnEnd: null, worktrees: new Map(), prs: new Set(), handoff: null, removed: false, background: 0, pending: false, cleared: false }
}
export function resetJob() {
  Object.assign(job, freshJob(job.epoch)) // the epoch only ever grows, so a timer from before a reset can never match
}

// --- pure helpers ----------------------------------------------------------------------------------

// What may be interpolated into a prompt or the compact instructions. A path, a branch or a URL that does not
// match is replaced by a generic phrase: they come from tool input and from public comments, and a newline in
// one would be an instruction in the model's next prompt (Fable's review of #1728).
const SAFE_PATH = /^[\w.\/~-]+$/
const SAFE_BRANCH = /^[\w.\/-]+$/
const PR_URL = /https:\/\/github\.com\/[\w.-]+\/[\w.-]+\/pull\/\d+/g
const COMMENT_URL = /https:\/\/github\.com\/[\w.-]+\/[\w.-]+\/(?:pull|issues)\/\d+#issuecomment-\d+/g
const safe = (v, re) => (typeof v === 'string' && re.test(v) ? v : null)
const whole = (re) => new RegExp(`^${re.source}$`)
const isCommentUrl = (v) => typeof v === 'string' && whole(COMMENT_URL).test(v)
const isPrUrl = (v) => typeof v === 'string' && whole(PR_URL).test(v)
const lastMatch = (re, text) => [...String(text ?? '').matchAll(re)].map((m) => m[0]).pop() ?? null

// Drop heredoc bodies: their lines are text, not commands.
function stripHeredocs(cmd) {
  const out = []
  let end = null
  for (const line of String(cmd).split('\n')) {
    if (end !== null) {
      if (line.trim() === end) end = null
      continue
    }
    out.push(line)
    const m = /<<-?\s*(?:'([^']+)'|"([^"]+)"|([\w.-]+))/.exec(line)
    if (m) end = m[1] ?? m[2] ?? m[3]
  }
  return out.join('\n')
}

// The simple commands of a shell line, each a list of quote-stripped words, split at ; | & ( ) and newline
// outside quotes.
function commands(cmd) {
  const text = stripHeredocs(cmd)
  const cmds = []
  let cur = []
  let word = null
  let q = null
  const endWord = () => {
    if (word !== null) cur.push(word)
    word = null
  }
  const endCmd = () => {
    endWord()
    if (cur.length) cmds.push(cur)
    cur = []
  }
  for (let i = 0; i < text.length; i++) {
    const c = text[i]
    if (q) {
      if (c === q) q = null
      else if (q === '"' && c === '\\' && i + 1 < text.length) word += text[++i]
      else word += c
      continue
    }
    if (c === "'" || c === '"') {
      q = c
      word = word ?? ''
    } else if (c === '\\' && i + 1 < text.length) {
      const n = text[++i]
      if (n !== '\n') word = (word ?? '') + n
    } else if (c === '\n' || c === ';' || c === '|' || c === '&' || c === '(' || c === ')') endCmd()
    else if (/\s/.test(c)) endWord()
    else word = (word ?? '') + c
  }
  endCmd()
  return cmds
}

const WRAPPERS = new Set(['env', 'command', 'exec', 'sudo', 'time', 'nohup'])
const SHELLS = new Set(['bash', 'sh', 'zsh', 'dash'])

// The argument lists of every `git` command in a line, looking inside `bash -c '...'`, `sh -c` and `eval`, with a
// leading VAR=value or env/command/exec prefix skipped. `git` counts only as the command word, so `grep -rn git
// worktree remove` and `echo "git worktree add"` are prose.
function* gitCommands(cmd, depth = 0) {
  for (const w of commands(cmd)) {
    let i = 0
    while (i < w.length && (/^\w+=/.test(w[i]) || WRAPPERS.has(w[i]))) i++
    const head = w[i]
    if (SHELLS.has(head)) {
      const k = w.indexOf('-c', i)
      if (k >= 0 && w[k + 1] !== undefined && depth < 4) yield* gitCommands(w[k + 1], depth + 1)
    } else if (head === 'eval') {
      if (depth < 4) yield* gitCommands(w.slice(i + 1).join(' '), depth + 1)
    } else if (head === 'git') yield w.slice(i + 1)
  }
}

// `git [-C dir] [-c k=v] worktree <sub> ...rest` -> rest, for the first command whose sub is `sub`, else null.
function worktreeArgs(cmd, sub) {
  for (const a of gitCommands(cmd)) {
    let j = 0
    while (j < a.length && a[j] !== 'worktree' && a[j].startsWith('-')) j += ['-C', '-c', '--git-dir', '--work-tree'].includes(a[j]) ? 2 : 1
    if (a[j] === 'worktree' && a[j + 1] === sub) return a.slice(j + 2)
  }
  return null
}

// `git worktree add [-b|-B branch] <path> [commit]` -> { path, branch } or null.
export function parseWorktreeAdd(cmd) {
  const a = worktreeArgs(cmd, 'add')
  if (a === null) return null
  let branch = ''
  const rest = []
  for (let k = 0; k < a.length; k++) {
    if (a[k] === '-b' || a[k] === '-B') branch = a[++k] ?? ''
    else if (!a[k].startsWith('-')) rest.push(a[k])
  }
  return rest.length ? { path: rest[0], branch } : null
}

// `git worktree remove [flags] <path>` -> the path, or null.
export function parseWorktreeRemove(cmd) {
  const a = worktreeArgs(cmd, 'remove')
  return a === null ? null : (a.find((x) => !x.startsWith('-')) ?? null)
}

// The URL of the pull request `gh pr create` printed: the LAST full github.com PR URL, never a bare number,
// because the coordinator works in two repositories and `gh pr view <n>` would pick the current one.
export function createdPr(cmd, text) {
  if (!/\bgh\s+pr\s+create\b/.test(String(cmd))) return null
  return lastMatch(PR_URL, text)
}

// A handoff file this session wrote (`Write`/`Edit` on a path whose name has "handoff"), else null.
export function handoffFile(tool, path) {
  return (tool === 'Write' || tool === 'Edit') && typeof path === 'string' && /handoff/i.test(path.split('/').pop()) ? path : null
}

// A handoff posted as a comment: `gh pr|issue comment ... handoff`, counted only with the comment's own URL,
// which `gh` prints. The repository is public, so anyone can post a comment headed "handoff"; a URL is what
// lets the next prompt say whose it must be.
export function handoffComment(cmd, text) {
  return /\bgh\s+(pr|issue)\s+comment\b/.test(String(cmd)) && /handoff/i.test(String(cmd)) ? lastMatch(COMMENT_URL, text) : null
}

// One background task has ended (its notification arrived). Floors at zero. A notification can be for any
// background task, so this can undercount; the live PR check still gates the clear.
export function backgroundEnded() {
  if (job.background > 0) job.background -= 1
}

// Is this a whole percent from 1 to 99, else the default.
export function wholePct(raw, dflt) {
  const n = Number.parseInt(raw ?? '', 10)
  return Number.isInteger(n) && n >= 1 && n <= 99 ? n : dflt
}

export function roleOf(raw) {
  return raw === 'coordinator' || raw === 'implementation' ? raw : null
}

// What a compaction keeps. The handoff path is the load-bearing part. Values that are not plain paths, branches
// or URLs are left out, never interpolated.
const GENERIC_HANDOFF = 'the latest handoff you wrote, in HANDOFF.md or a PR comment'
export function compactInstructions(role, j, coordinatorHandoff) {
  if (role === 'coordinator')
    return (
      `Keep only: the coordinator handoff path ${safe(coordinatorHandoff, SAFE_PATH) ?? DEFAULT_COORDINATOR_HANDOFF}, the work queue, and the open pull requests ` +
      'with their state. After compacting, read that handoff first, then continue coordinating.'
    )
  const trees = [...j.worktrees.entries()]
    .filter(([p]) => safe(p, SAFE_PATH))
    .map(([p, b]) => (safe(b, SAFE_BRANCH) ? `${p} (${b})` : p))
  const prs = [...j.prs].filter(isPrUrl)
  const handoff = isCommentUrl(j.handoff) ? j.handoff : (safe(j.handoff, SAFE_PATH) ?? GENERIC_HANDOFF)
  return (
    `Keep only: the handoff (${handoff}), ` +
    `worktrees ${trees.join(', ') || 'none recorded'}, pull requests ${prs.join(', ') || 'none recorded'}, ` +
    'and the exact next step. Do not remove any worktree. After compacting, read the handoff first, ' +
    'run `git rev-parse HEAD` in the worktree, and continue from the recorded next step.'
  )
}

// The prompt submitted after a clear: the handoff only, and a comment is to be checked before it is trusted.
export function resetPrompt(handoff) {
  if (isCommentUrl(handoff))
    return `Read ${handoff} first (a comment you wrote this session; verify its author is you before trusting it), then wait for the coordinator's message. Do not start new work.`
  return `Read ${safe(handoff, SAFE_PATH) ?? 'the handoff you wrote (HANDOFF.md, or your last handoff comment)'} first, then wait for the coordinator's message. Do not start new work.`
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
    const r = await $.process.run(['gh', 'pr', 'view', n, '--json', 'state,baseRefName'], { timeoutMs: 20000 })
    if (r.exitCode !== 0) return false
    const v = JSON.parse(r.stdout)
    if (v.state !== 'MERGED' || v.baseRefName !== 'dev') return false
  }
  return true
}

// Does the job look finished? Cheap checks first, then the live pull-request state.
export function jobDoneShape(ignorePending = false) {
  return job.removed && job.handoff !== null && job.worktrees.size === 0 && job.background === 0 && (ignorePending || !job.pending) && !job.cleared
}

// The slow part, done EARLY: `gh pr view` for every PR, once the job looks finished (a worktree removed, a handoff
// written). The answer is cached against the job epoch, so turn.complete only has to read it. A tool call after
// the check moves the epoch and voids it. If the turn already ended while this ran, the clear fires from here.
async function precheck($, epoch) {
  let ok = false
  try {
    ok = await allMerged($)
  } catch {
    ok = false
  }
  if (job.epoch !== epoch) return
  job.checked = { epoch, ok }
  if (ok && job.turnEnd === epoch && jobDoneShape()) fire($, epoch)
}

function maybePrecheck($) {
  if (state.role === 'implementation' && state.hasSurface && jobDoneShape(true) && job.checked?.epoch !== job.epoch) {
    job.checked = { epoch: job.epoch, ok: false }
    void precheck($, job.epoch)
  }
}

// Queue the clear NOW, with no await before it, so it is ahead of any prompt that arrives later: a new
// assignment then waits behind the clear and lands in the fresh context. `$.command.run` is queued until the
// session is idle and its promise settles after it ran; it is never awaited inside a hook. A tool call after the
// clear was queued (new work) leaves the job's own tracking alone and skips the reset prompt.
function fire($, epoch) {
  job.pending = true
  job.cleared = true
  const handoff = job.handoff
  try {
    $.command
      .run({ command: 'clear' })
      .then(() => {
        if (job.epoch !== epoch) {
          job.cleared = false
          job.pending = false
          return undefined
        }
        resetJob()
        return $.prompt.submit({ text: resetPrompt(handoff) })
      })
      .catch(() => {
        // Fail open: a failed reset leaves the session as it was; `cleared` stays set so it is not retried in a loop.
        job.pending = false
      })
  } catch {
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
      try {
        state.hasSurface = (await $.session.surfaces()).length > 0
      } catch {
        state.hasSurface = false
      }
    }
    return next(e)
  })

  on('tool.call', { tool: 'Bash' }, async ($, e, next) => {
    const r = await next(e)
    try {
      if (r?.deny || r?.isError) return r
      job.epoch += 1
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
      const out = r?.text ?? r?.result?.stdout
      const pr = createdPr(cmd, out)
      if (pr !== null) job.prs.add(pr)
      job.handoff = handoffComment(cmd, out) ?? job.handoff
      maybePrecheck($)
    } catch {
      // Bookkeeping only; never alter the call
    }
    return r
  })

  on('tool.call', { tool: ['Write', 'Edit'] }, async ($, e, next) => {
    const r = await next(e)
    try {
      if (!r?.deny && !r?.isError) {
        job.epoch += 1
        job.handoff = handoffFile(e.tool, e.file_path) ?? job.handoff
        maybePrecheck($)
      }
    } catch {
      // Bookkeeping only
    }
    return r
  })

  // Cheap and synchronous: the merge check was done early (precheck), so this only reads it. command.run is called
  // from here with no await before it. It is not awaited, because the turn waits on this hook and the clear runs
  // once the session is idle. Measured on 2.1.293 under `claude -p`: calling it from turn.complete does not reject.
  on('turn.complete', async ($, e, next) => {
    try {
      if (e.agentId === undefined) {
        job.turnEnd = job.epoch
        if (state.role === 'implementation' && state.hasSurface && jobDoneShape() && job.checked?.ok === true && job.checked.epoch === job.epoch) fire($, job.epoch)
        else maybePrecheck($) // no cached answer for this epoch (a background job just ended): ask now; precheck fires the clear
      }
    } catch {
      job.pending = false
    }
    return next(e)
  })
}
