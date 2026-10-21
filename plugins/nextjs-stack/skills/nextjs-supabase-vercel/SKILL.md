---
name: nextjs-supabase-vercel
description: How Next.js, Supabase and Vercel fit together in one project, and where each one's own guidance lives. Use when a project uses Next.js with Supabase and Vercel (the stack detector reports `nextjs`, `supabase` or `vercel`), when wiring Supabase keys or environment variables into a Next.js app, when generating database types for the app, or when deciding which official plugin to install. Platform knowledge is NOT here; it is in Vercel's plugin, the Next.js skills and supabase/agent-skills, and this skill points to them.
---

# Next.js + Supabase + Vercel

This skill is the seam between three platforms. It holds **only how they fit together**. Each platform's own knowledge belongs to its vendor, and this skill points there instead of copying it, so it never goes stale against the source.

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
- Supabase issues two kinds of API key, one meant for the browser and one only for servers. What each may reach, and how Row Level Security bounds the browser one, is Supabase's to say: read [Supabase API keys](https://supabase.com/docs/guides/api/api-keys) and [Row Level Security](https://supabase.com/docs/guides/database/postgres/row-level-security).

So the rule for this stack: **the publishable key may carry `NEXT_PUBLIC_`; the secret key never does**, and it is read only in server code. A secret key under a `NEXT_PUBLIC_` name is a leak, whatever the code around it does.

## 3. The vendor steps are the vendors' to teach

The CLI steps are not copied here: each vendor ships them, kept current against its own releases. The flows do not drive them yet.

- Hand-off: for the Supabase CLI steps (the local stack, migrations, schema diffs, generated types, advisors) use the vendor's `supabase` skill (supabase/agent-skills, installed in section 1); its "Supabase CLI" section owns the commands.
- Hand-off: for the Vercel steps (linking this directory to its project, pulling environment variables, deploying, project status) use the vendor plugin's commands `/vercel:bootstrap`, `/vercel:env`, `/vercel:deploy` and `/vercel:status` (vercel/vercel-plugin, installed in section 1).

Generated types are the contract between the database and the app: regenerate them with each migration, so the TypeScript build catches a schema change the code has not followed.

## What is deliberately not here

Routing, caching, rendering, auth flows, RLS policy design, deploy configuration and pricing. Each belongs to the official guidance in section 1. A rule that only restates a vendor's documentation does not belong in this skill.
