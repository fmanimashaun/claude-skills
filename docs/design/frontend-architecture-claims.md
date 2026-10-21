# External claims the #2220 outline would make (for doctrine-verifier)

Each row is one claim a framework page would state as established practice. None ships without a CONFIRMED verdict and citation; INCONCLUSIVE leaves it out. Our own choices among these are maintainer decisions recorded on #2220, not claims.

| # | Layer | Claim | Source to verify against |
|---|---|---|---|
| C1 | 1 | A skip link to main content is a Level A obligation (Bypass Blocks, 2.4.1) | WCAG 2.2 SC 2.4.1 |
| C2 | 1 | A page has one `main` landmark; landmark regions let assistive tech jump between regions | WAI-ARIA APG landmarks; HTML spec `main` |
| C3 | 1, 2 | Navigation that repeats across pages keeps the same relative order (Consistent Navigation, Level AA) | WCAG 2.2 SC 3.2.3 |
| C4 | 2 | A page offers more than one way to locate it within a set of pages (Multiple Ways, Level AA) | WCAG 2.2 SC 2.4.5 |
| C5 | 2 | The current location is exposed programmatically with `aria-current` | WAI-ARIA 1.2 `aria-current`; APG breadcrumb pattern |
| C6 | 2 | Nielsen's heuristics: visibility of system status; match between system and real world; consistency and standards | NN/g "10 Usability Heuristics" |
| C7 | 2 | Wayfinding: users must always be able to tell where they are, where they came from and where they can go | NN/g wayfinding / breadcrumbs articles |
| C8 | 2 | A view's state belongs in the URL so it is addressable and survives back/reload | a named source (web.dev / MDN history) — **candidate for removal if no source confirms**; we already hold it as our own rule `page-anatomies.md:409` |
| C9 | 3 | List/index, detail, create/edit, dashboard, settings and empty/first-run are the recurring page templates | Carbon patterns; GOV.UK Design System page templates (name which pages) |
| C10 | 3 | A first-run empty state should say what will appear and how to start | Carbon empty states; NN/g empty-state guidance |
| C11 | 4 | Compose layouts from a few layout primitives (stack, cluster, sidebar, switcher, grid) instead of per-page layout CSS | Every Layout (the named primitives) |
| C12 | 4 | Interfaces decompose into atoms, molecules, organisms, templates and pages | Atomic Design (Brad Frost) |
| C13 | 5 | A system should show status and recover from errors: error messages say what went wrong and how to fix it | NN/g heuristics 1 and 9 |
| C14 | 5 | An error identified in text, with a suggestion where known (Error Identification, A; Error Suggestion, AA) | WCAG 2.2 SC 3.3.1, 3.3.3 |
| C15 | 5 | Status messages are exposed to assistive tech without moving focus (`role=status`, `aria-live`) | WCAG 2.2 SC 4.1.3 |
| C16 | 5 | Skeleton placeholders reserve space when content size is known, avoiding layout shift | web.dev CLS; Carbon/other loading pattern (already in `components.md:1645` as convention) |
| C17 | 5 | A 403/permission-denied screen explains the restriction and a next step, and is distinct from an empty result | GOV.UK / Carbon / NN/g — **likely INCONCLUSIVE; keep out unless a source says so** |
| C18 | 6 | Contrast minimum 4.5:1 text, 3:1 large text and UI components | WCAG 2.2 SC 1.4.3, 1.4.11 |
| C19 | 6 | Target size minimum 24×24 CSS px (new in 2.2) | WCAG 2.2 SC 2.5.8 |
| C20 | 6 | Focus is visible and not obscured by sticky chrome (2.2) | WCAG 2.2 SC 2.4.7, 2.4.11 |
| C21 | 6 | Reflow at 320 CSS px wide without two-dimensional scrolling | WCAG 2.2 SC 1.4.10 |
| C22 | 6 | One `h1` and an ordered heading outline | WCAG technique G141 / HTML spec — **note: one `h1` is advice, not a WCAG requirement; verify wording** |
| C23 | 6 | Core Web Vitals "good" thresholds: LCP ≤ 2.5 s, INP ≤ 200 ms, CLS ≤ 0.1 at the 75th percentile | web.dev Core Web Vitals |
| C24 | 6 | Interaction feedback: respond to input within about 100 ms to feel instantaneous | NN/g response times; web.dev INP |
| C25 | 7 | Designing in a mock-up before implementation catches interface defects cheaper than in code | **no authoritative source; this is our decision (#2211), not a claim** |

Notes: C8, C17, C22 and C25 are flagged because they are likely INCONCLUSIVE or are our own choices; the outline does not depend on them. Performance budget numbers beyond C23 are a maintainer decision.
