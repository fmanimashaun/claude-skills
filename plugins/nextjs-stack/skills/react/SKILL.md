---
name: react
description: "React and Next.js App Router frontend architecture: composition, the Server/Client boundary, data and state, streaming, performance and the frontend's security share, each rule with its enforcement. Use when writing or reviewing React components in a Next.js project."
---

# React frontend architecture (Next.js App Router)

Patterns that hold and anti-patterns that bite, for React 19.3 with the Next.js 16.4 App Router. Every rule here was checked against react.dev and the Next.js docs on 2026-10-21; each cites the page it comes from. The layers are the same eight that the Hotwire architecture uses, so the two stacks compare row for row; the stack-neutral contracts behind them (shell, regions, the UX and performance contracts) are the design system's.

**Enforcement.** Every rule names what holds it:
- **default lint**: a rule `eslint-config-next` already turns on; run the project's lint.
- **`react-patterns`** / **`react-lint-off-by-default`**: nextjs-stack's own checks (`checks.json`), run by `/rails-flow:gates`.
- **declaration**: the exception is allowed only when the file states it, and the check verifies the statement.
- **verified advice**: a judgement no check can make today. It cites the confirmed claim it rests on and is followed as advice; it becomes a recorded-verdict rule (the reviewer records pass or fail with evidence, and a PR without the verdict is refused) when rails-flow #2225 lands. Until then nothing refuses a PR for it.

## 1. Composition

