// lane-band: a read-only band above the prompt showing where this session is working.
// Shows the branch, the worktree directory, the assigned lane (RAILS_FLOW_LANE) and the number of
// uncommitted files, refreshed every two seconds. It blocks nothing and rewrites nothing: every hook
// returns next(e) unchanged.
// Verified in the terminal only. `AbovePrompt` is also raised on the Desktop Code tab, but this band's
// data comes from `$.process`, which Claude Code's type declarations mark "CLI only", and it has not been
// run on Desktop. The VS Code chat panel draws nothing.
// Tested with Claude Code 2.1.287 (`claude plugin validate` and `claude plugin test`); mods need that version or later.

// What the band shows. Reset to null when the working directory is not a git repository.
let info = null

// Run one git command and return its trimmed stdout, or null when git fails or cannot start.
async function git($, args) {
  try {
    const r = await $.process.run(['git', ...args], { timeoutMs: 5000 })
    return r.exitCode === 0 ? r.stdout.trim() : null
  } catch {
    return null
  }
}

// Read branch, worktree and dirty count, then ask Claude Code to draw the band again.
// `--no-optional-locks` keeps `git status` from rewriting .git/index while the user's own git runs.
async function refresh($) {
  const top = await git($, ['rev-parse', '--show-toplevel'])
  let next = null
  if (top !== null) {
    const branch = (await git($, ['branch', '--show-current'])) || 'detached HEAD'
    const status = (await git($, ['--no-optional-locks', 'status', '--porcelain'])) ?? ''
    let lane = ''
    try {
      lane = (await $.env.get('RAILS_FLOW_LANE')) || ''
    } catch {
      // Keep the band without a lane rather than losing it
    }
    next = {
      branch,
      worktree: top.split('/').pop(),
      lane,
      dirty: status === '' ? 0 : status.split('\n').length,
    }
  }
  info = next
  $.ui.invalidate('ui.render')
}

// True while a refresh is running, so a slow one is never overlapped by the next tick.
let busy = false

// The timer callback. A throw or a rejection here (a failed redraw request, say) is caught here, so
// the band never depends on how the host treats a callback that fails.
async function tick($) {
  if (busy) return
  busy = true
  try {
    await refresh($)
  } catch {
    // Keep whatever the band last showed
  } finally {
    busy = false
  }
}

export function register(on) {
  // Runs before your first prompt, and again after a reload (which cancels the old timer). The git
  // calls run on a repeating timer, the documented way to do background work, so neither the first
  // prompt nor the end of a turn ever waits on them. The first refresh comes one interval after start.
  on('session.start', async ($, e, next) => {
    $.clock.every(2000, () => tick($))
    return next(e)
  })

  // Runs each time Claude Code draws the band above the prompt
  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const theirs = await next(e)
    if (info === null) return theirs
    const { Box, Text } = $.ui.resolve(e)
    const parts = [info.branch, info.worktree]
    if (info.lane) parts.push('lane ' + info.lane)
    parts.push(info.dirty === 0 ? 'clean' : info.dirty + ' uncommitted')
    // Keep what the mods after this one draw, and put the line above it
    return Box({
      flexDirection: 'column',
      children: [Text({ dimColor: true, children: [parts.join(' · ')] }), ...(theirs ? [theirs] : [])],
    })
  })
}
