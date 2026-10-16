#!/usr/bin/env node
// Make THIS session the machine-wide coordinator, without going to the current holder (#2070).
//   node claim_coordinator.mjs <engine-pid> <session-id>
// The caller passes its shell's $PPID (the Claude Code process: measured, the Bash tool's shell is its child) and
// $CLAUDE_CODE_SESSION_ID. This runs the election script's force path with that pid, so the claim is written exactly as
// RAILS_FLOW_ROLE=coordinator would write it. The previous holder is not told: its next turn re-reads the claim and
// demotes itself (syncRole in session-reset.mjs).
import { spawnSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { join } from 'node:path'
import { ELECT_SCRIPT } from '../hooks/session-reset.mjs'

export function validArgs(pid, sid) {
  return /^\d+$/.test(pid ?? '') && /^[\w-]+$/.test(sid ?? '')
}

// Who holds the claim now: { pid, sid } or null.
export function currentHolder(home = homedir()) {
  try {
    const [pid, sid] = readFileSync(join(home, '.claude/rails-flow/coordinator/claim'), 'utf8').split('\n')
    return /^\d+$/.test(pid) ? { pid, sid: /^[\w-]+$/.test(sid ?? '') ? sid : 'unknown' } : null
  } catch {
    return null
  }
}

export function claim(pid, sid, env = process.env) {
  const r = spawnSync('sh', ['-c', ELECT_SCRIPT, 'sh', sid, '1', '0', pid], { encoding: 'utf8', timeout: 8000, env })
  return r.status === 0 && r.stdout.trim() === 'coordinator'
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const [pid, sid] = process.argv.slice(2)
  if (!validArgs(pid, sid)) {
    console.error('usage: claim_coordinator.mjs <engine-pid> <session-id>   (pass "$PPID" "$CLAUDE_CODE_SESSION_ID" from the Bash tool)')
    process.exit(2)
  }
  try {
    process.kill(Number(pid), 0)
  } catch {
    console.error(`pid ${pid} is not a live process: refusing to claim for it`)
    process.exit(2)
  }
  const before = currentHolder()
  if (!claim(pid, sid)) {
    console.error('the claim was not made (the election script did not answer coordinator)')
    process.exit(1)
  }
  console.log(`coordinator claimed for pid ${pid} (session ${sid}).` +
    (before && before.pid !== pid ? ` Previous holder: pid ${before.pid} (session ${before.sid}); it demotes itself at its next turn.` : ' It was already the holder.'))
}