- **Declare every component at the top level.** A component defined inside another is a new type on every render, so React remounts it and its state is lost. *Enforcement: default lint (`react-hooks/static-components`).* [react.dev: preserving and resetting state](https://react.dev/learn/preserving-and-resetting-state)
- **Compose through `children` before drilling props.** When a component only forwards props it does not use, pass the JSX as `children`; reach for context only when props and composition do not fit. *Enforcement: verified advice (a recorded-verdict rule once #2225 lands).* [react.dev: passing data deeply with context](https://react.dev/learn/passing-data-deeply-with-context)
- **One concern per component.** When a component grows, decompose it (react.dev calls this separation of concerns). *Enforcement: verified advice (a recorded-verdict rule once #2225 lands).* [react.dev: thinking in React](https://react.dev/learn/thinking-in-react)
- **Keys are stable, unique among siblings, and never change.** An index key on a list that reorders, filters or inserts attaches state to the wrong row; a key generated during render (`Math.random()`) remounts every item. An index is fine for a list that never reorders. *Enforcement: default lint (`react/jsx-key`, `react-hooks/purity`) and `react-lint-off-by-default` (`react/no-array-index-key`).* [react.dev: rendering lists](https://react.dev/learn/rendering-lists)
- **Server Components by default.** Pages and layouts are Server Components; a component needs `"use client"` only for state, effects, custom hooks, event handlers or browser-only APIs. *Enforcement: verified advice (a recorded-verdict rule once #2225 lands); a check cannot see whether a third-party import is the reason a module needs the client.* [Next.js: Server and Client Components](https://nextjs.org/docs/app/getting-started/server-and-client-components)

## 2. Shell, navigation and page templates

- **Navigate internal routes with `<Link>`.** It does client-side navigation and prefetches in production (a static route fully, a dynamic route down to its nearest `loading.js`); a plain `<a>` to an internal route reloads the whole page. *Enforcement: `react-patterns` (`internal-anchor`; the Next lint rule only reads a `pages/` directory).* [Next.js: Link](https://nextjs.org/docs/app/api-reference/components/link)
- **Give each route segment its own error and not-found boundary.** `error.js` is a Client Component that contains an error to its segment (errors bubble to the nearest boundary; event handlers and async code are not caught); `not-found.js` renders for `notFound()`. *Enforcement: verified advice (a recorded-verdict rule once #2225 lands).* [Next.js: error handling](https://nextjs.org/docs/app/getting-started/error-handling)

## 3. Regions and flow

- **Put `"use client"` on the smallest interactive leaf.** A high boundary does not lose server rendering (Client Components still prerender HTML), but the subtree loses Server Components and ships more JavaScript. The boundary covers a module's imports and the components it renders directly, not Server Components passed to it as `children` or props. *Enforcement: `react-patterns` (`use-client-route-file`), passed by **declaration** when a client route is a deliberate trade-off: a comment `react-architecture: client-route -- <reason>` in that file.* [Next.js: Server and Client Components](https://nextjs.org/docs/app/getting-started/server-and-client-components)
- **Props crossing to a Client Component are serializable.** The only functions allowed are Server Functions (or functions exported from client modules); no class instances other than built-ins, no null-prototype objects. *Enforcement: the framework (a runtime error).* [react.dev: 'use client'](https://react.dev/reference/rsc/use-client)
- **Stream slow parts.** Wrap a slow part in `<Suspense>`, close to the data, or add `loading.js` to the segment, so the rest of the page is not blocked by its slowest fetch. A layout that reads uncached data blocks, because it does not fall back to its own segment's `loading.js`. *Enforcement: verified advice (a recorded-verdict rule once #2225 lands).* [Next.js: fetching data](https://nextjs.org/docs/app/getting-started/fetching-data)

## 4. Data and state

- **Compute derived values during render**, not in an Effect that stores them with `setState` (that renders once with a stale value, then again). Use `useMemo` only when the computation is expensive: measure first. *Enforcement: default lint (`react-hooks/set-state-in-effect` flags the shape).* [react.dev: you might not need an Effect](https://react.dev/learn/you-might-not-need-an-effect)
- **Reset state on a prop change with a `key`**, not an Effect. *Enforcement: default lint (same rule).* [react.dev: you might not need an Effect](https://react.dev/learn/you-might-not-need-an-effect)
- **Lift shared state to the closest common parent** and pass it down: one source of truth, never two copies kept in sync. *Enforcement: verified advice (a recorded-verdict rule once #2225 lands).* [react.dev: sharing state between components](https://react.dev/learn/sharing-state-between-components)
- **Keep state as local as it can be.** State lifted higher than needed widens what re-renders. *Enforcement: verified advice (a recorded-verdict rule once #2225 lands).* [react.dev: useMemo](https://react.dev/reference/react/useMemo)
- **Memoise a context provider's value.** Every consumer re-renders when the value changes, and an object or function built inline is new on every render; wrap it in `useMemo` / `useCallback`. `memo` does not stop a context re-render. *Enforcement: `react-lint-off-by-default` (`react/jsx-no-constructed-context-values`).* [react.dev: useContext](https://react.dev/reference/react/useContext)
- **Fetch a page's data in a Server Component**, not in a client Effect: Effects do not run on the server and create waterfalls. In client code use `use` or a data library (SWR, React Query); an Effect that does fetch needs cleanup to ignore stale responses. *Enforcement: `react-patterns` (`fetch-in-effect`).* [react.dev: synchronizing with Effects](https://react.dev/learn/synchronizing-with-effects)
- **Start independent requests together.** Awaiting them one after another is sequential; use `Promise.all` (or `Promise.allSettled` when one failure must not fail the rest). *Enforcement: verified advice (a recorded-verdict rule once #2225 lands).* [Next.js: fetching data](https://nextjs.org/docs/app/getting-started/fetching-data)

## 5. UX

The loading, empty, error, optimistic and focus states are the design system's contract; React's part is the streaming and boundaries in layers 2 and 3, and:

- **Load images and fonts through `next/image` and `next/font`**, which avoid layout shift (a remote image needs `width`/`height` or `fill`); a raw `<img>` loses that. *Enforcement: default lint (`@next/next/no-img-element`, `google-font-display`, `google-font-preconnect`).* [Next.js: images](https://nextjs.org/docs/app/getting-started/images)

## 6. Performance

- **Memoisation is an optimisation, never a fix.** Code must work without `useMemo`, `useCallback` or `memo`; when it does not, fix the cause. Rely on the React Compiler for new code, keep manual memoisation as an escape hatch (for example Effect dependencies), and do not strip existing memoisation without testing. *Enforcement: verified advice (a recorded-verdict rule once #2225 lands).* [react.dev: useMemo](https://react.dev/reference/react/useMemo) · [React Compiler 1.0](https://react.dev/blog/2025/10/07/react-compiler-1)
- **Lazy-load heavy Client Components** with `next/dynamic` / `React.lazy` to shrink the initial bundle. Server Components are split automatically; a Server Component that dynamically imports a Client Component gets no splitting from it. *Enforcement: verified advice (a recorded-verdict rule once #2225 lands).* [Next.js: lazy loading](https://nextjs.org/docs/app/guides/lazy-loading)

The other performance rules sit with their layer: stable component types and keys (1), the client boundary and streaming (3), context values and parallel fetching (4), images and fonts (5).

## 7. Security (the frontend's share)

nextjs-stack's security surface (the checklist, scanners and boundary patterns) is its own issue, #2210. The frontend architecture states only these:

- **`dangerouslySetInnerHTML` only with trusted, sanitised data.** It bypasses React's escaping. *Enforcement: `react-lint-off-by-default` (`react/no-danger` flags every use; keep it for sanitised markup only).* [react.dev: common components](https://react.dev/reference/react-dom/components/common)
- **Every Server Action is a public endpoint.** Check authentication, authorisation and ownership of the resource inside each action; a page-level check does not cover the actions defined in that page. *Enforcement: nextjs-stack's security surface (#2210).* [Next.js: data security](https://nextjs.org/docs/app/guides/data-security)
- **Whatever reaches a Client Component reaches the browser**, and so does every `NEXT_PUBLIC_` variable. Keep secrets in Server Components and mark server-only modules with `import "server-only"` (a build error if a client module imports it). *Enforcement: the framework's build error; the key seam is in the `nextjs-supabase-vercel` skill.* [Next.js: data security](https://nextjs.org/docs/app/guides/data-security)

## 8. Anti-patterns that bite

| anti-pattern | rule | what catches it |
|---|---|---|
| a component defined inside a component | 1 | default lint |
| an index or random `key` | 1 | default lint + `react-lint-off-by-default` |
| derived state or a prop reset in an Effect | 4 | default lint |
| an inline object as a context value | 4 | `react-lint-off-by-default` |
| `"use client"` on a route file, unexplained | 3 | `react-patterns` + declaration |
| `fetch` in a client Effect | 4 | `react-patterns` |
| an internal `<a>` | 2 | `react-patterns` |
| a raw `<img>`, unoptimised fonts | 5 | default lint |
| unsanitised `dangerouslySetInnerHTML` | 7 | `react-lint-off-by-default` |
| a Server Action without its own auth check | 7 | the security surface (#2210) |
| prop drilling, a component with many concerns, state too high or duplicated, memoisation as a band-aid, an unneeded `"use client"`, sequential independent fetches, missing boundaries or streaming | 1–6 | verified advice; a recorded verdict once #2225 lands |

## Rules that become recorded-verdict rules when #2225 lands

When the recorded-verdict mechanism (rails-flow #2225) lands, a PR that changes React components will need a verdict for each of these; until then they are verified advice and nothing refuses a PR for them. The registry format will be #2225's; this list is the declaration to move into it:

`compose-through-children`, `one-concern-per-component`, `server-components-by-default`, `segment-boundaries`, `stream-slow-parts`, `lift-shared-state`, `keep-state-local`, `parallel-requests`, `memoisation-not-a-fix`, `lazy-load-heavy-client`.
