# Stimulus audit: plugins/rails-stack/skills/hotwire/references/stimulus.md (+ SKILL.md:46)

Verified against: hotwired/stimulus tag v3.2.2 source (gh api contents ?ref=v3.2.2), GitHub release notes v3.0.0–v3.2.2, hotwired/stimulus-rails tag v1.3.4. Target: Stimulus 3.2.2 (SKILL.md:46), stimulus-rails 1.3.4. Auditor: doctrine-verifier, 2026-10-12. Read-only.

S = https://github.com/hotwired/stimulus/blob/v3.2.2/

| # | Claim (file:line) | Verdict | Source + quote | Version boundary |
|---|---|---|---|---|
| 1 | Default events for 7 tags, input[type=submit]->click (stimulus.md:103-106) | CONFIRMED | S src/core/action.ts:107-115 `input: (e) => (e.getAttribute("type") == "submit" ? "click" : "input")` | 3.x |
| 2 | Off those tags, action dropped silently; "missing event name" swallowed (:107-110) | CONFIRMED | action.ts:28 `error("missing event name")`; src/mutation-observers/value_list_observer.ts:87-93 `catch (error) { return { error } }`, tokenMatched uses only `value` | 3.2.2 |
| 3 | @window/@document targets (:111) | CONFIRMED | src/core/action_descriptor.ts parseEventTarget `window`/`document` | 3.x |
| 4 | Key filters only on keydown/keyup/keypress; else dot joins event name (:114-117) | CONFIRMED | action_descriptor.ts `if (keyFilter && !["keydown","keyup","keypress"].includes(eventName)) { eventName += \`.${keyFilter}\`` | 3.2.0+ |
| 5 | Filter set enter..page_down + a-z + 0-9; no F-keys (:117-120) | CONFIRMED | src/core/schema.ts keyMappings | page_up/page_down added 3.2.2 (release notes "Add PageUp and PageDown", #677); header says "v3.2" — minor, SKILL pins 3.2.2 |
| 6 | defaultSchema exported; custom keyMappings via Application.start schema (:120-124) | CONFIRMED | schema.ts `export const defaultSchema`; application.ts start(element, schema) | 3.2.0+ |
| 7 | Unknown key filter throws "contains unknown key filter", outside handleError (:124-128) | CONFIRMED | action.ts:59 `error(\`contains unknown key filter: ...\`)`, reached after keyFilterDissatisfied; binding.ts willBeInvokedByEvent calls it outside the try in invokeWithEvent | 3.2.x |
| 8 | Modifiers match exactly on all four (:129-132) | CONFIRMED | action.ts keyFilterDissatisfied `event.metaKey !== meta \|\| event.ctrlKey !== ctrl \|\| ...` | 3.2.0+ |
| 9 | Mouse modifier prefix ctrl+click (:132-133) | CONFIRMED | action.ts shouldIgnoreMouseEvent; release v3.2.2 "Support keyboard modifier for click events" (#665) | 3.2.2+ only (file does not state; recommend version note) |
| 10 | Key filter consulted only under instanceof KeyboardEvent (:134-138) | CONFIRMED | binding.ts:89 `if (event instanceof KeyboardEvent && this.action.shouldIgnoreKeyboardEvent(event))` | filters since 3.2.0 (release "Add modifier to filter keyboard events" #442) |
| 11 | Options :prevent :stop :once :capture :passive :self; custom options registrable (:162-165) | CONFIRMED | action_descriptor.ts defaultActionDescriptorFilters stop/prevent/self; others passed as AddEventListenerOptions; application.registerActionOption | :self since 3.1.0 (release notes #546) |
| 12 | data-<ctrl>-<name>-param typed into event.params (:166-168) | CONFIRMED | action.ts params `^data-${identifier}-(.+)-param$` + typecast; binding.ts prepareActionEvent | 3.x |
| 13 | xTarget throws if missing; xTargets; hasXTarget (:192-194) | CONFIRMED | src/core/target_properties.ts:21 `Missing target element "${name}"` | 3.x |
| 14 | [name]TargetConnected/Disconnected callbacks (:89) | CONFIRMED | target_observer / handbook reference/targets | 3.1+ (3.1.0 release) — not stated, acceptable for 3.2 target |
| 15 | Value change callbacks fire on connect with defaults applied (:229) | CONFIRMED | src/core/value_observer.ts start() -> invokeChangedCallbacksForDefaultValues | 3.x |
| 16 | Classes: xClass/xClasses/hasXClass (:251-252) | CONFIRMED | src/core/class_properties.ts `${key}Class`, `${key}Classes`, `has${capitalize(key)}Class` | 3.x |
| 17 | Outlets: xOutlet (throws), xOutlets, xOutletElements, hasXOutlet, xOutletConnected (:269-284) | CONFIRMED | src/core/outlet_properties.ts lines 31-98 incl. `throw new Error(` | Outlets since 3.2.0 (release "Outlets API" #576) |
| 18 | Outlet attribute data-<id>-<outlet>-outlet (:279) | CONFIRMED | schema.ts `outletAttributeForScope: data-${identifier}-${outlet}-outlet` | 3.2.0+ |
| 19 | dispatch prefixes identifier, bubbles; options target/detail/prefix/bubbles/cancelable (:291-295) | CONFIRMED | src/core/controller.ts:88-100 `target = this.element, detail = {}, prefix = this.identifier, bubbles = true` (+cancelable) | 3.x |
| 20 | static shouldLoad 3.0+ (:60) | CONFIRMED | controller.ts:30 `static get shouldLoad()`; v3.1.0 notes "move shouldLoad check from register to load" (exists pre-3.1) | 3.0+ |
| 21 | static afterLoad(identifier, application) 3.2+ (:63-64) | CONFIRMED | controller.ts:34; release v3.2.0 "Add ability to set afterLoad" #579 | 3.2.0+ |
| 22 | Importmap: index.js eagerLoadControllersFrom; generator skips manifest when importmap.rb exists (:40-52) | CONFIRMED | stimulus-rails v1.3.4 lib/install/app/javascript/controllers/index_for_importmap.js `eagerLoadControllersFrom("controllers", application)`; lib/generators/stimulus/stimulus_generator.rb `rails_command "stimulus:manifest:update" unless Rails.root.join("config/importmap.rb").exist? \|\| options[:skip_manifest]` | stimulus-rails 1.3.4 (main caveat already recorded) |
| 23 | Identifier mapping users/list_item -> users--list-item (:32-34) | CONFIRMED | stimulus_generator.rb `gsub(/\//, "--").gsub("_", "-")` | — |

Totals: 23 CONFIRMED, 0 REFUTED, 0 INCONCLUSIVE.
Advisory (not a defect): add "3.2.2+" to mouse-event modifiers (:132) and page_up/page_down (:118); file header says v3.2 while SKILL.md pins 3.2.2.
