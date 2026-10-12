// hooks.json names ONE module, so this file registers every mod rails-flow ships.
// Add a mod here with one import and one call; do not add a second path to hooks.json.
import { register as contextNudge } from './context-nudge.mjs'
import { register as laneBand } from './lane-band.js'
import { register as budgetGuard } from './budget-guard.mjs'
import { register as sessionReset } from './session-reset.mjs'

export function register(on, options) {
  contextNudge(on, options)
  laneBand(on, options)
  budgetGuard(on, options)
  sessionReset(on, options)
}
