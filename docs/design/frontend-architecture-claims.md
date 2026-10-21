# External claims the #2220 outline would make (for doctrine-verifier)

Each row is one claim a framework page would state as established practice. None ships without a CONFIRMED verdict and citation; INCONCLUSIVE leaves it out. Our own choices among these are maintainer decisions recorded on #2220, not claims.

| # | Layer | Claim | Source to verify against |
|---|---|---|---|
| C1 | 1 | WCAG 2.4.1 (Level A) requires *a* mechanism to bypass repeated blocks; landmarks and headings are sufficient techniques, so a skip link is our rule, not WCAG's (**restated**) | WCAG 2.2 SC 2.4.1 |
| C2 | 1 | A page has at most one visible `main` landmark (HTML spec); landmark regions let assistive tech jump between regions | WAI-ARIA APG landmarks; HTML spec `main` |
| C3 | 1, 2 | Navigation that repeats across pages keeps the same relative order (Consistent Navigation, Level AA) | WCAG 2.2 SC 3.2.3 |
| C4 | 2 | A page offers more than one way to locate it within a set of pages (Multiple Ways, Level AA) | WCAG 2.2 SC 2.4.5 |
| C5 | 2 | The current location is exposed programmatically with `aria-current` | WAI-ARIA 1.2 `aria-current`; APG breadcrumb pattern |
| C6 | 2 | Nielsen's heuristics: visibility of system status; match between system and real world; consistency and standards | NN/g "10 Usability Heuristics" |
| C7 | 2 | Wayfinding: users must always be able to tell where they are, where they came from and where they can go | NN/g wayfinding / breadcrumbs articles |
| C8 | 2 | A view's state belongs in the URL so it is addressable and survives back/reload | Nielsen, "URL as UI" (1999); our own rule already at `page-anatomies.md:409` |
| C9 | 3 | List/index, detail, create/edit, dashboard, settings and empty/first-run are the recurring page templates | **As a set, likely INCONCLUSIVE**: GOV.UK page patterns are question/confirmation/start/task-list/check-answers. The six templates are a maintainer decision; verify only individual templates against Carbon |
| C10 | 3 | A first-run empty state should say what will appear and how to start | Carbon empty states; NN/g empty-state guidance |
| C11 | 4 | Compose layouts from a few layout primitives (stack, cluster, sidebar, switcher, grid) instead of per-page layout CSS | Every Layout (the named primitives) |
| C12 | 4 | Interfaces decompose into atoms, molecules, organisms, templates and pages | Atomic Design (Brad Frost) |
| C13 | 5 | A system should show status and recover from errors: error messages say what went wrong and how to fix it | NN/g heuristics 1 and 9 |
| C14 | 5 | An error identified in text, with a suggestion where known (Error Identification, A; Error Suggestion, AA) | WCAG 2.2 SC 3.3.1, 3.3.3 |
| C15 | 5 | Status messages are exposed to assistive tech without moving focus (`role=status`, `aria-live`) | WCAG 2.2 SC 4.1.3 |
| C16 | 5 | Skeleton placeholders reserve space when content size is known, avoiding layout shift | web.dev CLS; Carbon/other loading pattern (already in `components.md:1645` as convention) |
| C17 | 5 | A 403/permission-denied screen explains the restriction and a next step, and is distinct from an empty result | GOV.UK / Carbon / NN/g — Carbon's empty-state pattern may carry a no-permission variant; keep out unless it does |
| C18 | 6 | Contrast minimum 4.5:1 text, 3:1 large text and UI components | WCAG 2.2 SC 1.4.3, 1.4.11 |
| C19 | 6 | Target size minimum 24×24 CSS px (new in 2.2) | WCAG 2.2 SC 2.5.8 |
| C20 | 6 | Focus is visible and not obscured by sticky chrome (2.2) | WCAG 2.2 SC 2.4.7, 2.4.11 |
| C21 | 6 | Reflow at 320 CSS px wide without two-dimensional scrolling | WCAG 2.2 SC 1.4.10 |
| C22 | 6 | An ordered heading outline helps navigation (1.3.1; G141 is a technique) | **One `h1` is not a WCAG or HTML requirement** (the HTML outline algorithm was dropped); it stays our rule |
| C23 | 6 | Core Web Vitals "good" thresholds: LCP ≤ 2.5 s, INP ≤ 200 ms, CLS ≤ 0.1 at the 75th percentile | web.dev Core Web Vitals |
| C24 | 6 | Interaction responsiveness: INP "good" is ≤ 200 ms (use this single number); the 0.1 s "instant" limit is NN/g's | web.dev INP; NN/g response times |
| C25 | 7 | Designing in a mock-up before implementation catches interface defects cheaper than in code | **no authoritative source; this is our decision (#2211), not a claim** |

Notes: C8, C17, C22 and C25 are flagged because they are likely INCONCLUSIVE or are our own choices; the outline does not depend on them. Performance budget numbers beyond C23 are a maintainer decision.
| C26 | 5 | Forms: inline error next to the field plus an error summary at the top, required fields marked, validate on submit or blur not per keystroke | GOV.UK error summary and validation patterns; WCAG 3.3.1-3.3.3 |
| C27 | 5 | Notifications: choose inline, toast, banner or badge by urgency and persistence; toasts must not carry the only copy of an error | Carbon notification pattern; Polaris banner/toast guidance; WCAG 4.1.3 |
| C28 | 5 | Permissions: hide vs disable an affordance the user cannot use, and say why when disabled | Atlassian / Polaris guidance — likely INCONCLUSIVE; verify before use |
| C29 | 6 | Content design: plain-language error messages and verb-led button labels | GOV.UK content design; Polaris content guidelines |
| C30 | 6 | Internationalisation: allow for text expansion, RTL and locale formats | Material and Polaris internationalisation pages |
| C31 | 2 | A route change in a client-routed interface moves focus to the new view | WCAG 2.4.3 (Focus Order) and a named framework or APG source; verify wording |
| C32 | 5 | Confirm destructive actions or, better, offer undo | NN/g heuristic 3 (user control and freedom) |

Notes: C8 is now expected to confirm. C22, C25, C28 are likely INCONCLUSIVE or our own choices; C9 is a maintainer decision as a set. Additional limits recorded in the outline: 1.4.3/1.4.11 (4.5:1 vs 3:1), 2.5.8 exceptions, 2.4.11 (AA means entirely hidden), 1.4.10 exempts two-dimensional content, 2.4.5 exempts steps in a process.
| C33 | 6 | Performance budgets default to the Core Web Vitals "good" thresholds (LCP ≤ 2.5 s, INP ≤ 200 ms, CLS ≤ 0.1, 75th percentile); a project may override them in its own config | web.dev Core Web Vitals (the thresholds); the default and the override are a maintainer decision (a2, 2026-10-21) |

Maintainer decisions recorded 2026-10-21 (claude-skills-a2, for the owner's review): (1) a screen's state list lives in the mock-up record, a `States:` line beside #2211's `Shell:` line; (2) performance budgets default to C33; (3) the six page templates are our decision, not a citation (C9 is not sent to the verifier); (4) modal-driven CRUD moves out of the neutral page to Hotwire (#2223). C25 is likewise our decision.

## Verdicts (doctrine-verifier, 2026-10-21)

Three verifier runs fetched the sources. C = CONFIRMED, R = REFUTED (wording must change), I = INCONCLUSIVE (stays out as worded), D = maintainer decision (not verified). "Use as" is the wording that may ship.

| # | Verdict | Citation | Use as |
|---|---|---|---|
| C1 | C | w3.org/WAI/WCAG22/Understanding/bypass-blocks.html | 2.4.1 (A) requires *a* bypass mechanism; landmarks (ARIA11) and headings (H69) suffice, a skip link (G1) is one technique. The skip link stays our rule. |
| C2 | C | html.spec.whatwg.org grouping-content `main`; APG landmark-regions | at most one non-hidden `main` |
| C3 | C | WCAG22 Understanding consistent-navigation | repeated navigation keeps the same relative order (AA, 3.2.3) |
| C4 | C | WCAG22 #multiple-ways | more than one way to locate a page, except process steps (AA, 2.4.5) |
| C5 | C | WAI-ARIA 1.2 aria-current; APG breadcrumb | `aria-current="page"` on the current item |
| C6 | C | nngroup.com/articles/ten-usability-heuristics | heuristics 1, 2, 4 |
| C7 | C, reword | nngroup.com/articles/breadcrumbs | where the user is in the hierarchy and where they can go; NOT "where they came from" (breadcrumbs are not history) |
| C8 | I | nngroup.com/articles/url-as-ui | NN/g covers stable, readable URLs, not view-state-in-URL. Not cited for that; the state-in-URL rule stays our own (`page-anatomies.md:409`) |
| C9 | D | — | the six page templates are our decision |
| C10 | C | carbondesignsystem.com/patterns/empty-states-pattern | say specifically what will appear and the next action |
| C11 | C | every-layout.dev/layouts | the named primitives exist (Stack, Cluster, Sidebar, Switcher, Grid, …); "instead of per-page layout CSS" is our framing |
| C12 | C, narrow | atomicdesign.bradfrost.com/chapter-2 | "a methodology of five stages: atoms, molecules, organisms, templates, pages"; its "template" is a skeleton, ours differs |
| C13 | C | nngroup ten heuristics (1, 9) | keep users informed; indicate the problem and suggest a solution |
| C14 | C | WCAG22 3.3.1 (A), 3.3.3 (AA) | error identified in text; suggestion where known |
| C15 | C | WCAG22 Understanding status-messages | status messages reach assistive tech without taking focus (ARIA22 `role=status`); `aria-live` is not the cited technique |
| C16 | I | web.dev/articles/cls | web.dev never says "skeleton"; may say only "reserve space for content to avoid layout shift". Our skeleton rule (`components.md:1645`) stays labelled convention |
| C17 | I (partial) | carbondesignsystem.com empty-states-pattern | Carbon only: a "permissions issue" empty state suggests how to request access. Re-verify as a Carbon claim before use |
| C18 | C | WCAG22 1.4.3, 1.4.11 | 4.5:1 text, 3:1 large text and UI components |
| C19 | C | WCAG22 2.5.8 | 24×24 CSS px minimum (AA, new in 2.2), with its exceptions |
| C20 | C, correction | WCAG22 2.4.7, 2.4.11 | focus visible; focus "not entirely hidden" by author content (not "not obscured") |
| C21 | C | WCAG22 1.4.10 | no 2-D scrolling at 320 CSS px; exceptions include data tables, maps, video |
| C22 | C, narrow | WCAG22 Techniques G141 | G141 is an *advisory* technique for 1.3.1. One `h1` is NOT verified and stays our rule |
| C23 | C | web.dev/articles/vitals | LCP ≤ 2.5 s, INP ≤ 200 ms, CLS ≤ 0.1 at the 75th percentile |
| C24 | C | web.dev/articles/inp; nngroup response-times | INP ≤ 200 ms is "good"; NN/g's 0.1 s is the "instant" limit. Use the single INP number |
| C25 | D | — | mock-up first is our decision (#2211) |
| C26 | R (partly) | design-system.service.gov.uk/patterns/validation | inline error next to the answer plus an error summary: confirmed. GOV.UK says do NOT validate on blur ("submit" only) and gives no required-marking rule; required marking cites WCAG 3.3.2 once verified |
| C27 | C (Carbon only) | carbondesignsystem.com/patterns/notification-pattern | critical messages must not auto-dismiss. "A toast must not carry the only copy of an error" is inference; drop it |
| C28 | I | carbondesignsystem.com/patterns/disabled-states | Atlassian/Polaris unverified. Carbon says hide for no-permission, disable for temporary and say how to enable. Re-verify as a Carbon-only claim |
| C29 | C | polaris.shopify.com/content/error-messages; GOV.UK validation | lead buttons with a strong verb; say what went wrong and how to fix it |
| C30 | I (partly) | m2.material.io/go/design-bidirectionality | only RTL mirroring confirmed; text expansion and locale formats have no source. Narrow to RTL or find sources |
| C31 | I as worded | web.dev/managed-focus | WCAG 2.4.3 does not mention route changes. web.dev supports "direct focus to a heading in the newly loaded content"; re-verify as a web.dev claim |
| C32 | R (wording) | nngroup ten heuristics (3, 5) | H3 supports undo and a marked exit; confirmation belongs to H5 (error prevention) |
| C33 | C (thresholds) | web.dev/articles/vitals | thresholds as C23; the default-plus-override is our decision |

**Tally (33):** 23 CONFIRMED (of which 7 need rewording or narrowing: C7, C12, C15, C20, C22, C27, C33), 2 REFUTED as worded (C26, C32), 6 INCONCLUSIVE (C8, C16, C17, C28, C30, C31), 2 maintainer decisions (C9, C25). Three INCONCLUSIVE claims (C17, C28, C31) have a real source for a narrower wording (Carbon, Carbon, web.dev) and are candidates for one re-verification pass; the rest stay out.

## Re-verification of the narrowed wording (doctrine-verifier, 2026-10-21)

| # | Verdict | Citation | Use as |
|---|---|---|---|
| C17' | CONFIRMED | carbondesignsystem.com/patterns/empty-states-pattern/ | Carbon's empty states include a permissions case: "The user does not have permission to view the data", with the action "Suggest steps or process to request access." Cite Carbon only |
| C28' | PARTIAL, reworded | carbondesignsystem.com/patterns/disabled-states/ | Carbon hides an element the user lacks permission to "view, interact with, or take action on"; it disables for temporary dependencies (it does not say "only"). The enable instructions belong to the optional inline notification, which "should describe how the user can enable or re-enable the disabled component". Cite Carbon only |
| C31' | CONFIRMED | developer.chrome.com/docs/lighthouse/accessibility/managed-focus (web.dev/managed-focus redirects here) | after a route change that fetches new content, "find a good heading in the newly loaded content and direct focus to it". Cite the developer.chrome.com URL |

**Updated tally (33):** 25 CONFIRMED (C17 and C31 join the 23; C28 ships only in its reworded Carbon form, counted below), 2 REFUTED as worded (C26, C32), 3 INCONCLUSIVE and out (C8, C16, C30), 1 PARTIAL reworded (C28), 2 maintainer decisions (C9, C25). Total 33.
