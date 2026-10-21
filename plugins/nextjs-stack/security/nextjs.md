# Next.js security checklist (nextjs-stack)

`/rails-flow:secure-design` reads this file for a project whose stack is Next.js (App Router), after it has drawn the
data flow and the trust boundaries. The detector names it: `detect_stack.py` lists it under `security` from this
plugin's `stacks.json`. A Supabase project also gets `supabase.md`, from the `supabase` stack.

The process is the same for every stack. This file is only the Next.js **surface**: the questions a STRIDE pass asks,
each answered in the model as a row with a decision (mitigate, transfer, accept, eliminate). It adds no doctrine of its
own. Each question that rests on a framework fact cites it as `(C-n)`, a CONFIRMED row of
`docs/evidence/audits/2026-10-21-nextjs-security-claims.md` in the claude-skills repository, quoted from the official docs.

## Spoofing — who is this request from?

- Every Server Function (`"use server"`) this boundary adds: where inside it is the caller authenticated? It is reachable
  by a direct POST, not only from the form that calls it (C-4)
- Every Route Handler (`app/**/route.ts`): what does it check before it answers? It is a public endpoint (C-5)
- Does the design lean on Proxy (`proxy.ts`, formerly `middleware.ts`) to keep a route private? Proxy runs only on
  the paths its `matcher` selects; where is the check repeated next to the data (C-6)
- With Supabase Auth on the server: is the user read with `getClaims()`, never trusted from `getSession()` (C-9)

## Tampering — can the input change what it must not?

- Each Server Function argument and Route Handler body: where is it validated before it reaches the database?
- A redirect built from `searchParams` or a form field: is the target restricted to this site?

## Repudiation — can we show who did it?

- Is the action recorded with who, what and when, server-side, where the browser cannot rewrite it?

## Information disclosure — what can leak?

- Every new `NEXT_PUBLIC_` variable: is it safe for anyone to read? It is inlined into the JavaScript sent to the
  browser at build time (C-3)
- Does any secret (a service key, a signing key) sit in a variable a Client Component imports? Name where it is read.
- What does a Server Component pass as props to a Client Component, and may the browser see all of it?
- Errors: does a failed action or handler return more than the caller may see?

## Denial of service — what can be exhausted?

- A public Server Function or Route Handler that writes, sends mail or calls a paid API: what limits its rate?
- Uploads: size and count ceilings before the body is read.

## Elevation of privilege — who may do this?

- Authorization: is the rule checked inside the Server Function or handler, in a data-access layer, not only in the
  page that renders the button (C-6)
- A Proxy `matcher` change: which paths stop running Proxy, and does any of them rely on it (C-6)

## Scanners this stack runs

`npm audit`, as the descriptor lists it, for the dependency tree. A threat-model row a scanner covers says which one,
so the per-row audit can point at its output.
