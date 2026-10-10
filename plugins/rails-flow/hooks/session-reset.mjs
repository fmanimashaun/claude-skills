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
export const state = { role: null, coordinator: null, line: null, hasSurface: false, compactDue: null, rearm: null, debug: [] }

// Debug notes: with RAILS_FLOW_DEBUG=1 each compact or clear decision, and any rejection, is appended to
// ~/.claude/rails-flow/debug.log, so a live test can be read without a transcript. Off, the notes are dropped.
// context-nudge.mjs adds notes through this pure function; only this module holds `$` and writes the file.
export function debugNote(line) {
  state.debug.push(String(line).slice(0, 400))
  if (state.debug.length > 100) state.debug.shift()
}

async function debugFlush($) {
  const lines = state.debug.splice(0)
  try {
    if (lines.length === 0 || (await $.env.get('RAILS_FLOW_DEBUG')) !== '1') return
    await $.process.run(
      ['sh', '-c', 'd="$HOME/.claude/rails-flow"; mkdir -p "$d" && printf "%s\\n" "$1" | while IFS= read -r l; do printf "%s %s\\n" "$(date +%Y-%m-%dT%H:%M:%S)" "$l"; done >> "$d/debug.log"', 'sh', lines.join('\n')],
      { timeoutMs: 5000 },
    )
  } catch {
    // A debug log never affects the session
  }
}

function say($, line) {
  debugNote(line)
  void debugFlush($)
}

// Queue the compaction the context-nudge decided is due. `/compact` goes through `$.command.run`: it is "queued and
// run once the session is idle", where `$.session.compact` "rejects while a turn runs" (measured live on 2.1.296: a
// compact tried from session.measure, which fires during a turn, never ran). Called from turn.complete only.
function queueCompact($, due) {
  say($, `compact queued (${due.key}: ${due.reason}) via /compact, role=${state.role}`)
  const failed = (err) => {
    state.rearm = due.key
    say($, `compact REJECTED (${due.key}): ${String(err?.message ?? err).slice(0, 200)}`)
  }
  try {
    $.command
      .run({ command: 'compact', args: due.text })
      .then(() => say($, `compact done (${due.key})`))
      .catch(failed)
  } catch (err) {
    failed(err)
  }
}

