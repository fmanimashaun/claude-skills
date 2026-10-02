// lane-band: a read-only band above the prompt showing where this session is working.
// Shows the branch, the worktree directory, the assigned lane (RAILS_FLOW_LANE) and the number of
// uncommitted files. It blocks nothing and rewrites nothing: every hook returns next(e) unchanged.
// Draws in the terminal and the Desktop Code tab only; the VS Code chat panel draws nothing.
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

// Counts refreshes as they start, so a slow one that finishes late cannot overwrite a newer answer.
let latest = 0

// Read branch, worktree and dirty count, then ask Claude Code to draw the band again.
// `--no-optional-locks` keeps `git status` from rewriting .git/index while the user's own git runs.
async function refresh($) {
  const mine = ++latest
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
  if (mine !== latest) return
  info = next
  $.ui.invalidate('ui.render')
}

// The timer callback. A throw here (a failed redraw request, say) is caught here, so the band never
// depends on how the host treats a callback that throws.
async function tick($) {
  try {
    await refresh($)
  } catch {
    // Keep whatever the band last showed
  }
}

export function register(on) {
  // Runs before your first prompt, and again after a reload. The git calls go on a zero-delay timer,
  // the documented way to run work after an event, so the first prompt never waits on them.
  on('session.start', async ($, e, next) => {
    $.clock.after(0, () => tick($))
    return next(e)
  })

  // Runs when a turn ends, which is when the branch or the dirty count has most likely changed
  on('turn.complete', async ($, e, next) => {
    $.clock.after(0, () => tick($))
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
