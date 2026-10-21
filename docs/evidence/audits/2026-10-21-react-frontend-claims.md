# React frontend architecture: verified claims (#2222, phase 1)

The evidence for nextjs-stack's React frontend-architecture skill and detector (#2222, the owner's request of 2026-10-21). Nothing here is doctrine yet. A claim becomes doctrine only if its verdict is CONFIRMED, and only with the corrected wording shown. The Hotwire twin is `docs/evidence/audits/2026-10-21-hotwire-frontend-claims.md` (#2223, branch `feature/2223-hotwire-claims`). Both tables use the same eight layers, so they can be compared row for row. The shared layers are #2220's.

**Versions in scope** (npm `latest` and the vendors' release pages, checked 2026-10-21): React 19.3.x (19.3.0 on react.dev/versions; 19.3.1 on npm); Next.js 16.4.x (16.4.2); eslint-plugin-react-hooks 7.1.1; eslint-plugin-react 7.37.5; @next/eslint-plugin-next 16.4.2. React Compiler 1.0 has been stable since 2025-10-07. It is a separate build tool, not part of a React version.

**Verification:** `doctrine-verifier`, three passes on 2026-10-21, against react.dev, nextjs.org/docs and the official React and Next.js blogs. The lint column was first read from the plugins' docs; it is now **measured** ("Measured lint run" below), and where the two disagreed the measurement wins (it found that `@next/next/no-html-link-for-pages` does not cover `app/`). **Recommended?** means in the plugin's recommended preset. `eslint-config-next` turns on the recommended sets of `eslint-plugin-react`, `eslint-plugin-react-hooks` and the Next plugin, so in a Next app the recommended rules are on by default.

**Skill coverage:** `plugins/nextjs-stack/skills/react/SKILL.md` (#2222) states every CONFIRMED row with its enforcement; before it, none. nextjs-stack's one skill (`nextjs-supabase-vercel`) covers only the key and environment-variable seam.

Verdict key: **C** confirmed as written · **C*** confirmed with the correction applied (the claim below is the corrected wording) · **I** inconclusive (held out) · **R** refuted.

## 1. Composition

| id | claim (corrected wording) | failure | fix | verdict · source | upstream rule (recommended?) |
|---|---|---|---|---|---|
| R1 (C5) | When an intermediate component only forwards props it does not use, pass JSX as `children` instead; reach for context only when plain props and composition do not fit. | Prop drilling couples every layer in between. | Compose through `children`. | C · react.dev/learn/passing-data-deeply-with-context | none (heuristic: an unused forwarded prop in one file) |
| R2 (C8) | Declare components at the top level, never inside another component's body: a nested definition is a new component type on every render, so React remounts it and its state is lost. | Lost state and focus on every render. | Move the component to the top level. | C · react.dev/learn/preserving-and-resetting-state | `react-hooks/static-components`, `react-hooks/component-hook-factories` (yes); `react/no-unstable-nested-components` (no). Mostly covered; gaps: components passed as props via `allowAsProps`, runtime-chosen types |
| R3 (C11) | A component should be concerned with one thing; when it grows, decompose it (separation of concerns, as react.dev names it). | Components that are hard to change and test. | Split by responsibility. | C · react.dev/learn/thinking-in-react (no Next.js guidance) | `react/no-multi-comp` (no); size rules are stand-ins; judgement call |
| R4 (C7) | A list item's `key` must be stable and unique among siblings and must not change: an index key on a list that reorders, filters or inserts gives items the wrong state, and a key generated during render (`Math.random()`) remounts every item. An index is acceptable for a list that never reorders. | Wrong state attached to rows; remounts. | A stable id from the data. | C · react.dev/learn/rendering-lists | `react/jsx-key` (yes); `react/no-array-index-key` (no; cannot tell whether a list reorders); `react-hooks/purity` (yes; catches `Math.random` in render, by inference); nothing detects duplicate sibling keys |
| R5 (C13) | Pages and layouts are Server Components by default; a component needs `"use client"` only for state, effects, custom hooks, event handlers or browser-only APIs. | Client JavaScript shipped for no reason. | Keep the Server Component default. | C* · nextjs.org/docs/app/getting-started/server-and-client-components | none |

## 2. Shell, navigation and page templates

| id | claim | failure | fix | verdict · source | upstream rule |
|---|---|---|---|---|---|
| R6 (C17) | Navigate between internal routes with `<Link>`, which does client-side navigation and prefetches (production only); a plain `<a>` to an internal route causes a full page load. Prefetching depends on the version: by default a static route is prefetched fully and a dynamic route only down to its nearest `loading.js`. | A full reload; lost client state; slower navigation. | `<Link>`. | C* · nextjs.org/docs/app/api-reference/components/link | `@next/next/no-html-link-for-pages` (yes; whether it covers `app/` routes is unverified) |
| R7 (C19) | `error.js` is a Client Component that isolates an error to its route segment (errors bubble to the nearest boundary); `not-found.js` renders for `notFound()`. Boundaries do not catch errors in event handlers or async code. Current docs name the props `error, retry`. | One failing segment blanks the whole page. | A segment-level `error.js` / `not-found.js`. | C* · nextjs.org/docs/app/getting-started/error-handling | none |

## 3. Regions and flow

| id | claim | failure | fix | verdict · source | upstream rule |
|---|---|---|---|---|---|
| R8 (C9) | Put `"use client"` on the smallest interactive leaves, not on a layout or page. A high boundary does NOT give up server rendering (Client Components still prerender HTML), but it loses Server Components for that subtree and ships more JavaScript. The boundary covers a module's imports and the components it renders directly, not Server Components passed to it as `children` or props. | A larger bundle; no Server Components where they would help. | Push the directive down; pass Server Components as `children`. | C* · nextjs.org/docs/app/getting-started/server-and-client-components | none (`@next/next/no-async-client-component` is adjacent only). Partly mechanical: `"use client"` on layout/page files, or on modules with no hooks, handlers or browser APIs |
| R9 (C14) | Props passed from a Server Component to a Client Component must be serializable: the only functions allowed are Server Functions (or functions exported from client-marked modules), and no class instances (other than built-ins) or null-prototype objects. | A runtime error at the boundary. | Pass plain data; pass a Server Function for actions. | C* · react.dev/reference/rsc/use-client | none |
| R10 (C15) | Wrap a slow part in `<Suspense>` (preferably close to the data), or add `loading.js` to a segment, to stream the rest of the page instead of blocking on the slowest fetch. Caveat: a layout that reads uncached data blocks, because it does not fall back to its own segment's `loading.js`. | The whole page waits for its slowest part. | `<Suspense>` near the data. | C* · nextjs.org/docs/app/getting-started/fetching-data | none |

## 4. Data and state

| id | claim | failure | fix | verdict · source | upstream rule |
|---|---|---|---|---|---|
| R11 (C1) | Compute a value derived from props or state during render, not in an Effect that stores it with `setState`, which renders once with a stale value then re-renders. Use `useMemo` only if the computation is expensive (measure first: react.dev's bar is creating or looping over thousands of objects). | An extra render with a stale value. | Compute during render. | C* · react.dev/learn/you-might-not-need-an-effect | `react-hooks/set-state-in-effect` (yes; flags synchronous `setState` in an effect, cannot tell derived state from a legitimate sync) |
| R12 (C2) | To reset state when a prop changes, give the component a `key` tied to that prop; adjusting state during render beats an Effect, but most components need neither. | Stale state on the first render after the change. | `key`. | C · react.dev/learn/you-might-not-need-an-effect | `react-hooks/set-state-in-effect` (yes; does not recognise the intent or suggest `key`) |
| R13 (C3) | When two components must show the same changing data, move the state to their closest common parent and pass it down as props, a single source of truth; do not duplicate state. | Copies that disagree. | Lift state up. | C · react.dev/learn/sharing-state-between-components | none; judgement call |
| R14 (C4) | Keep state local; do not lift it higher than you need to: state placed higher than needed widens what re-renders. | Wider re-renders than necessary. | Colocate state. | C* · react.dev/reference/react/useMemo | none; needs a usage graph |
| R15 (C6) | Every component that reads a context re-renders when its value changes, and an object or function created inline as a provider's `value` is new on every render. Memoise the value (`useMemo`/`useCallback`). (Splitting a context by how often it changes is community practice, not react.dev guidance; `memo` does not stop a context re-render.) | Every consumer re-renders on every provider render. | Memoise the value. | C* · react.dev/reference/react/useContext | `react/jsx-no-constructed-context-values` (no; misses values built through helpers; React 19 `<Ctx value>` form unverified) |
| R16 (C10) | In the App Router, fetch the data a page needs in a Server Component (async/await), not in a client Effect: Effects do not run on the server and create network waterfalls. In client code, use `use` or a library such as SWR or React Query; an Effect that fetches needs cleanup to ignore stale responses. | Waterfalls; fetching after hydration; race conditions. | Fetch on the server. | C* · react.dev/learn/synchronizing-with-effects; nextjs.org/docs/app/getting-started/fetching-data | none; detectable: `fetch` inside `useEffect` in a client module, and missing cleanup |
| R17 (C16) | Independent requests awaited one after another are sequential; start them together (`Promise.all`, or `Promise.allSettled` when one failure must not fail the rest). | A waterfall. | Parallel fetching. | C* · nextjs.org/docs/app/getting-started/fetching-data | none |
| (C18) | URL search params as the home of shareable state (filters, tabs, pagination). | — | — | **I** · only the Learn course (nextjs.org/learn/dashboard-app/adding-search-and-pagination) lists bookmark/share as benefits; no reload or back/forward rule. Held out unless narrowed to bookmark/share, or recorded as our own design decision on #2222. | none |

## 5. UX

The neutral UX contract (loading, empty, error, optimistic and focus states) is #2220's. React's share is the streaming and error-boundary mechanics in layers 2 and 3 (R7, R10), and image and font loading:

| id | claim | failure | fix | verdict · source | upstream rule |
|---|---|---|---|---|---|
| R18 (C21) | `next/image` and `next/font` load images and fonts without layout shift (remote images need `width`/`height` or `fill`); a raw `<img>` loses that. | Layout shift; slower loading. | `next/image`, `next/font`. | C* · nextjs.org/docs/app/getting-started/images; /fonts | `@next/next/no-img-element`, `google-font-display`, `google-font-preconnect` (yes) |

## 6. Performance

| id | claim | failure | fix | verdict · source | upstream rule |
|---|---|---|---|---|---|
| R19 (C12) | `useMemo`, `useCallback` and `memo` are performance optimisations only: code must work without them; if it does not, fix the cause. Rely on the React Compiler for new code; keep manual memoisation as an escape hatch (e.g. Effect dependencies), and do not strip existing memoisation without testing. | Memoisation hiding a correctness or structure problem. | Fix the cause. | C* · react.dev/reference/react/useMemo; react.dev/blog/2025/10/07/react-compiler-1 | `react-hooks/preserve-manual-memoization`, `react-hooks/use-memo` (yes; they check memoisation is correct, not whether it is needed); judgement call |
| R20 (C20) | `next/dynamic` / `React.lazy` defer a Client Component's code until needed, shrinking the initial bundle. Server Components are code-split automatically, and a Server Component that dynamically imports a Client Component gets no automatic splitting from it. | A larger initial bundle. | Lazy-load heavy client components. | C* · nextjs.org/docs/app/guides/lazy-loading | none |

Also performance: R2 (remounts), R4 (keys), R8 (bundle), R10 (streaming), R15 (context re-renders), R16/R17 (waterfalls), R18 (images).

## 7. Security (the frontend's share)

nextjs-stack's security surface (checklist, scanners, boundary patterns) is **#2210**. These are only the rules the frontend architecture must state, and they defer to #2210 for the rest.

| id | claim | failure | fix | verdict · source | upstream rule |
|---|---|---|---|---|---|
| R21 (C22) | Use `dangerouslySetInnerHTML` only with trusted and sanitised data: it bypasses React's escaping, so untrusted markup is an XSS vulnerability. | XSS. | Sanitise, or render as text. | C* · react.dev/reference/react-dom/components/common | `react/no-danger` (no; recommended has only `no-danger-with-children`, a different defect) |
| R22 (C23) | Treat every Server Action as reachable by a direct POST: verify authentication, authorisation and resource ownership inside each action. A page-level check does not cover the actions defined in that page. | Unauthorised mutation; insecure direct object reference. | Check inside each action. | C* · nextjs.org/docs/app/guides/data-security | none |
| R23 (C24) | Anything passed to a Client Component, and every `NEXT_PUBLIC_` variable, reaches the browser; keep secrets and server-only data in Server Components, and mark server-only modules with `import "server-only"` (a build error if imported into client code; React's taint APIs are an optional extra layer). | Secrets in the client bundle. | `server-only`; keep data server-side. | C* · nextjs.org/docs/app/getting-started/server-and-client-components; /guides/data-security | none (the guarantee is the build error) |

## 8. Anti-patterns that bite: where a check exists

| anti-pattern | rows | caught upstream (on by default in a Next app?) | our check needed |
|---|---|---|---|
| components defined inside components | R2 | yes (react-hooks, yes) | only the gaps listed in R2 |
| derived state / prop reset in an Effect | R11, R12 | partly (react-hooks/set-state-in-effect, yes) | no; upstream flags the shape, the skill names the fix |
| index or random keys | R4 | partly (jsx-key yes; no-array-index-key no) | maybe: turn on `no-array-index-key` where lists reorder (judgement) |
| inline context value | R15 | partly (`jsx-no-constructed-context-values`, not on by default) | enable the upstream rule rather than write one |
| `"use client"` too high | R8 | no | **yes**: flag the directive on layout/page files and on modules with no hooks, handlers or browser APIs |
| fetch in a client Effect | R16 | no | **yes**: `fetch` inside `useEffect` in an App Router client module; missing cleanup |
| sequential independent awaits | R17 | no | possible (consecutive independent `await`s in a Server Component), heuristic |
| internal `<a>`, raw `<img>`, font loading | R6, R18 | yes (Next plugin, yes) | no |
| unsanitised `dangerouslySetInnerHTML` | R21 | partly (`react/no-danger`, not on by default) | enable upstream; sanitiser use is judgement |
| Server Action without an auth check | R22 | no | defer to #2210 |
| lift/colocate, god components, memo as a band-aid | R13, R14, R3, R19 | no (judgement) | no: doctrine only |

## Measured lint run (2026-10-21)

One hand-written fixture per anti-pattern, in an App Router project (`app/`), linted by eslint 9.39.5 with `eslint-config-next` 16.4.2 (`core-web-vitals`) and its bundled react-hooks 7.1.1, eslint-plugin-react 7.37.5 and @next/eslint-plugin-next 16.4.2. Then again with the three off-by-default rules turned on.

| fixture | default Next preset | with the three rules on |
|---|---|---|
| derived state in an Effect (R11) | `react-hooks/set-state-in-effect` | same |
| prop reset in an Effect (R12) | `react-hooks/set-state-in-effect` | same |
| component inside a component (R2) | `react-hooks/static-components` | same |
| missing key (R4) | `react/jsx-key` | same |
| `Math.random()` key (R4) | `react-hooks/purity` | same |
| index key (R4) | nothing | `react/no-array-index-key` |
| inline context value (R15) | nothing | `react/jsx-no-constructed-context-values` |
| inline context value, React 19 `<Ctx value>` (R15) | nothing | `react/jsx-no-constructed-context-values` |
| `dangerouslySetInnerHTML` (R21) | nothing | `react/no-danger` |
| raw `<img>` (R18) | `@next/next/no-img-element` | same |
| internal `<a href="/dashboard">` in `app/` (R6) | **nothing** (`no-html-link-for-pages` reads `pages/` only) | nothing |
| `fetch` in a client `useEffect` (R16) | nothing | nothing |
| `"use client"` on a route layout (R8) | nothing | nothing |
| sequential independent awaits in a page (R17) | nothing | nothing |
| Server Action with no auth check (R22) | nothing | nothing |

So nextjs-stack runs the three rules (`react-lint-off-by-default`, via `check_react_lint.py`: on this fixture project, exactly those four findings and no other rule) and checks itself only what nothing upstream catches: R8 (client route files), R16 (fetch in a client Effect) and R6 (internal `<a>`), in `check_react_patterns.py` (`react-patterns`), which on the fixture project reports exactly those three. R17 and R22 are not mechanised: R17 is verified advice (a recorded-verdict rule once #2225 lands), R22 belongs to the security surface (#2210).

## False positives, measured (2026-10-21)

`check_react_patterns.py` over the 27 Next.js apps in the licensed design corpora (Tailwind UI and Flowbite templates: 908 source files, 62 with `useEffect`), read-only. flo-it-ui was the first choice, but it has no `"use client"` module yet.

| rule | fired | judged by hand | outcome |
|---|---|---|---|
| a `"use client"` module with no hook, handler, browser API or context | 9 | 4 certain false positives (a `Providers` wrapping `next-themes`' `ThemeProvider`, which needs the client because it renders a third-party context provider); 5 render `flowbite-react` components, undecidable from the file | **dropped** as a mechanical rule: a third-party import can be the reason a module needs the client, and source text cannot see it. It is now verified advice (`server-components-by-default`), a recorded-verdict rule once #2225 lands. |
| `use-client-route-file` | 3 | three client mail pages built from form inputs: deliberate trade-offs, exactly what R8 asks to be stated | kept, satisfied by **declaration** (`react-architecture: client-route -- <reason>`) |
| `fetch-in-effect` | 0 | an independent count found 0 files with both `useEffect` and `fetch(` | 0 false positives; the corpora contain no true positive, so detection rests on the fixtures |
| `internal-anchor` | 0 | an independent count found 0 internal `<a href="/...">` | as above |

The scan first read only `app/`, while 303 of the corpora's 335 client files live outside it (`components/`, `src/components/`); the rules other than route files now read the whole source tree, and the numbers above are from the widened scan. The guard on the script also found a real bug: comment stripping erased `//` inside strings (so `href="//cdn..."` and `https://` vanished); it is now string-aware.

## Enforcement by claim (owner ruling on #2222: "everything must be enforced")

| claim | enforcement |
|---|---|
| R2, R4 (missing/random key), R11, R12, R18 | default lint (on in every Next app) |
| R4 (index key), R15, R21 | `react-lint-off-by-default` (nextjs-stack `checks.json`) |
| R6, R16 | `react-patterns` |
| R8 | `react-patterns` + required declaration |
| R9 | the framework (runtime error) |
| R23 | the framework (`server-only` build error) |
| R22 | the security surface, #2210 |
| R1, R3, R5, R7, R10, R13, R14, R17, R19, R20 | verified advice now, each citing its CONFIRMED claim; a recorded-verdict rule once rails-flow #2225 lands (the coordinator's call on the #2243 review, under the owner's "advice is fine when tested against a standard") |
| C18 | not shipped (INCONCLUSIVE) |

## Verified quotes (2026-10-21)

The phrase each row rests on, quoted exactly. Each phrase was checked against the page itself, not the verifier's report (#2233 found the verifier inventing quotes): the page was fetched with `curl -sL`, its scripts and tags stripped, entities unescaped, typographic quotes and backticks normalised and whitespace collapsed, and the phrase had to occur verbatim. All 24 did. One verifier "quote" did not: for R14 it reported "don't lift state up any higher than you need to", but the page says "any further than necessary" (the row below has the page's words).

| row | exact phrase on the page | source |
|---|---|---|
| R1 | "pass JSX as children" | https://react.dev/learn/passing-data-deeply-with-context |
| R2 | "always declare component functions at the top level, and don't nest their definitions" | https://react.dev/learn/preserving-and-resetting-state |
| R3 | "a component should ideally only be concerned with one thing" | https://react.dev/learn/thinking-in-react |
| R4 | "do not generate keys on the fly" | https://react.dev/learn/rendering-lists |
| R5 | "By default, layouts and pages are Server Components" | https://nextjs.org/docs/app/getting-started/server-and-client-components |
| R6 | "Prefetching is only enabled in production" | https://nextjs.org/docs/app/api-reference/components/link |
| R7 | "Error boundaries must be Client Components" | https://nextjs.org/docs/app/getting-started/error-handling |
| R8 | "instead of marking large parts of your UI as Client Components" | https://nextjs.org/docs/app/getting-started/server-and-client-components |
| R9 | "Prop values passed from a Server Component to Client Component must be serializable" | https://react.dev/reference/rsc/use-client |
| R10 | "wrap the fetching component in <Suspense> to stream fresh data at request time" | https://nextjs.org/docs/app/getting-started/fetching-data |
| R11 | "it does an entire render pass with a stale value" | https://react.dev/learn/you-might-not-need-an-effect |
| R12 | "React will recreate the DOM and reset the state" | https://react.dev/learn/you-might-not-need-an-effect |
| R13 | "move it to their closest common parent, and then pass it down to them via props" | https://react.dev/learn/sharing-state-between-components |
| R14 | "Prefer local state and don't lift state up any further than necessary" | https://react.dev/reference/react/useMemo |
| R15 | "pointing at a different function" | https://react.dev/reference/react/useContext |
| R16 | "Effects don't run on the server" | https://react.dev/learn/synchronizing-with-effects |
| R17 | "can still be sequential" | https://nextjs.org/docs/app/getting-started/fetching-data |
| R18 | "Preventing layout shift automatically when images are loading" | https://nextjs.org/docs/app/getting-started/images |
| R19 | "only rely on useMemo as a performance optimization" | https://react.dev/reference/react/useMemo |
| R20 | "decreasing the amount of JavaScript needed to render a route" | https://nextjs.org/docs/app/guides/lazy-loading |
| R21 | "it is trivial to introduce an XSS vulnerability" | https://react.dev/reference/react-dom/components/common |
| R22 | "reachable via direct POST requests" | https://nextjs.org/docs/app/guides/data-security |
| R23 | "prefixed with NEXT_PUBLIC_ are included in the client bundle" | https://nextjs.org/docs/app/getting-started/server-and-client-components |
| C18 | "users can bookmark the current state of the application, including their search queries and filters, for future reference or sharing" | https://nextjs.org/learn/dashboard-app/adding-search-and-pagination |
