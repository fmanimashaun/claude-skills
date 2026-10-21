# Interface architecture — the layers above the catalog

The catalog says what a **component** looks like; `page-anatomies.md` says what a **screen** looks
like. This page says how an application's interface is **architected**: what the shell owns, how
navigation is modelled, which template a screen is, which states it must design, and what every
screen owes the user whatever it contains. It is stack-neutral: the same layers apply to a
server-rendered app and a client-routed one, and each stack plugin implements them in its own
technology under the same headings.

Nothing here is advice you may ignore. **Every rule below names its basis**, and a script
(`scripts/check_architecture_rules.py` in the marketplace repository) refuses a row without one:

| basis | meaning |
|---|---|
| `check: <path>` | a script that exists today fails when the rule is broken |
| `claim: C#` | an external standard or published pattern, confirmed against the source by `doctrine-verifier`; the rule is worded as the source words it |
| `decision: D#` | our own choice, with no upstream; reported as a house rule, **never** as a WCAG or NN/g failure |

**Today the design-flow checks (A11–A13) read a Rails project's `app/views` and `app/components`;** the same rules for another stack arrive with that stack's adapter (#2185, #2222), and until then they are enforced there by the reviewer, not by a script. A rule whose check is not built yet is not in the table. It is listed under *Arrives with its
enforcement* and joins the table in the change that builds the check.

## The shape: four structural layers, two contracts, one index

Layers 1–4 are a containment hierarchy: the **shell** contains **navigation**, which leads to
**page templates**, which are built from **regions**. Layers 5 and 6 are not constrained by the
layer above them; they are applied at **every** one of those levels: the **state contract** (what a
screen designs when it is not simply loaded) and the **cross-cutting contracts** (accessibility,
responsiveness, content, feedback, performance, security). Layer 7 is the **index** that maps each
layer to the artifact that proves it.

## 1. Application shell

The persistent frame: landmarks, chrome, and where global actions, identity and status live. The
three shell archetypes and what every shell must keep are in `page-anatomies.md` (Shell archetypes;
*The contract every shell keeps*). The approved shell mock-up of a project (`design-flow` mock-up
first, #2211) is the concrete instance a project's screens conform to.

## 2. Information architecture and navigation

Hierarchy, primary and secondary navigation, wayfinding and URL design as part of the interface.
The navigation components are in `components.md`; sort, filter and page as one URL state is in
`page-anatomies.md` (*Sort, filter and page are ONE url state*).

## 3. Page templates

A screen is one of nine templates: **list**, **detail** (list-detail is a layout variant of it),
**create-edit**, **multi-step** (question pages, check answers, confirmation, with an optional task
list), **dashboard-home**, **settings**, **search-results**, **sign-in**, and **system** (not found,
no permission, error, maintenance). First-run is a state (layer 5), not a template. The set is our
decision (D3). Where a public system documents a template, it is cited; the rest are ours and
labelled so:

| template | source |
|---|---|
| detail, list-detail | Material 3 canonical layouts: list-detail, supporting pane, feed; Salesforce Lightning *Record Page* |
| multi-step | GOV.UK Design System: *Question pages*, *Check answers*, *Confirmation pages*, *Complete multiple tasks* |
| dashboard-home | Salesforce Lightning *Home Page* and *App Page* |
| sign-in | GOV.UK: *Create accounts*, *Start using a service* |
| system: not found, error, maintenance | GOV.UK: *Page not found pages*, *There is a problem with the service pages*, *Service unavailable pages* |
| list, create-edit, settings, system: no permission | ours (D3) |
| search-results | ours (D3); the GOV.UK Design System has no search or search-results pattern (checked 2026-10-21), so it has no anatomy and no rule until a source is verified |

`page-anatomies.md` already holds the detailed anatomy of list-detail, detail, the data table,
settings, the dashboard, errors and sign-in; this page names the set and does not repeat them.

## 4. Regions and composition

Which components fill which region, and how a region composes. Layout is composed from the declared
primitives (`layout-primitives.md`), never hand-rolled per page.

## 5. The state contract

Every screen and every component designs the states it can be in, not only loaded: **empty-filtered**,
**loading**, **error**, **partial** (a region failed or was cut off while the rest rendered),
**permission-denied**, **success**, and **first-run** (the resource has no records yet). The
state list of a screen is declared in its mock-up record (D1).

## 6. Cross-cutting contracts

Accessibility (WCAG 2.2 AA), responsiveness, content hierarchy, interaction feedback, performance
budgets and security. Performance budgets default to the Core Web Vitals "good" thresholds (D2); a
project may override them in its own config. Security is a heading here and is enforced by each stack
plugin, since escaping, content-security policy and action authorization are stack mechanisms.

## 7. Mapping to the flow

| layer | proved by |
|---|---|
| 1 shell | the approved shell mock-up (#2211) |
| 2 navigation, 3 templates | the mock-up record's `Nav:` and `Template:` lines (#2226) |
| 4 regions | the design-flow layout checks |
| 5 state contract | the mock-up record's `States:` line (D1) |
| 6 cross-cutting | the qa-flow rendered-page checks |

## Rules

| id | layer | rule | basis | source |
|---|---|---|---|---|
| A1 | shell | A page has at most one non-hidden `main` landmark. | claim: C2 | HTML spec, *the main element* |
| A2 | shell | A skip link is first in `body`, and the shell keeps its toast region. | decision: D7 | WCAG 2.4.1 asks for *a* bypass mechanism (C1); the skip link is our rule |
| A3 | shell | Every UI change ships a mock-up in the app's own shell before the code. | decision: D6 | #2211 |
| A4 | navigation | The current item of the primary navigation carries `aria-current="page"`. | claim: C5 | WAI-ARIA 1.2 `aria-current`; APG breadcrumb |
| A5 | navigation | Navigation is at most three levels deep from the shell. | decision: D4 | ours |
| A6 | navigation | Navigation repeated across pages keeps the same relative order. | claim: C3 | WCAG 2.2 SC 3.2.3 |
| A7 | navigation | More than one way to locate a page is offered, except for steps in a process. | claim: C4 | WCAG 2.2 SC 2.4.5 |
| A8 | navigation | A list's sort, filter and page are URL state. | decision: D7 | ours (`page-anatomies.md`) |
| A9 | navigation | After a client-side route change, focus moves to a heading in the new content. | claim: C31' | Chrome Lighthouse *managed-focus* |
| A10 | template | A screen is one of the nine templates in layer 3. | decision: D3 | ours |
| A11 | template | A table is master-detail and does not scroll sideways. | check: plugins/design-flow/scripts/check_table_layout.py | ours |
| A12 | regions | Layout is composed from the declared primitives, not hand-rolled. | check: plugins/design-flow/scripts/check_layout_composition.py | ours |
| A13 | regions | A surface does not impose layout on the content it is handed. | check: plugins/design-flow/scripts/check_surface_layout.py | ours |
| A14 | state | Every catalogue component declares its states or says which do not apply. | check: scripts/check_component_states.py | ours |
| A15 | state | An error is identified in text, with a suggestion where one is known. | claim: C14 | WCAG 2.2 SC 3.3.1, 3.3.3 |
| A16 | state | A status message reaches assistive technology without taking focus. | claim: C15 | WCAG 2.2 SC 4.1.3 (technique ARIA22, `role=status`) |
| A17 | state | A first-run state says specifically what will appear and the next action. | claim: C10 | Carbon *Empty states pattern* |
| A18 | state | A permission-denied state says the user lacks permission and suggests how to request access. | claim: C17' | Carbon *Empty states pattern* |
| A19 | cross-cutting | Text contrast is at least 4.5:1, and 3:1 for large text and for UI components. | claim: C18 | WCAG 2.2 SC 1.4.3, 1.4.11 |
| A20 | cross-cutting | Targets are at least 24 by 24 CSS pixels, within the SC's exceptions. | claim: C19 | WCAG 2.2 SC 2.5.8 |
| A21 | cross-cutting | Focus is visible and is not entirely hidden by author content. | claim: C20 | WCAG 2.2 SC 2.4.7, 2.4.11 |
| A22 | cross-cutting | Content reflows at 320 CSS pixels without two-dimensional scrolling, except content that needs it (data tables, maps, video). | claim: C21 | WCAG 2.2 SC 1.4.10 |
| A23 | cross-cutting | A page hides nothing inside the viewport. | check: plugins/qa-flow/scripts/layout_fit.py | ours |
| A24 | cross-cutting | Enlarged text newly hides nothing. | check: plugins/qa-flow/scripts/text_resize.py | ours |
| A25 | cross-cutting | One theme does not break what the other renders. | check: plugins/qa-flow/scripts/theme_parity.py | ours |
| A26 | cross-cutting | No link points at nothing and no asset goes missing. | check: plugins/qa-flow/scripts/link_audit.py | ours |
| A27 | cross-cutting | Performance budgets default to LCP at most 2.5 s, INP at most 200 ms and CLS at most 0.1 at the 75th percentile. | claim: C33 | web.dev *Web Vitals* |
| A28 | cross-cutting | Error messages say what went wrong and how to fix it; button labels lead with a verb. | claim: C29 | GOV.UK *Validation*; Polaris *Error messages* |
| A29 | template | A multi-step flow asks one question per page. | claim: C34 | GOV.UK *Question pages* |
| A30 | template | A page that asks several related things has a statement as its heading. | claim: C35 | GOV.UK *Question pages* |
| A31 | template | Every question page has a back link at the top. | claim: C36 | GOV.UK *Question pages* |
| A32 | template | The back link goes to the previous page the user was on. | claim: C37 | GOV.UK *Question pages* |
| A33 | template | No two pages in a flow share a heading. | claim: C38 | GOV.UK *Question pages* |
| A34 | template | The forward button on a question page is labelled "Continue", not "Next". | claim: C39 | GOV.UK *Question pages* |
| A35 | template | The check-answers page offers a Change link beside each section. | claim: C41 | GOV.UK *Check answers* |
| A36 | template | Each Change link carries hidden text naming what it changes. | claim: C42 | GOV.UK *Check answers* |
| A37 | template | One check-answers page comes immediately before the confirmation. | claim: C43 | GOV.UK *Check answers* |
| A38 | template | The check-answers page says the transaction is not complete until the user confirms. | claim: C44 | GOV.UK *Check answers* |
| A39 | template | After a change, Continue returns to the check-answers page. | claim: C45 | GOV.UK *Check answers* |
| A40 | template | A statement of what the user is confirming sits above the submit button. | claim: C46 | GOV.UK *Check answers* |
| A41 | template | The confirmation shows a reference number when there is one. | claim: C49 | GOV.UK *Confirmation pages* |
| A42 | template | The confirmation says what happens next and when. | claim: C50 | GOV.UK *Confirmation pages* |
| A43 | template | A task list is used only for a longer transaction of several tasks. | claim: C52 | GOV.UK *Complete multiple tasks* |
| A44 | template | A task page has one task list per group of tasks. | claim: C53 | GOV.UK *Complete multiple tasks* |
| A45 | template | Task names start with a verb. | claim: C54 | GOV.UK *Complete multiple tasks* |
| A46 | template | Every task shows its status. | claim: C55 | GOV.UK *Complete multiple tasks* |
| A47 | template | A task that cannot be started yet is not a link. | claim: C56 | GOV.UK *Complete multiple tasks* |
| A48 | template | Tasks can be completed in any order where possible. | claim: C57 | GOV.UK *Complete multiple tasks* |
| A49 | template | A user can always go back into a task to change an answer. | claim: C58 | GOV.UK *Complete multiple tasks* |
| A50 | template | The user moves on from the task list only when every task is Completed. | claim: C60 | GOV.UK *Task list* |
| A51 | template | A task list is not used for a flow that must be done in a fixed order. | claim: C64 | GOV.UK *Task list* |
| A52 | template | A task list is never the way answers are shown; a description list is. | claim: C65 | GOV.UK *Task list* |

## Arrives with its enforcement

These rules are not in the table because nothing makes them fail yet. Each joins it in the change
that builds its check:

- A screen declares its `Template:`, `Nav:` and `States:`, and a script refuses an unknown value:
  #2226 (the allowed values live in `plugins/rails-flow/reference/mockup-vocabulary.json`).
- No card inside a card: #2227.
- Keyboard focus is visible on every focusable element, since axe runs no focus rule: #2228.
- Each declared state renders distinct from loaded, with its own marker: #2229.
- Core Web Vitals measured against the project's budget in the QA gate: #2230.
- Judgement rules (density, content hierarchy, interaction feedback) get a recorded reviewer verdict
  a script requires: #2225.
