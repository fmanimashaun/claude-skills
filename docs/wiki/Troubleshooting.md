# Troubleshooting

Most of what goes wrong here fails **silently** — it returns a plausible result rather than an
error. That is what this page is for.

## "Claude keeps asking me to confirm every command"

Commands are **compound pipelines**, and the whole string is evaluated, so **one** unlisted binary
anywhere in the chain re-prompts all of it. A permission list holding `git`, `gh` and `python3` but
not `grep` still prompts on most real commands.

Fix it in `~/.claude/settings.json` (all your projects) or a project's gitignored
`.claude/settings.local.json` — never a repo's tracked `settings.json`, which every clone inherits.
If you want no friction at all, choose a permission **mode** deliberately rather than arriving at one
by extending a list of binaries.

## "The version I have is not the version I think I have"

```bash
/rails-flow:toolchain-check
```

Two install records for one plugin can coexist in the cache, ordered only by `lastUpdated`. Reading
the wrong one reports a stale version as current.

## "The a11y audit flags every page"

Check it is deciding focus indicators by a **resting-vs-focused diff** rather than a property
lookup. A design system carrying its ring in `box-shadow` reports `outline: none` — a lookup calls
that a missing indicator and raises a blocking S1 on every page.

## "The asset generator refuses everything"

That is usually correct. In order, it refuses: an unsearched library, an unrecorded tier-1/2
refusal, a free-typed prompt, no aggregator configured, a cost over the ceiling. **Read the refusal
reason verbatim** — it names the one thing to fix. A missing API key is the expected state of a
fresh install, not a fault.

## "The QA pass says it passed but I do not believe it"

Look for the sampling row. *"Walked 25 of 72 pages"* with nothing reported missing is the shape to
distrust — a low count and a clean verdict together mean the pass sampled where the contract is
exhaustive.

## Captures that came out empty or wrong

Three silent failures, all of which produce a *file* rather than an error:

- **Lazy loading** — capture before scrolling and you get empty placeholders. Scroll in ~400px
  increments with a pause, then return to the top.
- **A login wall** — returns a sign-in page, filed as a reference. Sign in once into the persistent
  browser profile.
- **A rotted selector** — CSS-in-JS class names regenerate on every build. Select by role or
  semantics instead.
