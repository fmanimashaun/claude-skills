# Next.js + Supabase security surface — claim audit (#2210)

The framework claims behind nextjs-stack's security checklists (`plugins/nextjs-stack/security/nextjs.md`, `supabase.md`).
Verified 2026-10-21 by doctrine-verifier against nextjs.org/docs (Next.js 16.4.2) and supabase.com/docs, then re-checked
with `check_verdict_quotes.py` (#2249): every quoted phrase is an exact substring of the page's visible text.
A checklist question cites its claim as `(C-n)` at the end of its line.

Corrections against the issue's draft list: C-1 ties exposure to role grants, not to the anon key directly; C-8's CLI is
`supabase db advisors`, not `supabase db lint`; C-11's public bucket skips checks for reads only.

## C-1 — Supabase RLS on exposed tables

Claim: A table in an exposed schema without RLS is readable and writable by any role with a grant on it; on projects that still grant `anon`/`authenticated` by default, that is anyone holding the publishable/anon key. Enable RLS on every table in an exposed schema and revoke the default grants.

Version: 2026-10-21 (Supabase docs, unversioned)

Verdict: CONFIRMED [quotes: C-1]

```quotes C-1
https://supabase.com/docs/guides/database/postgres/row-level-security | 2026-10-21 | A table in an exposed schema without RLS is readable and writable by any role with a grant on it.
https://supabase.com/docs/guides/database/postgres/row-level-security | 2026-10-21 | Enable RLS on every table in an exposed schema.
https://supabase.com/docs/guides/database/postgres/row-level-security | 2026-10-21 | On projects that still grant anon and authenticated by default, revoke those grants.
```

## C-2 — The service-role / secret key

Claim: The `service_role` (secret) key bypasses RLS and must never reach a browser, a shipped app or source control.

Version: 2026-10-21

Verdict: CONFIRMED [quotes: C-2]

```quotes C-2
https://supabase.com/docs/guides/getting-started/api-keys | 2026-10-21 | It bypasses Row Level Security, so it must never leave your control
https://supabase.com/docs/guides/getting-started/api-keys | 2026-10-21 | Never put one in a browser, a shipped application, or source control
```

## C-3 — `NEXT_PUBLIC_` exposure

Claim: `NEXT_PUBLIC_` variables are inlined into the JavaScript sent to the browser at `next build`; only direct `process.env.NEXT_PUBLIC_X` references are inlined.

Version: Next.js 16.4.2

Verdict: CONFIRMED [quotes: C-3]

```quotes C-3
https://nextjs.org/docs/app/guides/environment-variables | v16.4.2 | these public environment variables will be inlined into the JavaScript bundle during next build
https://nextjs.org/docs/app/guides/environment-variables | v16.4.2 | It will be inlined into any JavaScript sent to the browser.
```

## C-4 — Server Functions are public endpoints

Claim: A Server Function (`"use server"`) is reachable by a direct POST request, so authentication and authorization are verified inside each one.

Version: Next.js 16.4.2

Verdict: CONFIRMED [quotes: C-4]

```quotes C-4
https://nextjs.org/docs/app/guides/data-security | v16.4.2 | it is reachable via a direct POST request, not just through your application's UI
https://nextjs.org/docs/app/guides/data-security | v16.4.2 | verify authentication and authorization inside each one
```

## C-5 — Route Handlers are public endpoints

Claim: Treat each Route Handler as a public-facing API endpoint and verify inside it that the user may access it.

Version: Next.js 16.4.2

Verdict: CONFIRMED [quotes: C-5]

```quotes C-5
https://nextjs.org/docs/app/guides/authentication | v16.4.2 | Treat Route Handlers with the same security considerations as public-facing API endpoints
https://nextjs.org/docs/app/guides/authentication | v16.4.2 | verify if the user is allowed to access the Route Handler.
```

## C-6 — Proxy (formerly Middleware) and its matcher

Claim: In Next.js 16 Middleware is renamed Proxy; it runs on the paths its `matcher` selects, and auth is verified inside each Server Function rather than relying on Proxy alone, close to the data.

Version: Next.js 16.4.2 (renamed in 16.0.0)

Verdict: CONFIRMED [quotes: C-6]

```quotes C-6
https://nextjs.org/docs/app/api-reference/file-conventions/proxy | v16.4.2 | The middleware file convention is deprecated and has been renamed to proxy.
https://nextjs.org/docs/app/api-reference/file-conventions/proxy | v16.4.2 | The matcher option allows you to target specific paths for the Proxy to run on.
https://nextjs.org/docs/app/api-reference/file-conventions/proxy | v16.4.2 | Always verify authentication and authorization inside each Server Function rather than relying on Proxy alone.
https://nextjs.org/docs/app/guides/authentication | v16.4.2 | you should do the checks close to your data source
```

## C-7 — Edge Functions and `verify_jwt`

Claim: Edge Functions default to `verify_jwt = true`; turned off per function (`verify_jwt = false` in `config.toml`, or `--no-verify-jwt` when serving locally), anyone can invoke the function, so it must authenticate callers itself.

Version: 2026-10-21

Verdict: CONFIRMED [quotes: C-7]

```quotes C-7
https://supabase.com/docs/guides/functions/auth | 2026-10-21 | The default is verify_jwt = true, so the platform validates the JWT before your handler runs.
https://supabase.com/docs/guides/functions/function-configuration | 2026-10-21 | it will allow anyone to invoke your Edge Function without a valid JWT
```

## C-8 — Supabase Security Advisor

Claim: The Security Advisor flags security issues such as misconfigured RLS policies; it runs from Studio, the CLI (`supabase db advisors`, not `supabase db lint`) and the Management API.

Version: 2026-10-21

Verdict: CONFIRMED [quotes: C-8]

```quotes C-8
https://supabase.com/docs/guides/observability/advisors | 2026-10-21 | misconfigured RLS policies, or missing indexes
https://supabase.com/docs/guides/observability/advisors | 2026-10-21 | CLI: supabase db advisors
https://supabase.com/docs/guides/observability/advisors | 2026-10-21 | Management API: security, performance, and health advisors
```

## C-9 — `getSession()` in server code

Claim: Never trust `supabase.auth.getSession()` in server code: it reads the cookie without revalidating; protect pages and data with `getClaims()` (`getUser()` for a fresh user record).

Version: 2026-10-21

Verdict: CONFIRMED [quotes: C-9]

```quotes C-9
https://supabase.com/docs/guides/auth/server-side/creating-a-client?queryGroups=framework&framework=nextjs | 2026-10-21 | Never trust supabase.auth.getSession() inside server code such as Proxy.
https://supabase.com/docs/guides/auth/server-side/creating-a-client?queryGroups=framework&framework=nextjs | 2026-10-21 | Always use supabase.auth.getClaims() to protect pages and user data.
```

## C-10 — Views bypass RLS

Claim: Views bypass RLS by default; on Postgres 15+ create them with `security_invoker = true`.

Version: Postgres 15+

Verdict: CONFIRMED [quotes: C-10]

```quotes C-10
https://supabase.com/docs/guides/database/postgres/row-level-security | 2026-10-21 | Views bypass RLS by default because they are usually created with the postgres user.
https://supabase.com/docs/guides/database/postgres/row-level-security | 2026-10-21 | by setting security_invoker = true
```

## C-11 — Storage buckets

Claim: Object access is controlled by RLS policies on `storage.objects`; a public bucket serves files to anyone with the URL, while uploads, deletes, moves and copies still go through access control.

Version: 2026-10-21

Verdict: CONFIRMED [quotes: C-11]

```quotes C-11
https://supabase.com/docs/guides/storage/security/access-control | 2026-10-21 | You selectively allow certain operations by creating RLS policies on the storage.objects table.
https://supabase.com/docs/guides/storage/buckets/fundamentals | 2026-10-21 | anyone who possesses the asset URL can readily access the file.
https://supabase.com/docs/guides/storage/buckets/fundamentals | 2026-10-21 | Access control is still enforced for other types of operations including uploading, deleting, moving, and copying.
```
