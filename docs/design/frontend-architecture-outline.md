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

## Enforcement (owner ruling 2026-10-21: "a claim or rule not enforced is useless")

No rule ships as advice. Every rule gets one of three enforcements, defined on #2220: **(1) mechanical check** (a lint, AST or rendered-page check in `checks.json` with a negative fixture and a mutation guard); **(2) required declaration verified by script** (the mock-up record names its template, states and so on, and a script refuses a missing or unknown value); **(3) recorded review verdict** (the reviewer records pass/fail with evidence per judgement rule, and a script refuses a PR whose record lacks one). A rule that fits none is rewritten until it does, or dropped. The per-layer "Kind: advice" lines above are superseded by this table; "authority" is where the rule comes from (a WCAG SC, a named source, or a maintainer decision), and #2221 cites it so a house rule is never reported as a standards failure.

| Layer | Rule | Enforcement | Where it would live | Authority |
|---|---|---|---|---|
| 1 shell | one non-hidden `main`, toast region present | 1 | rendered-page scan in the qa-flow crawl | HTML spec (C2) |
| 1 | skip link first in `body`; one `h1` | 1 | same scan | maintainer decision (C1: WCAG asks only for a bypass mechanism) |
| 1 | global actions, identity and status sit in shell chrome, as the approved shell | 2 | record `Shell:` line (#2211) names each region; script refuses an unknown region name | maintainer decision |
| 2 navigation | `aria-current` on the current item of primary nav | 1 | route sweep | WAI-ARIA (C5) |
| 2 | a list's sort/filter/page state is in the URL and survives reload | 1 | route sweep: load, change state, reload, compare | maintainer decision (C8 not cited) |
| 2 | each destination declares its parent and level; depth within a recorded cap | 2 | record `Nav:` line; script checks the cap. **The cap is an open number, a maintainer decision** | maintainer decision |
| 2 | a client-side route change moves focus to the new view | 1 | stack-specific crawl, belongs to #2222; neutral page holds the rule | web.dev (C31', pending re-verify) |
| 3 templates | the record declares one `Template:` from the fixed set; an unknown value is refused | 2 | #2226 (vocabulary in `plugins/rails-flow/reference/mockup-vocabulary.json`) | maintainer decision |
| 3 | per-template mechanical parts (data table: count shown, five states) | 1 | existing data-table rules where scripted, else new check | maintainer decision (`page-anatomies.md:383`) |
| 4 regions | no raw layout CSS | 1 | a design-flow gate if one exists (to be measured in phase 2), else new | maintainer decision |
| 4 | no card inside a card | 1 | **new** rendered-page check (none exists today: `grep -ci nested` on `design-auditor.md` returns 0) | maintainer decision |
| 4 | density matches the surface class (app / marketing / form) | 3 | reviewer verdict with evidence per screen | maintainer decision |
| 5 state contract | the record's `States:` line lists the designed states, or `n/a: <why>` per state | 2 | #2211 record check (a2 ruling 2026-10-21) | maintainer decision |
| 5 | each declared state renders distinct from loaded and carries its own marker | 1 | forced-state crawl (empty fixture, failing request, forbidden user) | WCAG 3.3.1, 4.1.3 (C14, C15) for error and status |
| 6 cross-cutting | axe WCAG 2.2 AA with the recorded limits (24px exceptions, no focus rule, 2.4.11 means entirely hidden, 1.4.10 exempts data tables) | 1 | qa-flow a11y gate | WCAG (C18-C21) |
| 6 | focus visible | 1 | **new**: axe runs no focus rule under WCAG tags (`a11y-auditor.md:76`), so a keyboard-tab crawl must be added | WCAG 2.4.7 (C20) |
| 6 | layout fit at 320px; heading order | 1 | qa-flow layout fit; heading-order scan | WCAG 1.4.10 (C21); heading order maintainer decision |
| 6 | Core Web Vitals within "good" (LCP 2.5 s, INP 200 ms, CLS 0.1, p75); a project may override in config | 1 | lab check in the QA gate | web.dev (C23, C33); default is a2's decision |
| 6 | content hierarchy; interaction feedback present for every action | 3 | reviewer verdict with evidence | maintainer decision |
| 6 | security: no unescaped user HTML, CSP present, action authorization | 1 | stack-specific, #2222 and #2223; the neutral page names the contract and the stack plugin enforces it | per stack, official docs |
| 7 flow | every UI change has a mock-up record with the required lines | 2 | #2211 gate | maintainer decision (#2211) |

A rule that cannot yet be placed is not in this table; it is listed under "Open" below until it fits one of the three kinds.

## Page-template set (final, a2 2026-10-21; our maintainer decision, C9)

list; detail (list-detail is a layout variant of it); create/edit; multi-step (question, check answers, confirmation, optional task list); dashboard/home; settings; search results; sign-in; system pages (not found, no permission, error, maintenance). **First-run is a state** (layer 5), not a template. Citations only where fetched: see the C9 table in the claims file (GOV.UK for multi-step, sign-in and three system pages; Material 3 and Lightning for detail and list-detail; Salesforce for home); the rest are ours and labelled so. Nav depth cap: **3 levels from the shell**, a maintainer decision.

**One vocabulary, one home.** The allowed values for `Template:`, `Nav:` and `States:` live in `plugins/rails-flow/reference/mockup-vocabulary.json`, read by the mock-up gate (a stack-neutral script cannot read design-flow's files); this framework page cites that path and a repo lint reads it. The validation is issue #2226, a separate PR stacked on #2211 (32 builds it). Kind-3 rows point at #2225 (reviewer verdict record and its refusing script). Caveats from 32: `Nav:` parent is checkable only for grammar and depth until the shell record carries a nav list; `n/a: <reason>` is a typed bypass (non-empty, not true), so the reviewer verdict reads it.

## External claims this outline would make

Each goes to `doctrine-verifier` before any skill edit; INCONCLUSIVE stays out. See `docs/design/frontend-architecture-claims.md`.

## Decided and open

Decided by a2 on 2026-10-21 (technical calls, recorded for the owner): the state list lives in the mock-up record as a `States:` line beside #2211's `Shell:` line; performance budgets default to the Core Web Vitals "good" thresholds (C33) with a per-project override; modal-driven CRUD leaves the neutral page for Hotwire (#2223, 7e has it as H25/H26); the template set is a maintainer decision, final list above.

Settled since: the final template list, the nav depth cap (3), the record location (#2211's record, vocabulary file above, validation #2226), and the home for reviewer verdicts (#2225).

Open: the nav-list format in the shell record (decided in #2226).

## Coordination

- #2185 (e6): the design-system catalog split and descriptor-driven design-flow. The framework page is a new file; the only shared edit is `DS/SKILL.md` frontmatter and the Rails wording.
- #2211 (32): the mock-up-first rule and the approved shell. Layer 1 and 7 cite it; no edits to its files.
- #2221: consumes the finding shapes. #2222: React composition, out of scope here.
