# AGENTS.md

Harness-neutral agent rules for this repo. Claude Code also reads `CLAUDE.md`; this file
does not repeat it.

## Measure before you assert

Never state a count, an environment fact, or a claim that justifies a design decision from
memory, from earlier in the session, or from assumption. Re-check it against the live source
at the moment you state it.

- **Counts and tallies** — re-run the query before quoting the number — the test command, the
  gate, or `gh issue list --state open --limit 200` kept on ONE line so the check below can
  see the flag. A number from earlier in the session is stale by
  default; do not carry it forward. An open-issue count has already been reported wrong and had to
  be corrected by hand. **Bound the command too**: `gh issue/pr list` silently defaults to
  `--limit 30`, so an unbounded call re-run at the moment you quote it still reports one page as
  the total — measuring the wrong thing carefully. `lint_self_consistency.py`'s
  `unbounded-issue-query` rule enforces this, and it fired on the first draft of this very
  paragraph.
- **Environment and CI facts** — open the file before describing it. Claims like "CI has no
  browser" or "this repo ships no `package.json`" must come from reading
  `.github/workflows/*.yml` and the actual tree, not from inference. These are load-bearing:
  they get used to justify a design, so a wrong one produces a wrong design.
- **Tool and service availability** — attempt a real read-only call before declaring a tool,
  MCP server, or credential unavailable or unauthenticated. Cached `/mcp` output and prior
  session state are not evidence that a live call would fail.

When you notice you are about to guess, go and measure instead of hedging. A hedged
recommendation is not an acceptable substitute for running the check — if the check is
possible, run it, then answer. Report an unknown only when measuring is genuinely impossible,
and say what you tried.

Say how you know. Name the command you ran or the file you read alongside any load-bearing
fact, so a stale claim is visible instead of being taken on trust.

## Write the mechanism out; don't compress it into a label

Never let a coined name stand in for the thing it names. A term like "the one unresolved
mechanism", "the licensing call", "Phase 3", or "the stack descriptor" only works on a
reader who already knows what it means — and here they did not: both of those first two
phrases came straight back as "not sure i understand this" and "what do u mean licensing
call".

Before naming a mechanism or a decision, spell it out in this order:

1. **What is true today** — "`rails-flow` is one self-contained plugin: install it and you
   get the commands, the agents, and the guardrail hooks."
2. **What the proposal changes** — "it splits into `dev-flow` (commands, validators,
   runner) and `stack-rails` (rubocop hook, rspec stop-gate, architecture graph)."
3. **Why it is unresolved, or what breaks** — "those two only work together, and no
   `plugin.json` in this repo has a `requires` field, so nothing can say so. Prose in a
   description is a sentence, not a mechanism."

The same applies to headings and summary bullets. "Two decisions worth recording" is not a
summary until each decision is stated. Labels and abbreviations are for referring back to
something already explained in plain terms, never for introducing it.

## End the analysis with the call, then make it

Constraints, options, and trade-offs are the setup, not the answer. Close a design analysis
with **one** concrete recommended next move — named, specific, already chosen — not a ranked
menu and not a neutral survey. "so what is your proposal?", "what do u recommend?", and "i
said make the call on what you feel is the next move and let continue to other works" are
all the same correction: the write-up stopped one step short.

- Recommend **one** thing. If a real alternative deserves a mention, say in a sentence why
  you rejected it, then move on.
- State the next move and then carry it out. Do not pause for approval on work already
  sanctioned.
- Stop only for genuinely irreversible or outward-facing steps — merging the promotion that
  publishes a release, deleting a repo, anything with a public blast radius. Say plainly
  that it publishes, and hand that call over.
