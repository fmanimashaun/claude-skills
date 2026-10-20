---
name: nextjs-supabase-vercel
description: How Next.js, Supabase and Vercel fit together in one project, and where each one's own guidance lives. Use when a project uses Next.js with Supabase and Vercel (the stack detector reports `nextjs`, `supabase` or `vercel`), when wiring Supabase keys or environment variables into a Next.js app, when generating database types for the app, or when deciding which official plugin to install. Platform knowledge is NOT here; it is in Vercel's plugin, the Next.js skills and supabase/agent-skills, and this skill points to them.
---

# Next.js + Supabase + Vercel

This skill is the seam between three platforms. It holds **only how they fit together**. Each platform's own knowledge belongs to its vendor, and this skill points there instead of copying it, so it never goes stale against the source (claude-skills EPIC #2162, decision 1).

Every fact below was checked against the vendor's documentation on 2026-10-20, with the page cited beside it. Re-check the source before relying on it after a vendor release.

## 1. Install the official guidance first

| For | Install | Source |
|---|---|---|
| Vercel (deploys, the CLI, the platform) | `npx plugins add vercel/vercel-plugin` | [Vercel plugin docs](https://vercel.com/docs/agent-resources/vercel-plugin) |
| Next.js (the framework) | `npx skills add vercel/next.js` (Vercel's plugin "doesn't ship Next.js skills") | [Vercel plugin docs](https://vercel.com/docs/agent-resources/vercel-plugin) |
| Supabase (database, auth, RLS) | `claude plugin marketplace add supabase/agent-skills`, then `claude plugin install supabase@supabase-agent-skills` (and `postgres-best-practices@supabase-agent-skills`) | [supabase/agent-skills](https://github.com/supabase/agent-skills) |

When one of those plugins answers a question, follow it. This skill only covers what falls between them.

## 2. Keys and environment variables: the one seam that leaks

The failure this stack invites is a server-only Supabase key reaching the browser bundle, because Next.js decides what reaches the browser by **name**:

- Next.js exposes to the browser only variables prefixed `NEXT_PUBLIC_`, and inlines them at `next build` ([Next.js environment variables](https://nextjs.org/docs/app/guides/environment-variables)).
- Supabase's **publishable** key (`sb_publishable_…`; the legacy name is `anon`) may reach the browser: "Anyone can read it, so it only reaches what Row Level Security allows." Enable Row Level Security on every table before you deploy ([Supabase API keys](https://supabase.com/docs/guides/api/api-keys)).
- Supabase's **secret** key (`sb_secret_…`; the legacy name is `service_role`): "Never put one in a browser, a shipped application, or source control" ([Supabase API keys](https://supabase.com/docs/guides/api/api-keys)).

So the rule for this stack: **the publishable key may carry `NEXT_PUBLIC_`; the secret key never does**, and it is read only in server code. A secret key under a `NEXT_PUBLIC_` name is a leak, whatever the code around it does.

## 3. The CLIs are driven, not reimplemented

The flows drive both vendors' CLIs rather than rebuilding them (EPIC #2162, decision 2):

| Step | Command | Source |
|---|---|---|
| Local Supabase for development and tests (needs Docker) | `supabase start` | [Supabase CLI getting started](https://supabase.com/docs/guides/local-development/cli/getting-started) |
| A new migration | `supabase migration new <name>` | [Supabase CLI reference](https://supabase.com/docs/reference/cli/introduction) |
| Schema changes as SQL | `supabase db diff` | [Supabase CLI reference](https://supabase.com/docs/reference/cli/introduction) |
| TypeScript types from the database schema | `supabase gen types --lang typescript` | [Supabase CLI reference](https://supabase.com/docs/reference/cli/introduction) |
| Link this directory to its Vercel project | `vercel link` | [vercel link](https://vercel.com/docs/cli/link) |
| Pull the development environment variables | `vercel env pull .env.local` (name the file: the default is described both as `.env` and `.env.local`) | [vercel env](https://vercel.com/docs/cli/env) |

Generated types are the contract between the database and the app: regenerate them with each migration, so the TypeScript build catches a schema change the code has not followed.

## What is deliberately not here

Routing, caching, rendering, auth flows, RLS policy design, deploy configuration and pricing. Each belongs to the official guidance in section 1. A rule that only restates a vendor's documentation does not belong in this skill.
