# Frontend architecture framework — outline (#2220, phase 1)

Status: OUTLINE ONLY. No doctrine file is edited. Paths are under `plugins/rails-stack/skills/design-system/` (the skill moved there with #2162; cited as `DS/`). Line numbers measured on `origin/dev` 8028b619.
React and Next.js specifics are out of scope here; they belong to #2222. The audit that consumes these layers is #2221.

## What exists today, what this adds

The skill covers tokens, primitives, a component catalog and screen anatomies. Nothing says how an application's interface is *architected*: what the shell owns, how navigation is modelled, which states every screen must design, and what an audit may call a defect. The framework is one page at the top of the skill (`DS/references/architecture.md`, new), linked from `DS/SKILL.md`; each layer constrains the one below it. `DS/SKILL.md:3-4` still says "Rails 8 + Hotwire + Tailwind", which contradicts the stack-neutral ruling (#2178) and is fixed in the same change.

## Shape of the seven layers (Fable advisory, 2026-10-21)

"Each layer constrains the one below" holds for layers 1-4 only: shell contains navigation, which contains page templates, which contain regions. Layer 5 (state contract) and layer 6 (cross-cutting contracts) are applied **at every one of those levels**, not constrained by the one above, and layer 7 is an index. The framework page says so: **four structural layers, two contracts applied at every level, one index.**

Concerns the advisory found missing, folded into layers 5 and 6 as named contracts rather than new layers: **forms and data entry** (validation timing, inline error placement, required marking, error summary), **notifications** (inline vs toast vs banner vs badge, persistence), **permissions** (hide vs disable an affordance, not only a 403 page), **content design** (error wording, button labels, voice), **internationalisation** (text expansion, RTL, locale formats), **focus management on navigation** (a route change moves focus; load-bearing for any client-routed stack), and **destructive confirmation and undo**. Each needs its own external source before it ships (added to the claim list as C26-C32).

## The seven layers

Legend: **covered** = a rule exists; **partial** = exists for one shape or in Rails terms; **missing** = nothing. "Check" = a script can fail; "advice" = judgement, labelled so.

### 1. Application shell
- Today: **partial.** Three shell archetypes (sidebar, stacked, multi-column) `DS/references/page-anatomies.md:57-160`; what every shell must keep (skip link, modal frame, toast live region) `:16-37`; type ramp inside a shell `:39-55`. The contract is written in ERB/Turbo terms (`:20-24`), so it is not neutral yet.
- Adds: a stack-neutral shell contract (persistent regions, where global actions, identity, status and notifications live, what never moves between screens); the Rails snippet becomes the viewcomponent-erb adapter's example. The approved shell mock-up from #2211 is the concrete instance a project conforms to.
- Finding looks like: "screen X drops the skip link / has no `main` landmark / puts the account menu in the page body, not the shell chrome / renders a second shell."
- Kind: **check** for one `main` landmark and the toast region (a DOM scan the QA crawl can run; authority: HTML spec, C2); the skip link and one-`h1` are **our rules** (WCAG 2.4.1 asks for *a* bypass mechanism, which landmarks or headings also satisfy; no standard requires one `h1`), so they are checks labelled maintainer decision; **advice** for chrome placement. Shell conformance against the mock-up is #2211's.

### 2. Information architecture and navigation model
- Today: **partial.** Nav components (header, sidebar, tabs, breadcrumb, pagination) are in the catalog `DS/references/components.md:42,817,828,1032`; the sidebar and stacked shells place them `page-anatomies.md:85`. Sort/filter/page as URL state `page-anatomies.md:409-418`. Nothing on hierarchy depth, primary vs secondary nav, wayfinding rules, or route design as interface.
- Adds: the navigation model (levels, what is primary, current-location signalling, breadcrumb rule, how deep before a pattern change), and URL design (a view is addressable; a state that changes what the user sees is in the URL).
- Finding looks like: "three nav levels with no current-location marker", "a destination reachable only from a modal", "list state not in the URL so back loses it".
- Kind: **check** for `aria-current` on the current item of the **primary** nav only (GOV.UK-style breadcrumbs omit the current page, so a breadcrumb scan would flag a compliant nav) and for state-in-URL on lists (route sweep); wizards are exempt from Multiple Ways (2.4.5); **advice** for hierarchy depth and naming. **Add:** a navigation moves focus (a route change in a client-routed stack must place focus on the new view).

### 3. Page templates
- Today: **covered, in Rails/product terms.** Home/dashboard `:170`, detail `:205`, list-detail `:242`, supporting pane `:297`, feed `:327`, data table `:343`, settings `:511`, plus marketing, auth, error and commerce screens `:810-1392`. Missing as a named template: **create/edit** (today only "modal-driven CRUD", `DS/SKILL.md:103-104`, which is a Rails/Turbo choice, not a template) and **empty-first-run** (only the dashboard bullet `:195-197`).
- Adds: extend `page-anatomies.md`, never duplicate it: a template index mapping the issue's six templates (list/index, detail, create/edit, dashboard, settings, first-run) to the existing anatomy sections, plus the two missing ones. Each template lists its regions.
- Finding looks like: "an index screen with no count / no empty state / no filtered-empty state", "an edit screen with no way back and no unsaved-change handling".
- Kind: **advice** for template choice; **check** where a template has a mechanical part (the data table's five states, count shown: our rule, `page-anatomies.md:383`). Naming note: Atomic Design's "template" is a content-less skeleton and "page" its instance, so our "page templates" correspond to Atomic's pages/patterns; the framework page states the mapping or drops the Atomic reference. The six templates are our decision, not GOV.UK's (its patterns are question, confirmation, start, task-list, check-answers).

### 4. Regions and composition rules
- Today: **partial.** Regions per anatomy are named inside each anatomy; composition via primitives (`DS/references/layout-primitives.md`); "which components may appear where" and density per surface are not stated anywhere (grep for density finds only incidental hits). Art direction covers per-surface intent `DS/references/art-direction.md`.
- Adds: a region vocabulary shared by all templates (header, toolbar, primary, supporting, footer-actions), the rule for which catalog entries may fill which, and a density rule per surface class (app screen vs marketing vs form).
- Finding looks like: "a card inside a card", "a toolbar below the content", "marketing-density spacing inside an app table".
- Kind: raw layout CSS is a **check** today (`plugins/design-flow/agents/design-auditor.md`); a nested card is **not** checked today (`grep -ci nested` on that agent returns 0; it exists only as prose at `page-anatomies.md:8`), so it is a **new check** to build, labelled maintainer decision; density is **advice**.

### 5. The state contract
- Today: **partial.** Per component: six states or a stated exemption `DS/references/components.md:10-12`, already enforced by `scripts/check_component_states.py`. Per screen: only the data table, "five states, and all five are required" `page-anatomies.md:383-399`. Skeleton rule `components.md:1645-1652`. No contract for permission-denied, partial, or success at screen level, and none for non-table screens.
- Adds: one screen-level state contract (empty-first-run, empty-filtered, loading, error, partial, permission-denied, success), generalising the table's five. Each screen design states which apply.
- Finding looks like: "screen has a loaded state only", "filtered-empty shows the first-run copy", "403 renders an empty list", "a failed region renders as empty".
- Kind: **check** (the best candidate): a catalogue of states per screen in the mock-up/spec, and a crawl that forces each (empty fixture, failing request, forbidden user) and asserts a result that is distinct from the loaded state **and carries the state's own marker** (a 500 page is non-blank and still wrong). "Partial" must be defined before it is audited: a region failed or truncated while the rest rendered. **Needs a decision on where the per-screen state list lives** (see Open questions).

### 6. Cross-cutting contracts
- Today: **partial.** WCAG is cited throughout (75 hits in 15 files; skip link `page-anatomies.md:29-37`), responsive `DS/references/responsive.md`, motion `DS/references/motion.md`. Interaction feedback is per component. **Performance budgets: missing** (only CLS/LCP asides, `DS/references/visual-assets.md:283-285`). Content hierarchy: one mention (`DS/SKILL.md:12`).
- Adds: the five contracts as a short list with the existing references as their depth: accessibility (WCAG 2.2 AA), responsiveness, content hierarchy, interaction feedback, performance budgets.
- Finding looks like: "contrast below 4.5:1", "target under 24px", "page with two `h1`", "an action with no feedback", "LCP image lazy-loaded".
- Kind: **check** for accessibility via axe, with these limits recorded: contrast is 4.5:1 for text but 3:1 for large text and UI components (1.4.3, 1.4.11); target size 24px has spacing, inline, essential and user-agent exceptions (2.5.8) and is not reliably covered by axe; focus-not-obscured at AA means *entirely* hidden (2.4.11); axe runs no focus rule under the WCAG tags (`plugins/qa-flow/agents/a11y-auditor.md:76`), so "focus visible" is **not a check today**; reflow at 320px exempts content needing two-dimensional layout (1.4.10), so the layout check must exempt the data table. Responsiveness (layout fit) and heading order are checks; performance budgets are a **check only if a budget value is a recorded maintainer decision**; otherwise advice. Interaction feedback needs a definition (what counts as feedback, within what window) before it can be audited; pick one threshold (INP 200 ms, C23) and drop the other number.

### 7. Mapping to the flow
- Today: **partial.** `design-flow` commands and `design-auditor` check the Rails implementation `plugins/design-flow/agents/design-auditor.md:13,51-60`; the mock-up-first rule is #2211, open.
- Adds: a table mapping each layer to the artifact that proves it (mock-up, audit, gate), and to the owner (#2211 mock-up, #2221 audit, #2178/#2185 adapters).
- Finding looks like: "a layer with no artifact that proves it".
- Kind: this layer is the index; it has no check of its own.

## Make each layer auditable (for #2221)

Every layer gets, in the framework page: a one-line **conformance statement** ("the shell has exactly one `main` landmark"), the **finding shape** above (a defect an auditor can name with a screen and a region), a **severity default**, and a **kind** (check or advice). #2221 reads that table; it must not invent layers or findings.

## Where the checks can fail

| Layer | Check that can fail | Authority | Owner |
|---|---|---|---|
| 1 shell | one `main` landmark, toast region; skip link and one `h1` as our rules; conformance to the approved shell | HTML spec (C2); maintainer decision (skip link, one `h1`); #2211 | crawl (qa-flow) + #2211 |
| 2 navigation | `aria-current` on primary nav; list state survives reload (URL) | WAI-ARIA (C5); NN/g URL-as-UI (C8) | route sweep |
| 3 templates | table: count shown, states present | maintainer decision (`page-anatomies.md:383-418`) | existing data-table rules |
| 4 regions | raw layout CSS today; nested card to build | maintainer decision | design-auditor |
| 5 state contract | forced-state crawl with per-state markers; per-screen state list present | WCAG 3.3.1, 4.1.3 (C14, C15) for error and status; the state set itself is a maintainer decision | new |
| 6 cross-cutting | axe (WCAG 2.2 AA, with the limits above), layout fit, heading order | WCAG SC per rule; heading order is advice-grade | qa-flow today |
| 7 flow | none (an index) | — | — |

Layers 2 (hierarchy depth), 3 (template choice), 4 (density) and 6 (content hierarchy, performance budgets) are **advice** and labelled so. **Rule for #2221:** a finding cites its authority column. A rule whose authority is "maintainer decision" is reported as a house rule, never as a WCAG or NN/g failure.

## External claims this outline would make

Each goes to `doctrine-verifier` before any skill edit; INCONCLUSIVE stays out. See `docs/design/frontend-architecture-claims.md`.

## Open questions (need a decision, not a guess)

1. Where does a screen's state list live: in the mock-up file, a `states:` block in the screen spec, or the QA test-case catalogue? The check in layer 5 depends on it.
2. Performance budgets: does the maintainer set numbers (our own decision), or do we cite only Core Web Vitals "good" thresholds and leave budgets to the project?
3. The six page templates are our decision (GOV.UK and Carbon do not list them as a set): confirm as a recorded maintainer decision.
4. The create/edit template: `DS/SKILL.md:103-104` mandates modal-driven CRUD, a Rails/Turbo choice. In a stack-neutral framework that is an adapter rule. Confirm it moves out of the non-negotiables for the neutral page.

## Coordination

- #2185 (e6): the design-system catalog split and descriptor-driven design-flow. The framework page is a new file; the only shared edit is `DS/SKILL.md` frontmatter and the Rails wording.
- #2211 (32): the mock-up-first rule and the approved shell. Layer 1 and 7 cite it; no edits to its files.
- #2221: consumes the finding shapes. #2222: React composition, out of scope here.
