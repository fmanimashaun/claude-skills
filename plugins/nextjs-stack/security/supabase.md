# Supabase security checklist (nextjs-stack)

`/rails-flow:secure-design` reads this file for a project that uses Supabase (`supabase/config.toml`), whatever its
web framework. The detector names it from the `supabase` stack in this plugin's `stacks.json`.

This file is only the Supabase **surface**: the questions a STRIDE pass asks, each answered in the model as a row with a
decision. It adds no doctrine of its own. Each question that rests on a framework fact cites it as `(C-n)`, a CONFIRMED
row of `docs/evidence/audits/2026-10-21-nextjs-security-claims.md` in the claude-skills repository.

## Spoofing — who is this request from?

- Each Edge Function this boundary adds or changes: does it keep `verify_jwt` on? If it is off (a webhook, say), how
  does the function authenticate the caller itself (C-7)
- Server code that reads the user: `getClaims()`, never a trusted `getSession()` (C-9)

## Tampering — can the input change what it must not?

- Each new or changed table in an exposed schema: is RLS enabled, and which policy allows each of select, insert,
  update and delete (C-1)
- An `update` policy: does its `with check` stop a row being moved to another owner?

## Repudiation — can we show who did it?

- Is the change recorded with who and when, in a table the `anon` and `authenticated` roles cannot rewrite?

## Information disclosure — what can leak?

- Does the `service_role` (secret) key stay on the server, out of every client bundle and out of source control (C-2)
- Each new view: on Postgres 15 or later, is it created with `security_invoker = true` (C-10)
- Each storage bucket: public or private? A public bucket serves every file to anyone with the URL (C-11)
- Uploads, deletes and moves in storage: which `storage.objects` policy allows them (C-11)

## Denial of service — what can be exhausted?

- A public Edge Function or an `anon`-callable function: what limits its rate and its cost?

## Elevation of privilege — who may do this?

- Default grants: does `anon` or `authenticated` hold a grant this boundary does not need (C-1)
- A `security definer` function: which role runs it, and can an `anon` caller reach it?

## Scanners this stack runs

Hand-off: Supabase's Security Advisor, run from Studio or through the vendor's `supabase` skill (supabase/agent-skills), as the descriptor lists it. It flags
misconfigured RLS among other issues (C-8)
