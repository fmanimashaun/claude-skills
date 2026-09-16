# 2026-09-16 — routing the B2B Enterprise UI/UX Design System Manual into `design-system`

**Source.** A *B2B Enterprise UI/UX Design System Manual* supplied by the maintainer on 15 Sep 2026,
covering shell architecture, canvas typologies, tables, permissions matrices, overlays, state
lifecycles, empty states, bulk operations, keyboard ergonomics, a11y, tokens and unsaved-changes
guardrails. **The document itself is not committed here** — it is the maintainer's; what this record
routes are the quotations and figures carried by the issues that filed it (#976, #977, #978, and the
gaps it supplied detail for: #964, #966–#970, #972). If the manual is later committed, link it from
this line and nothing else in the record changes.

**Standing.** The manual is a source of *our own* design decisions — there is no upstream to verify
it against — so every adoption below is a maintainer decision recorded on its issue, per CLAUDE.md's
gate for architecture changes. It was adopted **on general merit, rule by rule**, not wholesale: it is
written for a single-tenant enterprise platform and says so, and this skill ships to any Rails app.
Where a figure of ours was already measured (against the two licensed corpora) and disagreed with the
manual's, ours was kept and the disagreement is written next to it.

**The load-bearing conflict, settled first (#976).** The manual anchors everything to a strict 8px
grid; the shipped scale is fluid `clamp()`. Decision: **split by axis** — structure (shell header,
rails, sticky toolbar, table row heights, the selection column, drawer bounds) is fixed and divisible
by 8, in one marked block enforced by `scripts/check_structural_grid.py`; rhythm (`--space-*`, type)
stays fluid; control heights stay as measured. The manual's §8 checklist applies to the structural half.

## Section by section

| manual section | what it says | verdict | where it landed |
|---|---|---|---|
| Baseline 8px grid, fixed scale `micro…xl`, §8 checklist | every spatial figure divisible by 8 | **adapted** — split by axis; vocabulary not adopted | `foundations-tokens.md` §3b; `scripts/check_structural_grid.py` (#976) |
| Shell: 64px header, 256/64px sidebar, 1440px inner cap, 12-col / 24px gutters | fixed chrome | **adopted** header 64, icon rail 64; **kept ours** rail 288 (`lg:w-72`), cap 1280 (`--width-shell`, measured); 12-col grid **not adopted** (intrinsic `grid-auto` is the doctrine) | `foundations-tokens.md` §3b; `responsive.md` → *Above 1536px* (#978, reconciles #972) |
| Tables: alignment by type, ellipsis + tooltip, sticky dual-axis, density 56/32, 48px selection column | table mechanics | **adopted** | `components.md` → Table (CRUD) (#978, detail for #964) |
| Bulk toolbar replacing `<thead>` on ≥2 selected, 150ms crossfade, count left / actions right, persistent clear | bulk operations | **adapted** — the bar takes the *toolbar's* slot (same height, nothing shifts) on the **first** selection; crossfade is `--duration-fast`; select-all is *this page* with *all matching* as a second act; page-scoped selection is dropped and announced | `page-anatomies.md` → *Selection and bulk actions* (#969) |
| Non-blocking progress banner for >1000ms that survives navigation; *Processing… → Ready* toast | async operations | **adopted** as a shell-level slot fed by a per-user stream; the toast transition only while on the page; five states not two | `components.md` → Background operation (#968) |
| Error/500 empty state: icon, plain cause, *Reload Module*, generated Error ID | failed requests | **adopted** as the Error empty state with *Try again* re-sending the same request; the interface for a request that never returned is the hotwire skill's | `components.md` → Empty state (#978); `hotwire/references/turbo.md` (#967) |
| Toolbar: date pickers far left, filters at 16px, export right-aligned, sticky 56px | filter toolbar | **adopted**; the period selector is defined as URL state, not a date picker | `page-anatomies.md` → *The toolbar's order*; `components.md` → Period selector (#970) |
| Toasts bottom-right, 24px from the edge, 8px stack gap, 5000ms; **errors require manual dismissal** | notifications | **adopted** the dismissal rule (it fixes a measured defect, Retask #268); **not adopted** bottom-right — top-right stays; gap stays fluid `--space-2xs` | `components.md` → Toast; `component-implementations.md` (#977) |
| Empty-state typology: First Use / Cleared (no illustration) / Error | empty states | **adopted** | `components.md` → Empty state (#978) |
| Keyboard layer: `⌘K`, `?`, `j`/`k`, `Enter`, `x`, `<kbd>` pattern | power users | **adopted, with the obligation the manual omits** — WCAG 2.1.4 (Level A): single-character keys active only on focus, `?` behind a turn-off setting | `interaction-stimulus.md` → *The power-user keyboard layer* (#978) |
| Double-lock destructive confirmation (typed phrase) | confirmations | **adopted, scoped** — irreversible *and* bulk or naming a shared resource; never on a routine delete | `components.md` → Modal (#978) |
| Dirty-exit prevention with a *Discard / Return to editing* interstitial | unsaved changes | **adopted, corrected** — the interstitial is possible for Turbo visits only; `beforeunload` shows the platform's dialog (HTML Standard: not customizable, needs sticky activation); autosaving forms have no dirty state to guard | `forms.md` → *Unsaved changes* (#978) |
| Permissions matrix: roles × features, module accordions, four checkbox states | permissions | **adopted**; `indeterminate` → `aria-checked=mixed` is normative (HTML-AAM) | `components.md` → Permissions matrix (#978) |
| Slide-out detail drawer: 33% viewport, 480–720px, fixed header/footer, 40% backdrop, focus trap | overlays | **adopted** bounds and structure; backdrop stays `bg-overlay/50` to match Modal (one dialog implementation) | `components.md` → Drawer (#978) |
| Component state matrix: six required states | completeness | **adopted** as a rule at the top of the catalogue | `components.md` intro (#978) |
| No workspace switcher (single tenant) | tenancy | **not adopted** — tenancy-specific; the permissions matrix carries the one tenancy note | — |
| Tab counts | — | the manual does not rule; #971's measurement stands | — |

## What was verified before it was written (doctrine-verifier, 16 Sep 2026)

The manual's rules are ours to adopt, but several of them stand on framework or standards facts, and
those were confirmed against their sources before any edit: `aria-checked="mixed"` and the
`indeterminate` → `mixed` mapping (WAI-ARIA 1.2; HTML-AAM 1.0, normative); WCAG 2.1.4 Character Key
Shortcuts (Level A) and its three clauses; the toolbar-label MUST (WAI-ARIA 1.2, `toolbar`); `<kbd>`
semantics (HTML Standard); `beforeunload`'s non-customizable prompt and sticky-activation condition
(HTML Standard); `turbo:before-visit`'s history exception (Turbo reference); Active Job `retry_on` /
`discard_on`, Solid Queue's *no retry mechanism of its own* and its failed-executions table,
`limits_concurrency` with `on_conflict:`, and `perform_later` returning `false` on a failed enqueue
(Rails 8.1 API, solid_queue README). One citation in the shipped Toast entry was found to be
unattributed and to **not** support the error exception it sat beside — it is now attributed to
Mobbin's glossary and the error rule is stated as ours.

## Downstream evidence the routing rested on

`fmanimashaun/Retask-platform`: the 236px rail (fails the grid, satisfies the fluid doctrine); #268
(two refusals as disappearing toasts, recorded as "no message"); #258 (a failed Turbo request shows
nothing — templates cloned from server markup, delegated retry, the Stimulus-controller-vs-module
timing measured); D-061 (a KPI strip reading "0 / Nothing yet" over computed figures); seven reports
each with its own period handling; `Uploads::Inspection` with seven rejection reasons and ceilings
checked before extraction; Solid Queue in-Puma with mail failing inside jobs and no surface saying so.
