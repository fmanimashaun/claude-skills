// hooks.json names ONE module, so this file registers every mod rails-flow ships.
// Add a mod here with one import and one call; do not add a second path to hooks.json.
import { register as contextNudge } from './context-nudge.mjs'

export function register(on, options) {
  contextNudge(on, options)
}
