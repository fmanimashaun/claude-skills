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