// POSIX sh, run with $1 = this session's id, $2 = "1" to force a claim, $3 = "1" for a RESUMED session: it never
// makes or takes a claim, it only keeps one that already carries its own session id (owner rule, 2026-10-09, #1724).
// A resumed session whose claim holds another id, or none, reports implementation. $PPID is the engine's own pid
// (measured under `claude -p` 2.1.293: the shell `$.process.run` starts has the claude process as parent).
// The claim is a directory made with mkdir, which is atomic: of two simultaneous starts exactly one makes it.
// A claim is live only while its pid exists AND its process start time matches (a recycled pid after a
// reboot is not the coordinator). A stale claim is replaced under a second mkdir lock, so two takers cannot
// both win; a taker that finds the lock held reports implementation (fewer coordinators, never more). A claim directory
// exists a moment before its `claim` file is written, so an EMPTY claim younger than a minute is one being made, and is
// never taken over (#1728 review: a taker that removed it let both sessions print coordinator). A coordinator that dies is
// replaced only at the NEXT session start, and RAILS_FLOW_ROLE=coordinator (force) takes the claim without telling the
// live holder, which keeps believing it coordinates until it next starts.
export const ELECT_SCRIPT = `
d="$HOME/.claude/rails-flow"; c="$d/coordinator"; lk="$d/lock"; me="$PPID"; sid="$1"; force="$2"; resumed="$3"
mkdir -p "$d" || { echo error; exit 0; }
start() { ps -o lstart= -p "$1" 2>/dev/null | sed 's/^ *//'; }
claim() { mkdir "$c" 2>/dev/null || return 1; printf '%s\\n%s\\n%s\\n%s\\n' "$me" "$sid" "$(date +%s)" "$(start "$me")" > "$c/claim"; }
alive() { [ -n "$1" ] && kill -0 "$1" 2>/dev/null && [ "$(start "$1")" = "$2" ]; }
read_claim() { hp=$(sed -n 1p "$c/claim" 2>/dev/null); hs=$(sed -n 2p "$c/claim" 2>/dev/null); hl=$(sed -n 4p "$c/claim" 2>/dev/null); }
report() { echo "implementation $hp $hs"; exit 0; }
if [ "$force" = "1" ]; then rm -rf "$c"; fi
if [ "$resumed" = "1" ] && [ "$force" != "1" ]; then
  read_claim
  if [ -n "$hp" ] && [ "$hs" = "$sid" ] && { [ "$hp" = "$me" ] || ! alive "$hp" "$hl"; }; then
    printf '%s\\n%s\\n%s\\n%s\\n' "$me" "$sid" "$(date +%s)" "$(start "$me")" > "$c/claim"; echo coordinator; exit 0
  fi
  report
fi
if claim; then echo coordinator; exit 0; fi
read_claim
if [ -z "$hp" ]; then sleep 1; read_claim; fi
young_empty() { [ -z "$hp" ] && [ -d "$c" ] && [ -z "$(find "$c" -maxdepth 0 -mmin +1 2>/dev/null)" ]; }
if young_empty; then report; fi
if [ "$hp" = "$me" ] && [ "$hl" = "$(start "$me")" ]; then echo coordinator; exit 0; fi
if alive "$hp" "$hl"; then report; fi
if [ -n "$(find "$lk" -maxdepth 0 -mmin +1 2>/dev/null)" ]; then rmdir "$lk" 2>/dev/null; fi
mkdir "$lk" 2>/dev/null || report
read_claim
if alive "$hp" "$hl" || young_empty; then rmdir "$lk"; report; fi
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
    ? 'rails-flow role: this session was elected coordinator (none was live). It compacts itself near a limit and never clears.'
    : `rails-flow role: this session is an implementation session; the coordinator is ${r.coordinator ?? 'another live session'}. ` +
        'It clears itself after its PR is merged into dev and its worktree is removed.'
}

// Is this session a resume (or continue, or fork)? The mods `session.start` input carries no start source: its
// SessionStartInput is { cwd, surface, isInteractive } (plugins/rails-flow/.claude-plugin/types/claude-code/index.d.ts
// line 11679). The `source: 'startup' | 'resume' | 'clear' | 'compact' | 'fork'` field is on the classic hook's
// SessionStartHookInput (line 11653), which a mod does not receive. A mod sees the transcript instead:
// `$.session.turns()` (line 2799, "how many prompts the user has sent this session (user turns in the transcript)")
// is 0 at a fresh start and above 0 in a resumed conversation. Unmeasured live. If it cannot be read the session
// counts as resumed: fewer coordinators, never more.
async function isResumed($) {
  try {
    return (await $.session.turns()) > 0
  } catch {
    return true
  }
}

// Elect this session's role. Fails open to null: any error leaves the session with no automatic action.
export async function electRole($) {
  try {
    const forced = roleOf(await $.env.get('RAILS_FLOW_ROLE'))
    if (forced === 'implementation') return { role: forced, coordinator: null }
    const sid = await $.session.id()
    const r = await $.process.run(['sh', '-c', ELECT_SCRIPT, 'sh', String(sid), forced === 'coordinator' ? '1' : '0', (await isResumed($)) ? '1' : '0'], { timeoutMs: 8000 })
    return r.exitCode === 0 ? parseElection(r.stdout) : null
  } catch {
    return null
  }
}

// What this session has done in its current job. Reset after a clear.
export const job = freshJob()
function freshJob(epoch = 0) {
  return { epoch, touched: false, checked: null, turnEnd: null, worktrees: new Map(), removedPaths: new Set(), prs: new Set(), handoff: null, removed: false, background: 0, pending: false, cleared: false }
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
// Anchored: a URL is accepted only as a WHOLE word, so a github.com address embedded in another URL or text never
// counts (CodeQL js/regex/missing-regexp-anchor on #1728). lastMatch splits the text into words first.
const PR_URL = /^https:\/\/github\.com\/[\w.-]+\/[\w.-]+\/pull\/\d+$/
const COMMENT_URL = /^https:\/\/github\.com\/[\w.-]+\/[\w.-]+\/(?:pull|issues)\/\d+#issuecomment-\d+$/
const safe = (v, re) => (typeof v === 'string' && re.test(v) ? v : null)
const isCommentUrl = (v) => typeof v === 'string' && COMMENT_URL.test(v)
const isPrUrl = (v) => typeof v === 'string' && PR_URL.test(v)
const lastMatch = (re, text) => (String(text ?? '').match(/\S+/g) ?? []).map((w) => w.replace(/^[(<\["']+|[)>\].,;:"']+$/g, '')).filter((w) => re.test(w)).pop() ?? null

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
    } else if (c === '#' && word === null) {
      while (i + 1 < text.length && text[i + 1] !== '\n') i++ // a comment runs to the end of the line
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

const WRAPPERS = new Set(['env', 'command', 'exec', 'sudo', 'time', 'nohup', '{', 'if', 'then', 'else', 'elif', 'do', 'until', 'while', '!', 'xargs'])
// Options of a wrapper that take a value in the next word (`sudo -u me`, `xargs -n 1`, `env -u VAR`).
const FLAG_VALUE = { sudo: ['-u', '-g', '-h', '-p', '-C', '-D', '-R', '-T', '-r', '-t', '-U'], xargs: ['-I', '-n', '-P', '-L', '-s', '-d', '-E', '-a'], env: ['-u', '-C', '-S'] }
const SHELLS = new Set(['bash', 'sh', 'zsh', 'dash'])

// The argument lists of every `git` command in a line, looking inside `bash -c '...'`, `sh -c` and `eval`, with a
// leading VAR=value or env/command/exec prefix skipped. `git` counts only as the command word, so `grep -rn git
// worktree remove` and `echo "git worktree add"` are prose.
function* gitCommands(cmd, depth = 0) {
  for (const w of commands(cmd)) {
    let i = 0
    while (i < w.length && (/^\w+=/.test(w[i]) || WRAPPERS.has(w[i]))) {
      const wrapper = w[i++]
      // the options of a wrapper are not the command: `xargs -I{} git ...`, `sudo -u me git ...`, `env -i git ...`
      while (WRAPPERS.has(wrapper) && i < w.length && w[i].startsWith('-')) i += (FLAG_VALUE[wrapper] ?? []).includes(w[i]) ? 2 : 1
    }
    const head = w[i]
    if (SHELLS.has(head)) {
      const k = w.findIndex((x, n) => n > i && /^-[a-z]*c$/.test(x))
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
  // A path built by the shell (`$VAR`, `$(...)`, a backtick) or read from stdin (`xargs`) is unknown: it is recorded as
  // a worktree that no later remove can match, so the job never looks finished.
  const path = rest[0] === undefined || /[$`{]/.test(rest[0]) ? '(unknown)' : rest[0]
  return { path, branch }
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
// A HANDOFF THAT SURVIVES the job (#1728 review): a comment URL, or a file outside every worktree this job removed.
// A handoff written inside a worktree that is then removed is gone, and the session must not clear onto it.
// A relative removal path is matched by its last directory name anywhere in the handoff's path, so it errs towards
// not counting the handoff (no clear) rather than counting a lost one.
export function handoffSurvives(h = job.handoff) {
  if (h === null) return false
  if (isCommentUrl(h)) return true
  for (const r of job.removedPaths) {
    if (r.startsWith('/') ? h === r || h.startsWith(`${r}/`) : h.includes(`/${r.split('/').pop()}/`)) return false
  }
  return true
}

export function jobDoneShape(ignorePending = false) {
  return job.removed && handoffSurvives() && job.worktrees.size === 0 && job.background === 0 && (ignorePending || !job.pending) && !job.cleared
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
  say($, `merge check (epoch ${epoch}): ${ok ? 'all merged into dev' : 'not all merged'}`)
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
  say($, `clear queued (epoch ${epoch})`)
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
      .catch((err) => {
        // Fail open: a failed reset leaves the session as it was; `cleared` stays set so it is not retried in a loop.
        job.pending = false
        say($, `clear REJECTED: ${String(err?.message ?? err).slice(0, 200)}`)
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
      say($, `role=${r.role} hasSurface=${state.hasSurface}`)
    }
    return next(e)
  })

  on('tool.call', { tool: 'Bash' }, async ($, e, next) => {
    const r = await next(e)
    try {
      if (r?.deny || r?.isError) return r
      // (the epoch is moved by the catch-all tool.call hook below, for every tool, before this code runs)
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
        job.removedPaths.add(rm.replace(/\/+$/, ''))
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
        job.handoff = handoffFile(e.tool, e.file_path) ?? job.handoff
        maybePrecheck($)
      }
    } catch {
      // Bookkeeping only
    }
    return r
  })

  // A new turn is new work: a cached turn end belongs to the turn before it, and must not let a merge answer that
  // arrives mid-turn queue a clear (Fable's second review of #1728, P1).
  on('turn.start', async ($, e, next) => {
    job.turnEnd = null
    job.touched = false
    return next(e)
  })

  // Every tool call moves the epoch, whatever the tool (Read, Grep, Task as well as Bash, Write, Edit): any call after
  // the cached merge answer means the session is working again.
  on('tool.call', async ($, e, next) => {
    job.epoch += 1
    job.touched = true
    return next(e)
  })

  // Cheap and synchronous: the merge check was done early (precheck), so this only reads it. command.run is called
  // from here with no await before it. It is not awaited, because the turn waits on this hook and the clear runs
  // once the session is idle. Measured on 2.1.293 under `claude -p`: calling it from turn.complete does not reject.
  on('turn.complete', async ($, e, next) => {
    try {
      if (e.agentId === undefined) {
        // A turn that made no tool call (an assignment answered in text) is not the end of the finished job: it
        // must not clear the session and lose that assignment.
        job.turnEnd = job.touched ? job.epoch : null
        if (job.touched && state.role === 'implementation' && state.hasSurface && jobDoneShape() && job.checked?.ok === true && job.checked.epoch === job.epoch) fire($, job.epoch)
        else maybePrecheck($) // no cached answer for this epoch (a background job just ended): ask now; precheck fires the clear
        // A compaction the nudge found due is queued HERE, at turn end, never from session.measure (which fires during a
        // turn). A session whose job is done is cleared instead; a clear that was just queued wins.
        const due = state.compactDue
        state.compactDue = null
        if (due !== null) {
          if (job.pending || jobDoneShape(true)) say($, `compact dropped (${due.key}): the job is done, the clear takes over`)
          else queueCompact($, due)
        }
      }
    } catch {
      job.pending = false
    }
    void debugFlush($) // anything the nudge noted during the turn (a skip, a due compaction) is written now
    return next(e)
  })
}
